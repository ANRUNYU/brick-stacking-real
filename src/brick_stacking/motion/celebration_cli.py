"""Command-line entry point for the bounded asymmetric celebration motion."""

from __future__ import annotations

import argparse
import json
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .celebration import MAX_LOOPS, build_celebration_plan, run_celebration

_DRY_LEFT_START = (-0.0393, -0.0062, 0.0018, -0.0354, 1.5961, -0.03, 0.24)
_DRY_RIGHT_START = (0.0078, -0.0047, 0.3459, 0.044, -0.1243, -0.27, -0.35)


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _default_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "celebration" / f"celebration_{stamp}.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the loop-safe asymmetric dual-arm celebration. Default is a "
            "dry plan and never opens CAN."
        )
    )
    parser.add_argument(
        "--loops",
        type=int,
        required=True,
        help=f"explicit cycle count, 1..{MAX_LOOPS}",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--left-interface", default="can2")
    parser.add_argument("--right-interface", default="can3")
    parser.add_argument(
        "--enable-live-motion",
        action="store_true",
        help="open the P7 arms and move; dry-plan only when omitted",
    )
    parser.add_argument(
        "--authorization-ref",
        default="",
        help="required non-empty per-run authorization reference for live motion",
    )
    parser.add_argument("--confirm-empty-hands", action="store_true")
    parser.add_argument("--confirm-clear-workspace", action="store_true")
    parser.add_argument("--confirm-physical-stop", action="store_true")
    return parser


def _live_gate_errors(args: argparse.Namespace) -> list[str]:
    errors = []
    if not str(args.authorization_ref).strip():
        errors.append("--authorization-ref is required")
    for name in (
        "confirm_empty_hands",
        "confirm_clear_workspace",
        "confirm_physical_stop",
    ):
        if not getattr(args, name):
            errors.append("--" + name.replace("_", "-") + " is required")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output or _default_output()
    stamp_utc = datetime.now(timezone.utc).isoformat()

    try:
        dry_plan = build_celebration_plan(
            _DRY_LEFT_START,
            _DRY_RIGHT_START,
            loops=args.loops,
        )
    except (TypeError, ValueError) as exc:
        print(f"invalid celebration request: {exc}")
        return 2

    if not args.enable_live_motion:
        report = {
            "schema_version": "celebration-asymmetric-run-0.1",
            "stamp_utc": stamp_utc,
            "verdict": "DRY_PLAN_ONLY",
            "motion_enabled": False,
            "control_ready": False,
            "plan": dry_plan.as_dict(),
        }
        _write_report(output, report)
        print(json.dumps({"verdict": report["verdict"], "output": str(output)}, indent=2))
        return 0

    gate_errors = _live_gate_errors(args)
    if gate_errors:
        report = {
            "schema_version": "celebration-asymmetric-run-0.1",
            "stamp_utc": stamp_utc,
            "verdict": "REFUSED",
            "motion_enabled": False,
            "control_ready": False,
            "errors": gate_errors,
        }
        _write_report(output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    try:
        from linkerbot import P7
    except ImportError:  # pragma: no cover - depends on vendor package layout
        from linkerbot.arm.p7 import P7

    arms: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": "celebration-asymmetric-run-0.1",
        "stamp_utc": stamp_utc,
        "authorization_ref": str(args.authorization_ref),
        "requested_loops": int(args.loops),
        "motion_enabled": True,
        "control_ready": False,
        "safety_confirmations": {
            "empty_hands": True,
            "clear_workspace": True,
            "physical_stop": True,
        },
        "interfaces": {
            "left": str(args.left_interface),
            "right": str(args.right_interface),
        },
        "events": events,
        "verdict": "INCOMPLETE",
    }

    def event_callback(event: dict[str, Any]) -> None:
        events.append(dict(event))
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def emergency_hold(_signal: int, _frame: Any) -> None:
        for arm in arms.values():
            try:
                arm.emergency_stop()
            except Exception:  # noqa: BLE001
                pass
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, emergency_hold)
    signal.signal(signal.SIGTERM, emergency_hold)

    try:
        arms["left"] = P7(side="left", interface_name=str(args.left_interface))
        arms["right"] = P7(side="right", interface_name=str(args.right_interface))
        result = run_celebration(
            arms["left"],
            arms["right"],
            loops=int(args.loops),
            event_callback=event_callback,
        )
        report.update(result)
        report["events"] = events
        report["verdict"] = "PASS"
    except BaseException as exc:
        report["verdict"] = "FAIL"
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for arm in arms.values():
            try:
                arm.close()
            except Exception:  # noqa: BLE001
                pass
        _write_report(output, report)

    print(json.dumps({"verdict": report["verdict"], "output": str(output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
