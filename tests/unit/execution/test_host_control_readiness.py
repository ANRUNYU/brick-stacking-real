"""Host/safety gate ladder: dry-run ready vs formal entry vs control_ready."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

from brick_stacking.execution.host_control_readiness import (
    evaluate_host_control_readiness,
    probe_dry_run_arm_disabled,
)
from brick_stacking.execution.host_policy_attest import build_host_policy_attest

ROOT = Path(__file__).resolve().parents[3]
GAPS = (
    ROOT
    / "docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json"
)
DIAG = (
    ROOT
    / "docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json"
)
PLAN = (
    ROOT
    / "docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json"
)
ARM = (
    ROOT
    / "docs/team/B/evidence/field_20261110/recorded_arm_state_left_p7_20261110.json"
)
ATTEST = (
    ROOT
    / "config/observed/host_control_ready_policy_attest_20261110.json"
)


def test_probe_dry_run_arm_disabled_no_can_no_control_ready():
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    probe = probe_dry_run_arm_disabled(
        config_path=ROOT / "config/offline_task.yaml",
        diagnostic_permit=diag,
    )
    assert probe["reachable"] is True
    assert probe["mock_arm"]["hardware_enabled"] is False
    assert probe["mock_arm"]["backend"] == "mock"
    assert probe["step_without_permit_rejected"] is True
    assert probe["control_ready"] is False
    assert probe["motion_enabled"] is False
    assert probe["commands_sent"] == 0
    assert probe["can_opened"] is False
    issuance = probe["issuance_diagnostic"]
    assert issuance["executable"] is False
    assert issuance["live_permit"] is None
    assert issuance["issuance_attempted"] is True
    assert issuance["issuance_fields_complete"] is False
    assert "trajectory_hash" in issuance["still_missing_fields"]
    assert issuance["plumbing_self_check"]["gate_accepts_complete_dry_run_permit"] is True


def test_probe_with_plan_bundle_fields_complete():
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    probe = probe_dry_run_arm_disabled(
        config_path=ROOT / "config/offline_task.yaml",
        diagnostic_permit=diag,
        plan_bundle=plan,
    )
    issuance = probe["issuance_diagnostic"]
    assert probe["reachable"] is True
    assert issuance["issuance_fields_complete"] is True
    assert issuance["gate_accepts_draft"] is True
    assert issuance["executable"] is False
    assert issuance["live_permit"] is None
    assert issuance["only_hardware_enable_and_policy_remaining"] is True
    assert issuance["still_missing_fields"] == []
    assert issuance["draft_permit"]["trajectory_hash"] == plan["trajectory_hash"]


def test_field_gaps_without_plan_still_block():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
    )
    payload = report.to_dict()
    assert payload["control_ready"] is False
    assert payload["live_permit"] is None
    assert payload["dry_run_grasp_entry_ready"] is False
    assert payload["formal_grasp_entry_allowed"] is False
    assert payload["only_operator_enable_remaining"] is False
    assert "plan_bundle_trajectory_hash" in payload["missing_software"]
    assert "arm_state_device_id" in payload["missing_software"]
    assert payload["dry_run_arm_disabled"]["reachable"] is True
    by_id = {item.id: item for item in report.checklist}
    assert by_id["dry_run_safety_gate_issuance"].status == "PROBED"


def test_field_evidence_dry_run_ready_but_not_formal():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    arm = json.loads(ARM.read_text(encoding="utf-8"))
    attest = json.loads(ATTEST.read_text(encoding="utf-8"))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=arm,
        operator_policy_attest=attest,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
    )
    payload = report.to_dict()
    assert payload["schema_version"] == "host-control-readiness-0.2"
    assert payload["vision_pre_grasp_ready"] is True
    assert payload["dry_run_grasp_entry_ready"] is True
    assert payload["formal_grasp_entry_allowed"] is False
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
    assert payload["formal_grasp_ready"] is False
    assert payload["live_permit"] is None
    assert payload["operator_policy_attest"]["attested"] is False
    assert payload["only_operator_enable_remaining"] is False
    assert payload["needs_operator_physical_enable_now"] is False
    assert "plan_bundle_trajectory_hash" not in payload["missing_software"]
    assert "arm_state_device_id" not in payload["missing_software"]
    assert "live_permit" in payload["missing_field_or_operator"]
    assert "operator_policy_attest_control_ready" in payload["missing_field_or_operator"]
    assert "host_policy_control_ready" in payload["missing_field_or_operator"]
    ladder = payload["gate_ladder"]
    assert ladder["vision_pre_grasp_ready"] is True
    assert ladder["dry_run_grasp_entry_ready"] is True
    assert ladder["formal_grasp_entry_allowed"] is False
    assert ladder["control_ready"] is False
    assert ladder["can_enter_formal_grasp"] is False
    assert "live_contracts_Permit_validated" in ladder["formal_grasp_entry_missing"]
    assert "live_VALID_ArmState_source_real" in ladder["formal_grasp_entry_missing"]
    assert "operator_policy_attest_control_ready" in ladder["control_ready_missing"]
    issuance = payload["dry_run_arm_disabled"]["issuance_diagnostic"]
    assert issuance["issuance_fields_complete"] is True
    assert issuance["only_hardware_enable_and_policy_remaining"] is True
    assert issuance["executable"] is False
    by_id = {item.id: item for item in report.checklist}
    assert by_id["plan_bundle_trajectory_hash"].status == "PASS"
    assert by_id["arm_state_device_id"].status == "PASS"
    assert by_id["live_valid_arm_state"].status == "MISSING"
    assert by_id["live_permit"].status == "MISSING"
    assert by_id["dry_run_safety_gate_issuance"].status == "PASS"
    assert by_id["dry_run_grasp_entry_ready"].status == "PASS"
    assert by_id["formal_grasp_entry_gate"].status == "POLICY_HOLD"
    assert by_id["operator_policy_attest_control_ready"].status == "POLICY_HOLD"
    assert by_id["host_policy_control_ready"].status == "POLICY_HOLD"


def test_refuses_spurious_live_permit_without_live_arm():
    report = evaluate_host_control_readiness(
        pre_grasp_gaps={"vision_pre_grasp_ready": True, "permit_eligible": True},
        live_permit={"device_id": "should-not-count"},
        arm_state={"device_id": "mock", "source": "recorded"},
    )
    by_id = {item.id: item for item in report.checklist}
    assert by_id["live_permit"].status == "FAIL"
    assert report.to_dict()["control_ready"] is False
    assert report.to_dict()["formal_grasp_entry_allowed"] is False
    assert report.to_dict()["live_permit"] is None


def test_attest_open_without_formal_still_holds_control_ready():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    arm = json.loads(ARM.read_text(encoding="utf-8"))
    open_attest = build_host_policy_attest(
        operator="test-op",
        evidence_ref="tests/unit/execution/test_host_control_readiness.py",
        attested=True,
        notes="test only — must not raise without formal entry",
    )
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=arm,
        operator_policy_attest=open_attest,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
    )
    payload = report.to_dict()
    assert payload["dry_run_grasp_entry_ready"] is True
    assert payload["formal_grasp_entry_allowed"] is False
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
    assert payload["operator_policy_attest"]["attested"] is True
    assert payload["gate_ladder"]["reporter_never_raises_control_ready"] is True
    assert payload["gate_ladder"]["control_ready_prerequisites_met"] is False
    assert "reporter_hard_hold_no_large_motion_elevation" in payload["gate_ladder"][
        "control_ready_missing"
    ]
    by_id = {item.id: item for item in report.checklist}
    # Attest open clears the attest prerequisite item, but reporter still holds control_ready.
    assert by_id["operator_policy_attest_control_ready"].status == "PASS"
    assert by_id["host_policy_control_ready"].status == "POLICY_HOLD"


def test_cli_writes_report(tmp_path):
    out = tmp_path / "host_ready.json"
    mod = runpy.run_path(str(ROOT / "tools/host_control_readiness.py"))
    rc = mod["main"](
        [
            "--pre-grasp-gaps",
            str(GAPS),
            "--diagnostic-permit",
            str(DIAG),
            "--plan-bundle",
            str(PLAN),
            "--arm-state",
            str(ARM),
            "--operator-policy-attest",
            str(ATTEST),
            "--probe-dry-run-arm-disabled",
            "--config",
            str(ROOT / "config/offline_task.yaml"),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "host-control-readiness-0.2"
    assert payload["vision_pre_grasp_ready"] is True
    assert payload["dry_run_grasp_entry_ready"] is True
    assert payload["formal_grasp_entry_allowed"] is False
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
    assert payload["only_operator_enable_remaining"] is False
    assert payload["gate_ladder"]["can_enter_formal_grasp"] is False
    assert payload["dry_run_arm_disabled"]["reachable"] is True
    assert payload["dry_run_arm_disabled"]["issuance_diagnostic"]["executable"] is False
    assert payload["dry_run_arm_disabled"]["issuance_diagnostic"][
        "issuance_fields_complete"
    ] is True
    assert payload["formal_grasp_ready"] is False


def test_policy_attest_cli_default_closed(tmp_path):
    out = tmp_path / "attest.json"
    mod = runpy.run_path(str(ROOT / "tools/host_control_ready_policy_attest.py"))
    rc = mod["main"](
        [
            "--operator",
            "test",
            "--evidence-ref",
            "docs/team/B/HOST_CONTROL_READY_20261110.md",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["attested"] is False
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
