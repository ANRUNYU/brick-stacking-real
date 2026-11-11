"""One-shot audit rerun: default vs dual Rest attest formal entry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / "src"))

from brick_stacking.arm.rest_state_capture import build_live_valid_draft_from_rest
from brick_stacking.execution.host_control_readiness import evaluate_host_control_readiness

OUT = Path(__file__).resolve().parent


def _mock_rest_capture() -> dict:
    received = []
    for mid, q in zip(range(61, 66), (0.01, 0.02, 0.03, 0.04, 0.05), strict=True):
        received.append(
            {
                "motor_id": mid,
                "position_sdk_rad": q,
                "host_receive_monotonic_s": float(mid - 61),
            }
        )
    for mid, u16 in ((66, 32767), (67, 32767)):
        received.append(
            {
                "motor_id": mid,
                "position_raw_u16": u16,
                "status": 0,
                "fault": 0,
                "host_receive_monotonic_s": float(mid - 61),
                "raw_hex": (
                    bytes([0]) + int(u16).to_bytes(2, "big") + bytes(5)
                ).hex(),
            }
        )
    return {
        "schema_version": "c-left-supported-rest-1",
        "source": "real",
        "arm_role": "left",
        "interface": "can2",
        "status": "RAW_SEVEN_AXIS_CAPTURED",
        "clock_domain": "host_monotonic",
        "epoch": "linux_boot:audit-rerun",
        "authorization_ref": "audit-rerun-mock-only",
        "received": received,
    }


def _mock_range_profile() -> dict:
    return {
        "66": {
            "verified": True,
            "evidence": "audit-rerun-synthetic",
            "units": "rad",
            "theta_min_rad": 0.0,
            "theta_max_rad": 1.0,
        },
        "67": {
            "verified": True,
            "evidence": "audit-rerun-synthetic",
            "units": "rad",
            "theta_min_rad": 0.0,
            "theta_max_rad": 1.0,
        },
    }


def main() -> None:
    draft = build_live_valid_draft_from_rest(
        _mock_rest_capture(),
        rest_state_capture=True,
        attest_rest_for_pregrasp=True,
        range_profile=_mock_range_profile(),
    )
    (OUT / "rest_attested_arm_state_draft.json").write_text(
        json.dumps(draft, indent=2) + "\n", encoding="utf-8"
    )

    gaps = json.loads(
        (ROOT / "docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json").read_text(
            encoding="utf-8"
        )
    )
    diag = json.loads(
        (
            ROOT
            / "docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json"
        ).read_text(encoding="utf-8")
    )
    plan = json.loads(
        (
            ROOT / "docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json"
        ).read_text(encoding="utf-8")
    )
    recorded = json.loads(
        (
            ROOT
            / "docs/team/B/evidence/field_20261110/recorded_arm_state_left_p7_20261110.json"
        ).read_text(encoding="utf-8")
    )

    r0 = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=recorded,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
        rest_state_capture=False,
        attest_rest_for_pregrasp=False,
    ).to_dict()
    r1 = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=draft["arm_state"],
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
        rest_state_capture=True,
        attest_rest_for_pregrasp=True,
    ).to_dict()
    for r in (r0, r1):
        r["control_ready"] = False
        r["motion_enabled"] = False
        r["live_permit"] = None

    (OUT / "host_control_api_dual_rest_draft.json").write_text(
        json.dumps(r1, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "default": {
            "formal_grasp_entry_allowed": r0["formal_grasp_entry_allowed"],
            "control_ready": r0["control_ready"],
            "blocked_by": r0.get("formal_grasp_blocked_by"),
            "live_arm_via": (r0.get("gate_ladder") or {}).get("live_arm_via"),
            "live_permit_path_status": (r0.get("live_permit_path") or {}).get("status"),
        },
        "dual_rest_attest_with_rest_draft": {
            "formal_grasp_entry_allowed": r1["formal_grasp_entry_allowed"],
            "control_ready": r1["control_ready"],
            "blocked_by": r1.get("formal_grasp_blocked_by"),
            "live_arm_via": (r1.get("gate_ladder") or {}).get("live_arm_via"),
            "dry_run_grasp_entry_ready": r1.get("dry_run_grasp_entry_ready"),
            "can_enter_formal_grasp": (r1.get("gate_ladder") or {}).get(
                "can_enter_formal_grasp"
            ),
            "live_permit_path_status": (r1.get("live_permit_path") or {}).get("status"),
            "live_permit_executable": (r1.get("live_permit_path") or {}).get(
                "executable"
            ),
            "control_ready_missing": (r1.get("gate_ladder") or {}).get(
                "control_ready_missing"
            ),
            "how_to_open_gates": [
                "--rest-state-capture / BRICK_STACKING_REST_STATE_CAPTURE",
                "--attest-rest-for-pregrasp / BRICK_STACKING_ATTEST_REST_FOR_PREGRASP",
                "structurally live VALID Rest draft as arm_state (Mock/shadow)",
                "dry-run ready evidence chain (pre_grasp_gaps + plan_bundle + probe)",
            ],
        },
        "note": "Rest draft here is Mock/synthetic for audit; real Rest risks wrist loss-of-hold",
    }
    (OUT / "formal_entry_rerun_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
