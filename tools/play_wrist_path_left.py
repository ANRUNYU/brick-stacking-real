"""Play a left-arm wrist-path-0.1 (default dry-run; no finger commands).

Dry-run (default):
  python tools/play_wrist_path_left.py \\
    docs/team/P/evidence/wrist_path_layer1_grasp_to_place_20261111_215245.json \\
    --expected-sha256-lf 349adb65352c820dc13ece77da26b575b269ab31af821244ec60e426758d16a3 \\
    --assume-at-path-start \\
    --output docs/team/P/evidence/wrist_path_player_dryrun_<ts>.json

Future authorized live empty-run (NOT this PR's job; both flags required):
  python tools/play_wrist_path_left.py PATH \\
    --expected-sha256-lf <lf-sha> \\
    --enable-live-motion \\
    --authorization-ref <field-auth-id> \\
    --output <report.json>

Live backend is linkerbot.P7.move_j([J1..J7]) coordinated seven-axis — never
host_monitor single-joint MOVE, never O6/hand, never Rest, never right arm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from brick_stacking.wrist_handoff.wrist_path_player import (
    MOTION_BACKEND_KIND,
    build_linkerbot_p7_move_j_backend,
    evaluate_live_authorization,
    parse_q_rad_from_state,
    play_wrist_path,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("wrist_path", type=Path, help="wrist-path-0.1 JSON")
    p.add_argument(
        "--expected-sha256-lf",
        default=None,
        help="optional LF-normalized file SHA-256 gate",
    )
    p.add_argument(
        "--urdf",
        type=Path,
        default=Path("config/models/p7_left/p7__left.urdf"),
        help="locked left P7 URDF",
    )
    p.add_argument(
        "--current-q-json",
        type=Path,
        default=None,
        help="JSON list[7] or host_monitor-like snapshot with arms.left.q_rad",
    )
    p.add_argument(
        "--assume-at-path-start",
        action="store_true",
        help="dry-run only: treat path grasp_ready seed as current pose",
    )
    p.add_argument(
        "--enable-live-motion",
        action="store_true",
        help="explicit live dispatch (default OFF); also needs --authorization-ref",
    )
    p.add_argument(
        "--authorization-ref",
        default="",
        help="non-empty field authorization id required for live",
    )
    p.add_argument(
        "--interface",
        default="can2",
        help="left-arm CAN interface for live P7 backend only",
    )
    p.add_argument(
        "--linkerbot-src",
        default=None,
        help="optional path containing linkerbot package (live only)",
    )
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)

    current_q = None
    if args.current_q_json is not None:
        state = json.loads(args.current_q_json.read_text(encoding="utf-8-sig"))
        try:
            current_q = list(parse_q_rad_from_state(state))
        except ValueError as exc:
            payload = {
                "schema_version": "wrist-path-left-player-0.1",
                "verdict": "REFUSE_CURRENT_Q",
                "blocked_by": [str(exc)],
                "finger_commands_issued": False,
                "motion_started": False,
                "notes": [
                    "Readonly host_monitor may leave J6/J7 null; refuse inventing wrist angles.",
                ],
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"verdict": payload["verdict"], "output": str(args.output)}))
            return 2

    live_gate = evaluate_live_authorization(
        enable_live_motion=bool(args.enable_live_motion),
        authorization_ref=str(args.authorization_ref),
    )

    arm_factory = None
    if live_gate["live_dispatch_allowed"]:
        # Factory runs inside play_wrist_path only after static validation passes.
        # Still no hand / Rest / right arm.
        def arm_factory():
            return build_linkerbot_p7_move_j_backend(
                side="left",
                interface_name=str(args.interface),
                linkerbot_src=args.linkerbot_src,
            )

    report = play_wrist_path(
        path_file=args.wrist_path,
        expected_sha256_lf=args.expected_sha256_lf,
        urdf_path=args.urdf,
        current_q_rad=current_q,
        assume_at_path_start=bool(args.assume_at_path_start),
        enable_live_motion=bool(args.enable_live_motion),
        authorization_ref=str(args.authorization_ref),
        arm_factory=arm_factory,
    )

    report.setdefault("cli", {})
    report["cli"] = {
        "enable_live_motion": bool(args.enable_live_motion),
        "authorization_ref_present": bool(str(args.authorization_ref).strip()),
        "motion_backend_kind": MOTION_BACKEND_KIND,
        "dry_run_default": not bool(args.enable_live_motion),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "verdict": report.get("verdict"),
                "motion_started": report.get("motion_started"),
                "finger_commands_issued": report.get("finger_commands_issued"),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    verdict = str(report.get("verdict") or "")
    if verdict in {"DRY_RUN_OK", "LIVE_PLAY_OK"}:
        return 0
    if verdict.startswith("REFUSE") or verdict.startswith("DRY_RUN_NEED"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
