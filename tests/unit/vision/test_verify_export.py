"""#10 field verify handoff export; never invents association or placement PASS."""
import json
from pathlib import Path

import pytest

from brick_stacking.vision.verify_export import (
    POINT_KIND_MODEL_CENTER,
    POINT_KIND_VISIBLE_TOP_CENTER,
    bundle_to_visual_sample,
    classify_visibility,
    export_field_session,
    localized_review_handoff,
    optical_frame_for_camera,
    resolve_camera_point,
)


ROOT = Path(__file__).resolve().parents[3]
FIELD = ROOT / "docs/team/B/evidence/field_20261110"
RED = FIELD / "verify_pre_grasp_observation_bundles.jsonl"
GREEN = FIELD / "verify_green_observation_bundles.jsonl"
EMPTY = FIELD / "verify_empty_observation_bundles.jsonl"
PLACEMENT_REQUEST = ROOT / "config/planning/first_placement_review_request.template.json"


def test_optical_frame_matches_c35_naming():
    assert optical_frame_for_camera("CP2L863000KL") == (
        "camera_CP2L863000KL_color_optical_frame"
    )


def test_resolve_point_kinds_do_not_fall_back():
    extras = {
        "top_surface_point_kind": "visible_top_center",
        "top_surface_point_camera_m": [0.1, 0.2, 0.3],
        "model_center_camera_m": [0.11, 0.22, 0.33],
    }
    model, _ = resolve_camera_point(extras, POINT_KIND_MODEL_CENTER)
    top, _ = resolve_camera_point(extras, POINT_KIND_VISIBLE_TOP_CENTER)
    assert model == (0.11, 0.22, 0.33)
    assert top == (0.1, 0.2, 0.3)

    missing_model, reasons = resolve_camera_point(
        {"top_surface_point_camera_m": [0.1, 0.2, 0.3],
         "top_surface_point_kind": "visible_top_center"},
        POINT_KIND_MODEL_CENTER,
    )
    assert missing_model is None
    assert "model_center_unavailable_no_top_surface_fallback" in reasons

    missing_top, reasons = resolve_camera_point(
        {"model_center_camera_m": [0.1, 0.2, 0.3]},
        POINT_KIND_VISIBLE_TOP_CENTER,
    )
    assert missing_top is None
    assert "visible_top_center_unavailable_no_model_center_fallback" in reasons


def test_multi_candidate_is_ambiguous_not_empty():
    visibility, block, reasons = classify_visibility({
        "blocks": [
            {"validity": "VALID", "observation_id": "a"},
            {"validity": "VALID", "observation_id": "b"},
        ]
    })
    assert visibility == "AMBIGUOUS"
    assert block is None
    assert "multiple_valid_candidates" in reasons


def test_non_valid_clutter_is_not_empty():
    visibility, block, reasons = classify_visibility({
        "blocks": [{"validity": "INVALID", "observation_id": "x"}]
    })
    assert visibility == "AMBIGUOUS"
    assert block is None
    assert "no_single_valid_block" in reasons


def test_formal_sample_uses_model_center_only():
    rows = [json.loads(line) for line in RED.read_text(encoding="utf-8").splitlines() if line.strip()]
    sample, unknowns = bundle_to_visual_sample(
        rows[0],
        object_id="m-first-red-01",
        region_id="m-first-placement-region-01",
        association_confirmed=False,
        point_kind=POINT_KIND_MODEL_CENTER,
    )
    assert sample is not None
    assert sample.visibility == "VISIBLE"
    assert sample.center_camera_m is not None
    extras = rows[0]["blocks"][0]["b_extensions"]
    assert sample.center_camera_m == tuple(extras["model_center_camera_m"])
    assert sample.center_camera_m != tuple(extras["top_surface_point_camera_m"])
    assert "calibration_hash_sentinel_not_binding" in unknowns


def test_red_session_with_m_request_stays_unknown():
    report = export_field_session(
        RED,
        phase="pre_grasp",
        placement_request_path=PLACEMENT_REQUEST,
    )
    assert report["n_frames"] == 15
    assert report["color_check_counts"].get("MATCH") == 15
    assert report["control_ready"] is False
    assert report["target_id"] == "m-first-red-01"
    assert report["slot_id"] == "m-first-placement-slot-01"
    assert report["region_id"] == "m-first-placement-region-01"
    assert report["formal_verify_point_kind"] == "model_center"
    assert report["placement_review_point_kind"] == "visible_top_center"
    assert report["expected_center_camera_m"] is None
    assert report["calibration_hash"] is None
    first = report["localized_review_handoffs"][0]
    assert first["target_association_confirmed"] is False
    assert first["slot_id"] == "m-first-placement-slot-01"
    assert first["point_kind"] == "visible_top_center"
    assert first["formal_verify_point_kind"] == "model_center"
    assert first["xy_m"]["status"] == "UNKNOWN"
    assert first["support_ok"] is None
    assert first["calibration_candidate_sha256"]
    assert first["frame_id"] == "camera_CP2L863000KL_color_optical_frame"
    assert report["verification_verdict_counts"].get("UNKNOWN", 0) == 15


def test_green_session_is_color_mismatch_diagnostic():
    report = export_field_session(
        GREEN,
        phase="pre_grasp",
        placement_request_path=PLACEMENT_REQUEST,
    )
    assert report["color_check_counts"].get("MISMATCH") == 11
    assert report["control_ready"] is False


def test_empty_session_marks_missing_block():
    rows = [json.loads(line) for line in EMPTY.read_text(encoding="utf-8").splitlines() if line.strip()]
    handoff = localized_review_handoff(
        rows[0],
        expected_color="red",
        region_id="m-first-placement-region-01",
        target_id="m-first-red-01",
        slot_id="m-first-placement-slot-01",
    )
    assert handoff.observation_id is None
    assert "no_single_valid_block" in handoff.unknown_reasons
    assert handoff.color_check == "UNKNOWN"
    assert handoff.formal_verify_point_kind == "model_center"


def test_rejects_mismatched_point_kind_in_request():
    bad = {
        "expected_color": "red",
        "region_id": "r",
        "formal_verify_reference": {"point_kind": "visible_top_center"},
    }
    with pytest.raises(ValueError, match="model_center"):
        export_field_session(RED, phase="pre_grasp", placement_request=bad)
