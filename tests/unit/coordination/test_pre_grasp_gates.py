"""Pre-grasp readiness: report gaps only; never forge PASS/permit/control_ready."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from brick_stacking.planning.pre_grasp_gates import (
    GATE_IDS,
    association_switch_payload,
    evidence_gap_report,
    evaluate_pre_grasp_readiness,
)

ROOT = Path(__file__).resolve().parents[3]
FIELD = ROOT / "docs/team/B/evidence/field_20261110"
ADOPTED = ROOT / "config/planning/first_placement_review_request.adopted.json"
SHADOW_ASSOC = FIELD / "slot_contrast_red_s140_shadow_assoc_20261110_214801.json"
SHADOW_BOUND = FIELD / "slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json"
OVERLAY = FIELD / "first_placement_request_assoc_handclear_overlay_20261110.json"
ASSOC_RECORD = FIELD / "association_confirm_switch_20261110.json"


def test_gate_catalog_covers_required_ids():
    required = {
        "association",
        "hand_clear",
        "calibration_binding",
        "bundle_binding_clock",
        "m_context",
        "permit",
        "control_ready_policy",
    }
    assert required.issubset(set(GATE_IDS))


def test_field_shadow_readiness_blocks_and_never_grants_entry():
    # Adopted alone still lacks durable association/hand_clear overlay fields.
    request = json.loads(ADOPTED.read_text(encoding="utf-8"))
    shadow = json.loads(SHADOW_ASSOC.read_text(encoding="utf-8"))
    report = evaluate_pre_grasp_readiness(
        request=request,
        shadow_report=shadow,
        request_path=str(ADOPTED),
        shadow_path=str(SHADOW_ASSOC),
    )
    assert report.control_ready is False
    assert report.motion_enabled is False
    assert report.permit is None
    assert report.formal_grasp_entry_allowed is False
    assert report.evidence_gates_clear is False
    by_id = {g.gate_id: g for g in report.gates}
    assert by_id["expected_pose_adopted"].status == "PASS"
    assert by_id["reference_id"].status == "PASS"
    assert by_id["color_match"].status == "PASS"
    assert by_id["xy_height_measured"].status == "PASS"
    # Current-binding ACTIVE stamps calibration_hash; clock BundleBinding already present.
    assert by_id["calibration_binding"].status == "PASS"
    assert by_id["bundle_binding_clock"].status == "PASS"
    assert by_id["m_context"].status == "PASS"
    assert by_id["hand_clear"].status == "UNKNOWN"
    assert by_id["yaw_bound"].status == "UNKNOWN"
    assert by_id["permit"].status == "POLICY_HOLD"
    assert by_id["control_ready_policy"].status == "POLICY_HOLD"
    # CLI association on shadow without durable record → association UNKNOWN
    assert by_id["association"].status == "UNKNOWN"
    gaps = evidence_gap_report(report)
    assert gaps["formal_grasp_entry_allowed"] is False
    assert gaps["control_ready"] is False
    assert "ERROR_BOUND_UNKNOWN:yaw_rad" in report.consumer_reason_union
    assert "HAND_CLEAR_EVIDENCE_MISSING" in report.consumer_reason_union
    assert "CALIBRATION_BINDING_MISSING" not in report.consumer_reason_union
    assert "M_CONTEXT_MISSING" not in report.consumer_reason_union


def test_overlay_handclear_association_still_blocks_on_yaw():
    request = json.loads(OVERLAY.read_text(encoding="utf-8"))
    shadow = json.loads(SHADOW_BOUND.read_text(encoding="utf-8"))
    association = json.loads(ASSOC_RECORD.read_text(encoding="utf-8"))
    report = evaluate_pre_grasp_readiness(
        request=request,
        shadow_report=shadow,
        association_record=association,
        request_path=str(OVERLAY),
        shadow_path=str(SHADOW_BOUND),
        association_path=str(ASSOC_RECORD),
    )
    by_id = {g.gate_id: g for g in report.gates}
    assert by_id["association"].status == "PASS"
    assert by_id["hand_clear"].status == "PASS"
    assert by_id["calibration_binding"].status == "PASS"
    assert by_id["m_context"].status == "PASS"
    assert by_id["yaw_bound"].status == "UNKNOWN"
    assert by_id["shadow_inspection"].status != "PASS"
    assert report.formal_grasp_entry_allowed is False
    assert report.control_ready is False
    assert "ERROR_BOUND_UNKNOWN:yaw_rad" in report.consumer_reason_union


def test_association_record_without_forging_control_ready():
    request = json.loads(ADOPTED.read_text(encoding="utf-8"))
    shadow = json.loads(SHADOW_ASSOC.read_text(encoding="utf-8"))
    record = association_switch_payload(
        target_id=request["target_id"],
        reference_id=request["reference_id"],
        region_id=request["region_id"],
        slot_id=request["slot_id"],
        operator="unit-test",
        evidence_ref="docs/team/B/evidence/field_20261110/slot_contrast_20261110_214801.zip",
        confirmed=True,
    )
    report = evaluate_pre_grasp_readiness(
        request=request, shadow_report=shadow, association_record=record
    )
    by_id = {g.gate_id: g for g in report.gates}
    assert by_id["association"].status == "PASS"
    assert report.formal_grasp_entry_allowed is False
    assert report.control_ready is False
    assert by_id["calibration_binding"].status == "PASS"
    assert by_id["yaw_bound"].status == "UNKNOWN"


def test_association_switch_requires_evidence_fields():
    with pytest.raises(ValueError):
        association_switch_payload(
            target_id="",
            reference_id="table_black_cross_20mm",
            region_id="r",
            slot_id=None,
            operator="op",
            evidence_ref="e",
            confirmed=True,
        )


def test_cli_readiness_and_association_tools(tmp_path):
    assoc_out = tmp_path / "assoc.json"
    overlay_out = tmp_path / "overlay.json"
    ready_out = tmp_path / "ready.json"
    gaps_out = tmp_path / "gaps.json"

    assoc_mod = runpy.run_path(str(ROOT / "tools/association_confirm_switch.py"))
    assoc_mod["main"](
        [
            "--operator",
            "unit-test",
            "--evidence-ref",
            "docs/team/B/evidence/field_20261110/slot_contrast_20261110_214801.zip",
            "--output",
            str(assoc_out),
            "--write-adopted-overlay",
            "--overlay-output",
            str(overlay_out),
        ]
    )
    assoc = json.loads(assoc_out.read_text(encoding="utf-8"))
    assert assoc["target_association_confirmed"] is True
    assert assoc["control_ready"] is False
    overlay = json.loads(overlay_out.read_text(encoding="utf-8"))
    assert overlay["target_association_confirmed"] is True
    assert overlay["control_ready"] is False
    assert overlay["permit"] is None

    ready_mod = runpy.run_path(str(ROOT / "tools/pre_grasp_readiness.py"))
    ready_mod["main"](
        [
            "--shadow",
            str(SHADOW_ASSOC),
            "--association-record",
            str(assoc_out),
            "--output",
            str(ready_out),
        ]
    )
    ready = json.loads(ready_out.read_text(encoding="utf-8"))
    assert ready["formal_grasp_entry_allowed"] is False
    assert ready["control_ready"] is False
    assert ready["evidence_gates_clear"] is False

    ready_mod["main"](
        [
            "--gaps-only",
            "--shadow",
            str(SHADOW_ASSOC),
            "--association-record",
            str(assoc_out),
            "--output",
            str(gaps_out),
        ]
    )
    gaps = json.loads(gaps_out.read_text(encoding="utf-8"))
    assert gaps["permit"] is None
    assert any(g["gate_id"] == "hand_clear" for g in gaps["blocking_gaps"])
