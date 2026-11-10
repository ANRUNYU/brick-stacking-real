"""Emit shadow PlanBundle + recorded ArmState for host_control_readiness.

Never raises control_ready, never opens CAN, never enables actuators.
trajectory_hash is computed from a validated offline contracts.Trajectory.
Arm device_id comes from audited config/history binding (left P7 default).
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

from brick_stacking.arm.device_binding import (  # noqa: E402
    emit_recorded_arm_state_payload,
    load_arm_device_binding,
)
from brick_stacking.planning.shadow_plan_bundle import (  # noqa: E402
    build_shadow_plan_bundle,
    load_json,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--diagnostic-permit",
        type=Path,
        default=None,
        help="m-diagnostic-permit-eligibility JSON (identity fields)",
    )
    p.add_argument(
        "--shadow",
        type=Path,
        default=None,
        help="pre_grasp shadow pipeline JSON (optional identity fallback)",
    )
    p.add_argument(
        "--arm-binding",
        type=Path,
        default=ROOT / "config/observed/arm_device_binding_left_p7_20261110.json",
        help="recorded arm device_id binding JSON",
    )
    p.add_argument(
        "--plan-bundle-output",
        type=Path,
        required=True,
        help="write shadow PlanBundle JSON",
    )
    p.add_argument(
        "--arm-state-output",
        type=Path,
        required=True,
        help="write recorded ArmState wrapper JSON (arm_state nested)",
    )
    args = p.parse_args(argv)

    plan = build_shadow_plan_bundle(
        diagnostic_permit=load_json(args.diagnostic_permit),
        shadow_report=load_json(args.shadow),
        diagnostic_path=(
            str(args.diagnostic_permit).replace("\\", "/") if args.diagnostic_permit else None
        ),
        shadow_path=str(args.shadow).replace("\\", "/") if args.shadow else None,
    )
    binding = load_arm_device_binding(args.arm_binding)
    arm_payload = emit_recorded_arm_state_payload(
        binding,
        binding_path=str(args.arm_binding).replace("\\", "/"),
    )

    # Hard invariants
    plan["control_ready"] = False
    plan["motion_enabled"] = False
    plan["executable"] = False
    arm_payload["control_ready"] = False
    arm_payload["motion_enabled"] = False
    arm_payload["can_opened"] = False

    args.plan_bundle_output.parent.mkdir(parents=True, exist_ok=True)
    args.arm_state_output.parent.mkdir(parents=True, exist_ok=True)
    args.plan_bundle_output.write_text(
        json.dumps(plan, indent=2) + "\n", encoding="utf-8"
    )
    args.arm_state_output.write_text(
        json.dumps(arm_payload, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "plan_bundle_schema": plan["schema_version"],
        "trajectory_hash": plan["trajectory_hash"],
        "plan_executable": False,
        "motion_enabled": False,
        "control_ready": False,
        "arm_device_id": arm_payload["device_id"],
        "arm_source": arm_payload["source"],
        "fresh_live_read": False,
        "can_opened": False,
        "plan_bundle_output": str(args.plan_bundle_output).replace("\\", "/"),
        "arm_state_output": str(args.arm_state_output).replace("\\", "/"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
