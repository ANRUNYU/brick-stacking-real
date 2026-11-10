"""Offline analysis for #7; never invents a zero bound."""
import json
from pathlib import Path

from brick_stacking.vision.clock_error_bound import analyze_clock_rows


ROOT = Path(__file__).resolve().parents[3]
FIELD = ROOT / "docs/team/B/evidence/field_20261110/single_red_observation_bundles.jsonl"


def test_single_red_draft_bound_is_provisional_and_nonzero():
    rows = [json.loads(line) for line in FIELD.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = analyze_clock_rows(
        rows, source=str(FIELD), half_exposure_s=50e-6, safety_factor=2.0, min_frames=12,
    )
    assert report["status"] == "PROVISIONAL_MAPPING_BOUND"
    assert report["control_ready"] is False
    assert report["clock_error_bound_s"] > 0
    assert report["n_usable"] == 12
    assert report["exposure_reference"].startswith("orbbec_color_global")


def test_insufficient_samples_stay_null():
    report = analyze_clock_rows(
        [], source="empty", half_exposure_s=50e-6, safety_factor=2.0, min_frames=12,
    )
    assert report["status"] == "INSUFFICIENT_SAMPLES"
    assert report["clock_error_bound_s"] is None
