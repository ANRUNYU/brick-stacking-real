"""Offline: Rest capture → sdk-report angles + rest-draft attempt + T1 status.

Never opens CAN / never sends Rest / never enables motion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brick_stacking.arm.rest_state_capture import (  # noqa: E402
    attempt_rest_draft_or_gap,
)
from brick_stacking.execution.t1_bounded_live_runner import (  # noqa: E402
    summarize_t1_status,
)


def main() -> int:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--rest-capture", type=Path, required=True)
    p.add_argument("--range-profile", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--rest-state-capture", action="store_true")
    p.add_argument("--attest-rest-for-pregrasp", action="store_true")
    p.add_argument("--urdf-available", action="store_true")
    p.add_argument("--role", default="left", choices=("left", "right"))
    args = p.parse_args()

    rest_capture = json.loads(args.rest_capture.read_text(encoding="utf-8"))
    range_profile = json.loads(args.range_profile.read_text(encoding="utf-8"))
    attempt = attempt_rest_draft_or_gap(
        rest_capture,
        range_profile=range_profile,
        rest_state_capture=bool(args.rest_state_capture),
        attest_rest_for_pregrasp=bool(args.attest_rest_for_pregrasp),
        role=args.role,
    )
    status = summarize_t1_status(
        rest_capture=rest_capture,
        rest_draft_attempt=attempt,
        range_profile=range_profile,
        urdf_available=bool(args.urdf_available),
    )
    payload = {
        "schema_version": "t1-rest-draft-status-0.1",
        "rest_capture_path": str(args.rest_capture),
        "range_profile_path": str(args.range_profile),
        "rest_draft_attempt": attempt,
        "t1_status": status,
        "control_ready": False,
        "motion_enabled": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": attempt.get("verdict"),
                "pass": attempt.get("pass"),
                "error": attempt.get("error"),
                "subset_dry_plan_allowed": status["prerequisites"]["subset_dry_plan_allowed"],
                "live_motion_allowed": status["prerequisites"]["live_motion_allowed"],
                "blocked_by": status["prerequisites"]["blocked_by"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if attempt.get("pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
