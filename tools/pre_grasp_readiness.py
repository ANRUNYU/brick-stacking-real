"""Report pre_grasp gate gaps and grasp-entry readiness.

Never raises control_ready, never emits permit/motion/CAN. Outputs what is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from brick_stacking.planning.pre_grasp_gates import (  # noqa: E402
    evidence_gap_report,
    evaluate_pre_grasp_readiness,
    load_json,
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--request",
        type=Path,
        default=ROOT / "config/planning/first_placement_review_request.adopted.json",
    )
    p.add_argument(
        "--shadow",
        type=Path,
        default=None,
        help="slot_shadow_pipeline JSON (optional but recommended)",
    )
    p.add_argument(
        "--association-record",
        type=Path,
        default=None,
        help="association-confirm-switch JSON from tools/association_confirm_switch.py",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--gaps-only",
        action="store_true",
        help="write compact evidence-gap report instead of full readiness",
    )
    args = p.parse_args(argv)

    request = load_json(args.request)
    shadow = load_json(args.shadow) if args.shadow else None
    association = load_json(args.association_record) if args.association_record else None
    report = evaluate_pre_grasp_readiness(
        request=request,
        shadow_report=shadow,
        association_record=association,
        request_path=str(args.request).replace("\\", "/"),
        shadow_path=str(args.shadow).replace("\\", "/") if args.shadow else None,
        association_path=(
            str(args.association_record).replace("\\", "/") if args.association_record else None
        ),
    )
    payload = evidence_gap_report(report) if args.gaps_only else report.to_dict()
    # Hard invariants for any output shape.
    payload["control_ready"] = False
    payload["motion_enabled"] = False
    payload["permit"] = None
    payload["formal_grasp_entry_allowed"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    blocking = []
    if args.gaps_only:
        blocking = [g["gate_id"] for g in payload.get("blocking_gaps") or []]
    else:
        blocking = [
            g["gate_id"]
            for g in payload.get("gates") or []
            if g.get("blocking_for_formal_grasp") and g.get("status") != "PASS"
        ]
    print(
        json.dumps(
            {
                "output": str(args.output).replace("\\", "/"),
                "formal_grasp_entry_allowed": False,
                "evidence_gates_clear": payload.get("evidence_gates_clear"),
                "blocking_gates": blocking,
                "control_ready": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
