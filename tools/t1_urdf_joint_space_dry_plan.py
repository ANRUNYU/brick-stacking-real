#!/usr/bin/env python3
"""Offline T1 URDF-gated joint-space dry-plan (no CAN / no motion / not H3)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brick_stacking.execution.t1_bounded_live_runner import (  # noqa: E402
    build_t1_urdf_joint_space_dry_plan,
    evaluate_t1_prerequisites,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rest-capture",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/left_supported_rest_20261111_011818.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/t1_urdf_joint_space_dry_plan_20261111.json",
    )
    parser.add_argument("--joints", default="1,2,3")
    parser.add_argument("--step-deg", type=float, default=1.0)
    args = parser.parse_args()

    rest = json.loads(args.rest_capture.read_text(encoding="utf-8"))
    joints = tuple(int(x) for x in args.joints.split(",") if x.strip())
    prereq = evaluate_t1_prerequisites(rest_capture=rest, urdf_available=True)
    plan = build_t1_urdf_joint_space_dry_plan(
        rest_capture=rest,
        joints=joints,
        step_deg=args.step_deg,
        prerequisites=prereq,
        repo_root=ROOT,
    )
    payload = {
        "schema_version": "t1-urdf-joint-space-dry-plan-evidence-0.1",
        "generated_by": "tools/t1_urdf_joint_space_dry_plan.py",
        "rest_capture_path": str(args.rest_capture.as_posix()),
        "live_motion_run": False,
        "control_ready": False,
        "not_h3": True,
        "plan": plan,
        "notes": [
            "Offline only; uses locked p7__left.urdf declared limits instead of synthetic ±2.5.",
            "Does not claim FK/IK live wiring or wrist theta verified.",
            "T1 joint-space subset; not whole PlanBundle empty run.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"wrote": str(args.output), "waypoint_count": plan["waypoint_count"],
                      "executable": plan["executable"], "urdf_sha256": plan["urdf_sha256"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
