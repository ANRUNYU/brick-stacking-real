"""Live-or-recorded ArmState validity classification (no CAN / no motion)."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

from brick_stacking.arm.adapter import MockArm
from brick_stacking.arm.arm_state_validity import (
    LIVE_OR_RECORDED_SCHEMA,
    assign_validity_from_joints,
    build_fixture_valid_arm_state,
    classify_arm_state,
    emit_live_or_recorded_payload,
    unwrap_arm_state,
)
from brick_stacking.arm.device_binding import (
    emit_recorded_arm_state_payload,
    load_arm_device_binding,
)
from brick_stacking.execution.host_control_readiness import evaluate_host_control_readiness

ROOT = Path(__file__).resolve().parents[3]
BINDING = ROOT / "config/observed/arm_device_binding_left_p7_20261110.json"
GAPS = ROOT / "docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json"
DIAG = (
    ROOT
    / "docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json"
)
PLAN = ROOT / "docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json"


def test_recorded_binding_is_not_live_valid():
    binding = load_arm_device_binding(BINDING)
    payload = emit_recorded_arm_state_payload(binding)
    state = payload["arm_state"]
    classified = classify_arm_state(state)
    assert classified["source_kind"] == "recorded"
    assert classified["counts_as_recorded_binding"] is True
    assert classified["counts_as_live_valid"] is False
    assert classified["validity"] == "INVALID"
    assert "all_seven_q_rad_finite" in classified["blockers"]
    assert "source_is_real" in classified["blockers"]


def test_fixture_valid_recorded_still_not_live():
    state = build_fixture_valid_arm_state(role="left", source="recorded")
    assert state["validity"] == "VALID"
    assert all(isinstance(q, float) for q in state["q_rad"])
    classified = classify_arm_state(state)
    assert classified["counts_as_live_valid"] is False
    assert classified["source_kind"] == "recorded"
    assert "source_is_real" in classified["blockers"]
    assert classified["condition_status"]["all_seven_q_rad_finite"] == "PASS"


def test_fixture_builder_refuses_source_real():
    import pytest

    with pytest.raises(ValueError, match="refuses source=real"):
        build_fixture_valid_arm_state(source="real")  # type: ignore[arg-type]


def test_mock_arm_valid_is_not_live():
    arm = MockArm((0.0,) * 7, device_id="mock-arm-validity")
    state = arm.read_state()
    classified = classify_arm_state(state)
    assert state["validity"] == "VALID"
    assert classified["counts_as_mock_valid"] is True
    assert classified["counts_as_live_valid"] is False


def test_assign_validity_requires_seven_finite():
    validity, reason = assign_validity_from_joints(
        positions=[0.1, 0.2, 0.3, 0.4, 0.5, None, None],
        failures=["J6/J7: no audited read-only position query"],
    )
    assert validity == "INVALID"
    assert reason is not None
    assert "J6" in reason and "J7" in reason

    validity_ok, reason_ok = assign_validity_from_joints(
        positions=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        failures=[],
    )
    assert validity_ok == "VALID"
    assert reason_ok is None


def test_live_shaped_invalid_reader_sample_classified():
    # Shape of ArmStateReader output today: source=real, J6/J7 missing.
    state = build_fixture_valid_arm_state(role="left", source="recorded")
    live_shaped = dict(state)
    live_shaped["source"] = "real"
    live_shaped["q_rad"] = (0.1, 0.2, 0.3, 0.4, 0.5, None, None)
    live_shaped["validity"], live_shaped["reason"] = assign_validity_from_joints(
        positions=list(live_shaped["q_rad"]),
        failures=["J6/J7: no audited read-only position query"],
    )
    classified = classify_arm_state(live_shaped)
    assert classified["source_kind"] == "live_real"
    assert classified["counts_as_live_valid"] is False
    assert classified["validity"] == "INVALID"
    assert "all_seven_q_rad_finite" in classified["blockers"]


def test_live_valid_requires_seven_finite_real():
    state = build_fixture_valid_arm_state(role="left", source="recorded")
    live = dict(state)
    live["source"] = "real"
    classified = classify_arm_state(live)
    assert classified["counts_as_live_valid"] is True
    assert classified["blockers"] == []


def test_unwrap_live_or_recorded_envelope():
    state = build_fixture_valid_arm_state()
    payload = emit_live_or_recorded_payload(mode="fixture-valid", arm_state=state)
    assert payload["schema_version"] == LIVE_OR_RECORDED_SCHEMA
    assert unwrap_arm_state(payload)["device_id"] == state["device_id"]
    assert payload["counts_as_live_valid"] is False
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False


def test_host_readiness_distinguishes_recorded_vs_live_valid():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    recorded = emit_recorded_arm_state_payload(load_arm_device_binding(BINDING))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=recorded,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
    )
    payload = report.to_dict()
    by_id = {item["id"]: item for item in payload["checklist"]}
    assert by_id["arm_state_device_id"]["status"] == "PASS"
    assert by_id["live_valid_arm_state"]["status"] == "MISSING"
    assert "j6_j7_no_audited_readonly_position_query" in by_id["live_valid_arm_state"]["detail"]
    assert payload["arm_feedback"]["counts_as_live_valid"] is False
    assert payload["arm_feedback"]["source_kind"] == "recorded"
    assert payload["arm_feedback"]["j6j7_readonly_hard_block"]["status"] == "HARD_BLOCK"
    assert payload["gate_ladder"]["counts_as_live_valid"] is False
    assert payload["gate_ladder"]["j6j7_readonly_position_hard_block"] is True
    assert "live_valid_arm_state" not in payload["missing_software"]
    assert any(b["id"] == "live_valid_arm_state" for b in payload["hard_blockers"])


def test_cli_recorded_and_fixture_modes(tmp_path):
    mod = runpy.run_path(str(ROOT / "tools/arm_state_live_or_recorded.py"))
    out_rec = tmp_path / "recorded.json"
    out_fix = tmp_path / "fixture.json"
    assert (
        mod["main"](
            [
                "--mode",
                "recorded",
                "--arm-binding",
                str(BINDING),
                "--output",
                str(out_rec),
            ]
        )
        == 0
    )
    assert (
        mod["main"](
            [
                "--mode",
                "fixture-valid",
                "--output",
                str(out_fix),
            ]
        )
        == 0
    )
    rec = json.loads(out_rec.read_text(encoding="utf-8"))
    fix = json.loads(out_fix.read_text(encoding="utf-8"))
    assert rec["validity"] == "INVALID"
    assert rec["counts_as_live_valid"] is False
    assert rec["counts_as_recorded_binding"] is True
    assert fix["validity"] == "VALID"
    assert fix["counts_as_live_valid"] is False
    assert fix["control_ready"] is False
    assert fix["motion_enabled"] is False
