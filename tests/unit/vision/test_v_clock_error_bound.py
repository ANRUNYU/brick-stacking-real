"""Offline analysis for #7; never invents a zero bound."""
import json
from pathlib import Path

from brick_stacking.vision.clock_error_bound import (
    analyze_clock_rows,
    attach_accepted_timing_bound,
    load_observation_timing_bound,
    resolve_clock_bound_evidence_path,
)
from brick_stacking.planning.placement_bridge import BundleBinding, audit_bundle


ROOT = Path(__file__).resolve().parents[3]
FIELD = ROOT / "docs/team/B/evidence/field_20261110/single_red_observation_bundles.jsonl"
STUDY = ROOT / "docs/team/B/evidence/field_20261110/clock_error_bound_study_v0.1.json"
LIVE_INCOMPLETE = (
    ROOT / "docs/team/B/evidence/field_20261110"
    / "slot_contrast_20261110_214801/rgbd/observation_bundles.jsonl"
)


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


def test_field_study_loads_for_observation_timing():
    bound, ref = load_observation_timing_bound(STUDY)
    assert bound > 0
    assert ref.endswith("clock_error_bound_study_v0.1.json")
    assert json.loads(STUDY.read_text(encoding="utf-8"))["acceptance"] == (
        "ACCEPTED_FOR_OBSERVATION_TIMING"
    )


def test_resolve_clock_bound_evidence_falls_back_to_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_clock_bound_evidence_path(STUDY.name) is None
    resolved = resolve_clock_bound_evidence_path(
        "docs/team/B/evidence/field_20261110/clock_error_bound_study_v0.1.json"
    )
    assert resolved is not None
    assert resolved.resolve() == STUDY.resolve()
    bound, ref = load_observation_timing_bound(
        "docs/team/B/evidence/field_20261110/clock_error_bound_study_v0.1.json"
    )
    assert bound > 0
    assert ref.endswith("clock_error_bound_study_v0.1.json")


def test_attach_accepted_bound_enables_bundle_binding_on_live_incomplete():
    rows = [json.loads(line) for line in LIVE_INCOMPLETE.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    bundle = json.loads(json.dumps(rows[0]))
    timing = bundle["timing"]
    assert timing["clock_error_bound_s"] is None
    assert timing["output_monotonic_s"] is not None
    assert attach_accepted_timing_bound(bundle, STUDY) is True
    assert timing["validity"] == "VALID"
    assert timing["error_bound_evidence_ref"].endswith("clock_error_bound_study_v0.1.json")
    assert bundle["control_ready"] is False
    rgbd = bundle["rgbd"]
    binding = BundleBinding(
        rgbd["device_id"], rgbd["frame_id"], rgbd["epoch"], timing["host_boot_epoch"],
        bundle["profile_hash"], timing["error_bound_evidence_ref"], 2.656,
    )
    # Live contrast pack had 0 VALID blocks under production HSV; binding/timing still audit.
    report = audit_bundle(
        bundle, binding, now_s=timing["output_monotonic_s"], expected_color="red",
    )
    assert "BUNDLE_BINDING_MISSING" not in report["problems"]
    assert "TIMING_UNKNOWN_STALE_OR_FUTURE" not in report["problems"]
    assert "MISSING_OR_AMBIGUOUS_TARGET" in report["problems"]
