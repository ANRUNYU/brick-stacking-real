"""Report host/safety gate ladder and control_ready / motion_enabled gaps.

Gate ladder:
  vision_pre_grasp_ready → dry_run_grasp_entry_ready →
  formal_grasp_entry_allowed → control_ready (operator policy attest gated)

Default: control_ready stays false; attest switch is not auto-opened.
Never invents live Permit, never enables actuators, never sends CAN.
Optional --probe-dry-run-arm-disabled exercises OfflineSafetyGate + MockArm only.
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

from brick_stacking.execution.host_control_readiness import (  # noqa: E402
    evaluate_host_control_readiness,
)


def load_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--pre-grasp-gaps",
        type=Path,
        default=None,
        help="pre_grasp gaps/readiness JSON (vision_pre_grasp_ready, permit_eligible, …)",
    )
    p.add_argument(
        "--diagnostic-permit",
        type=Path,
        default=None,
        help="optional m-diagnostic-permit-eligibility JSON",
    )
    p.add_argument(
        "--plan-bundle",
        type=Path,
        default=None,
        help="optional PlanBundle JSON with trajectory_hash (do not invent)",
    )
    p.add_argument(
        "--arm-state",
        type=Path,
        default=None,
        help="optional ArmState JSON (device_id); camera SN is not accepted as arm id",
    )
    p.add_argument(
        "--live-permit",
        type=Path,
        default=None,
        help="optional live contracts.Permit JSON (validated; never invented here)",
    )
    p.add_argument(
        "--host-monitor-snapshot",
        type=Path,
        default=None,
        help="optional host_monitor control snapshot (motion_process_enabled/session_open)",
    )
    p.add_argument(
        "--operator-policy-attest",
        type=Path,
        default=None,
        help=(
            "optional host-control-ready-policy-attest JSON "
            "(default closed; do not auto-open)"
        ),
    )
    p.add_argument(
        "--probe-dry-run-arm-disabled",
        action="store_true",
        help="probe Offline dry-run / MockArm path (hardware_enabled=False; no CAN)",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "offline_task.yaml",
        help="offline dry_run config for probe (default: config/offline_task.yaml)",
    )
    p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="write host-control-readiness JSON",
    )
    args = p.parse_args(argv)

    report = evaluate_host_control_readiness(
        pre_grasp_gaps=load_json(args.pre_grasp_gaps),
        diagnostic_permit=load_json(args.diagnostic_permit),
        plan_bundle=load_json(args.plan_bundle),
        arm_state=load_json(args.arm_state),
        live_permit=load_json(args.live_permit),
        host_monitor_snapshot=load_json(args.host_monitor_snapshot),
        operator_policy_attest=args.operator_policy_attest,
        config_path=args.config,
        probe_dry_run=bool(args.probe_dry_run_arm_disabled),
    )
    payload = report.to_dict()
    # Belt-and-suspenders: motion never enabled; live_permit never echoed.
    payload["motion_enabled"] = False
    payload["live_permit"] = None

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    ladder = payload.get("gate_ladder") or {}
    summary = {
        "schema_version": payload["schema_version"],
        "gate_ladder": {
            "vision_pre_grasp_ready": ladder.get("vision_pre_grasp_ready"),
            "dry_run_grasp_entry_ready": ladder.get("dry_run_grasp_entry_ready"),
            "formal_grasp_entry_allowed": ladder.get("formal_grasp_entry_allowed"),
            "control_ready": ladder.get("control_ready"),
            "can_enter_formal_grasp": ladder.get("can_enter_formal_grasp"),
            "formal_grasp_entry_missing": list(ladder.get("formal_grasp_entry_missing") or []),
            "control_ready_missing": list(ladder.get("control_ready_missing") or []),
        },
        "dry_run_grasp_entry_ready": payload.get("dry_run_grasp_entry_ready"),
        "formal_grasp_entry_allowed": payload.get("formal_grasp_entry_allowed"),
        "formal_grasp_ready": payload.get("formal_grasp_ready"),
        "control_ready": payload.get("control_ready"),
        "motion_enabled": False,
        "operator_policy_attest_attested": (
            (payload.get("operator_policy_attest") or {}).get("attested")
        ),
        "only_operator_enable_remaining": payload["only_operator_enable_remaining"],
        "needs_operator_physical_enable_now": payload[
            "needs_operator_physical_enable_now"
        ],
        "needs_operator_physical_enable_before_real_motion": payload[
            "needs_operator_physical_enable_before_real_motion"
        ],
        "vision_pre_grasp_ready": payload.get("vision_pre_grasp_ready"),
        "permit_eligible": payload.get("permit_eligible"),
        "missing_software": list(payload.get("missing_software") or []),
        "missing_field_or_operator": list(payload.get("missing_field_or_operator") or []),
        "hard_blocker_ids": [b["id"] for b in payload.get("hard_blockers") or []],
        "dry_run_arm_disabled_reachable": (
            (payload.get("dry_run_arm_disabled") or {}).get("reachable")
            if payload.get("dry_run_arm_disabled")
            else None
        ),
        "dry_run_issuance": (
            {
                "executable": (
                    ((payload.get("dry_run_arm_disabled") or {}).get("issuance_diagnostic") or {}).get(
                        "executable"
                    )
                ),
                "issuance_fields_complete": (
                    ((payload.get("dry_run_arm_disabled") or {}).get("issuance_diagnostic") or {}).get(
                        "issuance_fields_complete"
                    )
                ),
                "still_missing_fields": list(
                    ((payload.get("dry_run_arm_disabled") or {}).get("issuance_diagnostic") or {}).get(
                        "still_missing_fields"
                    )
                    or []
                ),
                "only_hardware_enable_and_policy_remaining": (
                    ((payload.get("dry_run_arm_disabled") or {}).get("issuance_diagnostic") or {}).get(
                        "only_hardware_enable_and_policy_remaining"
                    )
                ),
                "plumbing_ok": (
                    (
                        ((payload.get("dry_run_arm_disabled") or {}).get("issuance_diagnostic") or {})
                        .get("plumbing_self_check")
                        or {}
                    ).get("gate_accepts_complete_dry_run_permit")
                ),
            }
            if payload.get("dry_run_arm_disabled")
            else None
        ),
        "output": str(args.output).replace("\\", "/"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
