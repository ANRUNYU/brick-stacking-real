"""Report pre_grasp gate gaps and grasp-entry readiness.

Never raises control_ready, never emits *live* permit/motion/CAN.
When evidence gates clear, may set permit_eligible=true and write a diagnostic
(shadow) eligibility record — not a contracts.Permit.
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
    p.add_argument(
        "--diagnostic-permit-output",
        type=Path,
        default=None,
        help="optional path to write diagnostic (shadow) permit-eligibility JSON alone",
    )
    p.add_argument(
        "--plan-bundle",
        type=Path,
        default=None,
        help="optional shadow PlanBundle JSON (updates diagnostic trajectory_hash status only)",
    )
    p.add_argument(
        "--arm-state",
        type=Path,
        default=None,
        help="optional recorded/mock ArmState JSON (updates diagnostic device_id status; ≠ live VALID)",
    )
    args = p.parse_args(argv)

    request = load_json(args.request)
    shadow = load_json(args.shadow) if args.shadow else None
    association = load_json(args.association_record) if args.association_record else None
    plan_bundle = load_json(args.plan_bundle) if args.plan_bundle else None
    arm_state = load_json(args.arm_state) if args.arm_state else None
    report = evaluate_pre_grasp_readiness(
        request=request,
        shadow_report=shadow,
        association_record=association,
        request_path=str(args.request).replace("\\", "/"),
        shadow_path=str(args.shadow).replace("\\", "/") if args.shadow else None,
        association_path=(
            str(args.association_record).replace("\\", "/") if args.association_record else None
        ),
        plan_bundle=plan_bundle,
        arm_state_payload=arm_state,
        plan_bundle_path=(
            str(args.plan_bundle).replace("\\", "/") if args.plan_bundle else None
        ),
        arm_state_path=str(args.arm_state).replace("\\", "/") if args.arm_state else None,
    )
    payload = evidence_gap_report(report) if args.gaps_only else report.to_dict()
    # Hard invariants for any output shape: never forge formal entry / motion / live permit.
    payload["control_ready"] = False
    payload["motion_enabled"] = False
    payload["permit"] = None
    payload["formal_grasp_entry_allowed"] = False
    payload["vision_pre_grasp_ready"] = bool(report.vision_pre_grasp_ready)
    payload["evidence_gates_clear"] = bool(report.evidence_gates_clear)
    payload["permit_eligible"] = bool(report.permit_eligible)
    payload["diagnostic_permit"] = report.diagnostic_permit
    payload["permit_hold_reason"] = report.permit_hold_reason
    payload["awaiting_m_permit"] = bool(report.awaiting_m_permit)
    payload["awaiting_live_permit_host_enable"] = bool(report.awaiting_live_permit_host_enable)
    payload["awaiting_actuator_enable"] = bool(report.awaiting_actuator_enable)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.diagnostic_permit_output is not None and report.diagnostic_permit is not None:
        args.diagnostic_permit_output.parent.mkdir(parents=True, exist_ok=True)
        args.diagnostic_permit_output.write_text(
            json.dumps(report.diagnostic_permit, indent=2) + "\n",
            encoding="utf-8",
        )

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
                "vision_pre_grasp_ready": payload.get("vision_pre_grasp_ready"),
                "evidence_gates_clear": payload.get("evidence_gates_clear"),
                "permit_eligible": payload.get("permit_eligible"),
                "permit": None,
                "permit_hold_reason": payload.get("permit_hold_reason"),
                "awaiting_m_permit": payload.get("awaiting_m_permit"),
                "awaiting_live_permit_host_enable": payload.get(
                    "awaiting_live_permit_host_enable"
                ),
                "awaiting_actuator_enable": payload.get("awaiting_actuator_enable"),
                "blocking_gates": blocking,
                "control_ready": False,
                "diagnostic_permit_output": (
                    str(args.diagnostic_permit_output).replace("\\", "/")
                    if args.diagnostic_permit_output
                    else None
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
