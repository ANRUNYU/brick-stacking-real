"""Shadow PlanBundle + recorded arm binding for host checklist wiring."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

from brick_stacking.arm.adapter import trajectory_hash
from brick_stacking.arm.device_binding import (
    emit_recorded_arm_state_payload,
    format_arm_device_id,
    load_arm_device_binding,
)
from brick_stacking.arm.state import ENDPOINTS
from brick_stacking.execution.host_control_readiness import evaluate_host_control_readiness
from brick_stacking.planning.shadow_plan_bundle import (
    build_shadow_offline_trajectory,
    build_shadow_plan_bundle,
)

ROOT = Path(__file__).resolve().parents[3]
BINDING = ROOT / "config/observed/arm_device_binding_left_p7_20261110.json"
GAPS = ROOT / "docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json"
DIAG = (
    ROOT
    / "docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json"
)
SHADOW = (
    ROOT
    / "docs/team/B/evidence/field_20261110"
    / "slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json"
)


def test_left_binding_matches_code_endpoints():
    binding = load_arm_device_binding(BINDING)
    channel, _usb, ids = ENDPOINTS["left"]
    assert binding["device_id"] == format_arm_device_id(channel, ids)
    assert binding["device_id"] == "can2:61,62,63,64,65,66,67"


def test_recorded_arm_state_source_and_no_can():
    binding = load_arm_device_binding(BINDING)
    payload = emit_recorded_arm_state_payload(binding, binding_path=str(BINDING))
    assert payload["source"] == "recorded"
    assert payload["device_id"] == "can2:61,62,63,64,65,66,67"
    assert payload["arm_state"]["source"] == "recorded"
    assert payload["can_opened"] is False
    assert payload["motion_enabled"] is False
    assert payload["control_ready"] is False
    assert payload["fresh_live_read"] is False


def test_shadow_plan_hash_is_computed_not_invented():
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    shadow = json.loads(SHADOW.read_text(encoding="utf-8"))
    plan = build_shadow_plan_bundle(diagnostic_permit=diag, shadow_report=shadow)
    traj = build_shadow_offline_trajectory()
    assert plan["trajectory_hash"] == trajectory_hash(traj)
    assert plan["trajectory"]["hash"] == plan["trajectory_hash"]
    assert plan["executable"] is False
    assert plan["motion_enabled"] is False
    assert plan["h3_production_plan"] is False
    assert plan["identity"]["calibration_hash"] == diag["context_present"]["calibration_hash"]
    assert plan["identity"]["config_hash"] == diag["context_present"]["config_hash_or_profile_hash"]
    assert plan["identity"]["scene_version"] == diag["context_present"]["scene_version"]


def test_host_checklist_software_gaps_close_with_shadow_artifacts():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    shadow = json.loads(SHADOW.read_text(encoding="utf-8"))
    plan = build_shadow_plan_bundle(diagnostic_permit=diag, shadow_report=shadow)
    arm = emit_recorded_arm_state_payload(load_arm_device_binding(BINDING))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=arm,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
    )
    payload = report.to_dict()
    assert "plan_bundle_trajectory_hash" not in payload["missing_software"]
    assert "arm_state_device_id" not in payload["missing_software"]
    by_id = {item.id: item for item in report.checklist}
    assert by_id["plan_bundle_trajectory_hash"].status == "PASS"
    assert by_id["arm_state_device_id"].status == "PASS"
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
    assert payload["formal_grasp_ready"] is False
    assert payload["live_permit"] is None
    assert payload["only_operator_enable_remaining"] is False
    assert "live_permit" in payload["missing_field_or_operator"]
    assert "host_policy_control_ready" in payload["missing_field_or_operator"]


def test_emit_cli(tmp_path):
    plan_out = tmp_path / "plan.json"
    arm_out = tmp_path / "arm.json"
    mod = runpy.run_path(str(ROOT / "tools/emit_shadow_plan_and_arm_state.py"))
    rc = mod["main"](
        [
            "--diagnostic-permit",
            str(DIAG),
            "--shadow",
            str(SHADOW),
            "--arm-binding",
            str(BINDING),
            "--plan-bundle-output",
            str(plan_out),
            "--arm-state-output",
            str(arm_out),
        ]
    )
    assert rc == 0
    plan = json.loads(plan_out.read_text(encoding="utf-8"))
    arm = json.loads(arm_out.read_text(encoding="utf-8"))
    assert plan["trajectory_hash"]
    assert arm["device_id"] == "can2:61,62,63,64,65,66,67"
