"""#10 field verify handoff export; never invents association or placement PASS."""
import json
from pathlib import Path

from brick_stacking.vision.verify_export import (
    export_field_session,
    localized_review_handoff,
    optical_frame_for_camera,
)


ROOT = Path(__file__).resolve().parents[3]
FIELD = ROOT / "docs/team/B/evidence/field_20261110"
RED = FIELD / "verify_pre_grasp_observation_bundles.jsonl"
GREEN = FIELD / "verify_green_observation_bundles.jsonl"
EMPTY = FIELD / "verify_empty_observation_bundles.jsonl"


def test_optical_frame_matches_c35_naming():
    assert optical_frame_for_camera("CP2L863000KL") == (
        "camera_CP2L863000KL_color_optical_frame"
    )


def test_red_session_color_match_but_association_unknown():
    report = export_field_session(
        RED, expected_color="red", region_id="supply", target_id=None,
        phase="pre_grasp", association_confirmed=False,
    )
    assert report["n_frames"] == 15
    assert report["color_check_counts"].get("MATCH") == 15
    assert report["control_ready"] is False
    first = report["localized_review_handoffs"][0]
    assert first["target_association_confirmed"] is False
    assert first["xy_m"]["status"] == "UNKNOWN"
    assert first["support_ok"] is None
    assert first["frame_id"] == "camera_CP2L863000KL_color_optical_frame"
    # Without expected pose / association, formal verify stays UNKNOWN (not placement PASS).
    assert report["verification_verdict_counts"].get("UNKNOWN", 0) == 15


def test_green_session_is_color_mismatch_diagnostic():
    report = export_field_session(
        GREEN, expected_color="red", region_id="supply", target_id=None,
        phase="pre_grasp",
    )
    assert report["color_check_counts"].get("MISMATCH") == 11
    assert report["control_ready"] is False


def test_empty_session_marks_missing_block():
    rows = [json.loads(line) for line in EMPTY.read_text(encoding="utf-8").splitlines() if line.strip()]
    handoff = localized_review_handoff(rows[0], expected_color="red", region_id="supply")
    assert handoff.observation_id is None
    assert "no_single_valid_block" in handoff.unknown_reasons
    assert handoff.color_check == "UNKNOWN"
