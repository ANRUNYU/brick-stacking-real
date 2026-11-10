"""Emit live-or-recorded ArmState envelope for host readiness.

Modes:
  recorded       — device_id binding only (INVALID; CAN not opened)
  fixture-valid  — structurally VALID recorded/mock fixture (not live)
  live-readonly  — best-effort ArmStateReader open+read (no motion / no Rest)

Never raises control_ready, never enables actuators, never sends motion.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from brick_stacking.arm.arm_state_validity import (  # noqa: E402
    build_fixture_valid_arm_state,
    classify_arm_state,
    emit_live_or_recorded_payload,
    try_live_readonly_arm_state,
)
from brick_stacking.arm.device_binding import (  # noqa: E402
    emit_recorded_arm_state_payload,
    load_arm_device_binding,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--mode",
        choices=("recorded", "fixture-valid", "live-readonly"),
        required=True,
        help="recorded binding | fixture VALID (not live) | live ArmStateReader probe",
    )
    p.add_argument(
        "--arm-binding",
        type=Path,
        default=ROOT / "config/observed/arm_device_binding_left_p7_20261110.json",
        help="recorded arm device_id binding JSON",
    )
    p.add_argument(
        "--role",
        choices=("left", "right"),
        default="left",
        help="arm role for fixture-valid / live-readonly",
    )
    p.add_argument(
        "--channel",
        default=None,
        help="override SocketCAN channel for live-readonly (default: audited)",
    )
    p.add_argument(
        "--fixture-source",
        choices=("recorded", "mock"),
        default="recorded",
        help="source label for fixture-valid (never real)",
    )
    p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="write arm-live-or-recorded JSON",
    )
    args = p.parse_args(argv)

    if args.mode == "recorded":
        binding = load_arm_device_binding(args.arm_binding)
        recorded = emit_recorded_arm_state_payload(
            binding,
            binding_path=str(args.arm_binding).replace("\\", "/"),
        )
        state = recorded["arm_state"]
        payload = emit_live_or_recorded_payload(
            mode="recorded",
            arm_state=state,
            binding_path=str(args.arm_binding).replace("\\", "/"),
            can_opened=False,
            fresh_live_read=False,
            extra_notes=list(recorded.get("notes") or []),
        )
    elif args.mode == "fixture-valid":
        state = build_fixture_valid_arm_state(
            role=args.role,
            source=args.fixture_source,
        )
        payload = emit_live_or_recorded_payload(
            mode="fixture-valid",
            arm_state=state,
            binding_path=str(args.arm_binding).replace("\\", "/"),
            can_opened=False,
            fresh_live_read=False,
            extra_notes=[
                "fixture-valid is for Mock/recorded software-path verification only.",
                "counts_as_live_valid remains false because source is not real.",
            ],
        )
    else:
        live = try_live_readonly_arm_state(role=args.role, channel=args.channel)
        if live.get("arm_state") is not None:
            payload = emit_live_or_recorded_payload(
                mode="live-readonly",
                arm_state=live["arm_state"],
                classification=live.get("classification"),
                can_opened=bool(live.get("can_opened")),
                fresh_live_read=bool(live.get("fresh_live_read")),
                extra_notes=[
                    "live-readonly used ArmStateReader only (position/mode READ).",
                    "No Rest, enable, target, or Flash write.",
                ],
            )
            payload["live_readonly_error"] = live.get("error")
        else:
            payload = {
                "schema_version": live["schema_version"],
                "kind": "arm_live_or_recorded",
                "mode": "live-readonly",
                "arm_state": None,
                "device_id": None,
                "source": None,
                "validity": None,
                "fresh_live_read": False,
                "can_opened": bool(live.get("can_opened")),
                "motion_enabled": False,
                "control_ready": False,
                "classification": live.get("classification")
                or classify_arm_state(None),
                "counts_as_live_valid": False,
                "counts_as_recorded_binding": False,
                "live_readonly_error": live.get("error"),
                "arm_state_reader_live_hold": live.get("arm_state_reader_live_hold"),
                "notes": [
                    "live-readonly probe failed soft; see live_readonly_error.",
                    "Never raises control_ready; never enables motion.",
                ],
            }

    # Hard invariants
    payload["control_ready"] = False
    payload["motion_enabled"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    classification = payload.get("classification") or {}
    summary = {
        "mode": payload.get("mode"),
        "source": payload.get("source"),
        "validity": payload.get("validity"),
        "device_id": payload.get("device_id"),
        "fresh_live_read": payload.get("fresh_live_read"),
        "can_opened": payload.get("can_opened"),
        "counts_as_live_valid": payload.get("counts_as_live_valid"),
        "counts_as_recorded_binding": payload.get("counts_as_recorded_binding"),
        "blockers": list(classification.get("blockers") or []),
        "control_ready": False,
        "motion_enabled": False,
        "live_readonly_error": payload.get("live_readonly_error"),
        "output": str(args.output).replace("\\", "/"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
