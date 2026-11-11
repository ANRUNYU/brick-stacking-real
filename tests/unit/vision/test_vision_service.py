"""CONTRACTS facade and offline continuous replay (#8/#9/#10)."""
import json
from pathlib import Path

import pytest

from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.verification.visual_transition import VerificationRequest
from brick_stacking.vision.observation_exchange import CaptureContext
from brick_stacking.vision.replay_pipeline import replay_recordings
from brick_stacking.vision.service import VisionSession, detect_blocks, load_tabletop_profile, replay, verify


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config/vision_profiles/head_replacement_candidate.yaml"
CAMERA = ROOT / "tests/fixtures/real/C_20261108_tabletop/camera"
RECORDINGS = [CAMERA / f"frame_{index:03d}.npz" for index in range(3)]


def test_replay_exports_observation_bundle_with_control_ready_false():
    bundle = replay(RECORDINGS[0], config_path=CONFIG, image_ref=RECORDINGS[0].relative_to(ROOT).as_posix())
    assert bundle["schema_version"] == "0.1"
    assert bundle["control_ready"] is False
    assert bundle["calibration_hash"] is None
    assert bundle["timing"]["clock_error_bound_s"] is None
    assert any(block["validity"] == "VALID" for block in bundle["blocks"])
    assert all(block["camera_pose"] is None for block in bundle["blocks"])


def test_detect_blocks_matches_replay_candidate_count():
    profile, _, _ = load_tabletop_profile(CONFIG)
    frame, _ = RecordedCamera.read_recording(RECORDINGS[0])
    observed = detect_blocks(frame, profile)
    bundle = replay(RECORDINGS[0], config_path=CONFIG)
    assert len(observed.candidates) == len(bundle["blocks"])


def test_verify_facade_returns_unknown_without_images():
    request = VerificationRequest(
        "pre_grasp", "block-1", "supply", "red", "scene", "config", "calibration",
        "geometry", "mock", "epoch", .5, "mock",
    )
    evidence = verify(request, before=None, after=(), now_s=1.)
    assert evidence["verdict"] == "UNKNOWN"
    assert evidence["reason"] == "missing_images"


def test_continuous_replay_publishes_all_frames_and_keeps_latency_null(tmp_path):
    report = tmp_path / "replay_summary.json"
    bundles, summary = replay_recordings(
        RECORDINGS, config_path=CONFIG, max_receive_age_s=3., max_pair_skew_s=.05,
        report_path=report,
    )
    assert len(bundles) == 3
    assert summary["published"] == 3
    assert summary["rejected"] == []
    assert summary["preserved_host_clocks"] is False
    assert summary["clock_error_bound_s"] is None
    assert summary["control_ready"] is False
    assert summary["independent_scene_validation"] is False
    assert summary["online_metrics"]["exposure_to_output_s"] is None
    assert summary["online_metrics"]["receive_to_output_s"] is not None
    for row in summary["per_frame"]:
        assert row["control_ready"] is False
        assert row["exposure_to_output_s"] is None
        assert row["valid_blocks"] >= 1
        assert row["output_monotonic_s"] is not None
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["profile_hash"] == summary["profile_hash"]


def test_field_preserve_clock_replay_fills_binding_timing():
    from brick_stacking.planning.placement_bridge import BundleBinding, audit_bundle

    field = ROOT / "docs/team/B/evidence/field_20261110/slot_contrast_20261110_214801/rgbd"
    npz = sorted(field.glob("observed_00_*.npz"))
    config = ROOT / "config/vision_profiles/head_slot_contrast_s140.yaml"
    if len(npz) < 3 or not config.is_file():
        pytest.skip("field slot-contrast NPZ / S140 profile unavailable")
    rows, summary = replay_recordings(
        npz, config_path=config, max_receive_age_s=3., max_pair_skew_s=.05,
    )
    assert summary["preserved_host_clocks"] is True
    assert summary["published"] == 3
    assert summary["clock_error_bound_s"] is not None
    assert summary["control_ready"] is False
    for row in rows:
        timing = row["bundle"]["timing"]
        assert timing["validity"] == "VALID"
        assert timing["error_bound_evidence_ref"]
        assert timing["output_monotonic_s"] is not None
        assert timing["exposure_host_stamp_s"] is not None
        assert timing["exposure_to_output_s"] is not None
        rgbd = row["bundle"]["rgbd"]
        binding = BundleBinding(
            rgbd["device_id"], rgbd["frame_id"], rgbd["epoch"], timing["host_boot_epoch"],
            row["bundle"]["profile_hash"], timing["error_bound_evidence_ref"], 2.656,
        )
        report = audit_bundle(
            row["bundle"], binding, now_s=timing["output_monotonic_s"], expected_color="red",
        )
        assert "BUNDLE_BINDING_MISSING" not in report["problems"]
        assert "TIMING_UNKNOWN_STALE_OR_FUTURE" not in report["problems"]
    assert sum(row["valid_blocks"] for row in rows) == 3


def test_vision_session_get_observation_expires():
    now = [10.]
    session = VisionSession(
        config_path=CONFIG, max_receive_age_s=1., max_pair_skew_s=.05, clock=lambda: now[0],
    )
    frame, metadata = RecordedCamera.read_recording(RECORDINGS[0])
    session.start(camera_id=frame.camera_id, epoch="session-a")
    profile, digest, name = load_tabletop_profile(CONFIG)
    patched = dict(
        metadata, host_receive_stamp_s=now[0], host_clock_domain="process_monotonic",
        epoch="session-a", image_profile_version=name, profile_hash=digest,
    )
    context = CaptureContext.from_recording(
        frame, patched, image_ref=RECORDINGS[0].as_posix(), profile=name,
        profile_hash=digest, report=json.loads((CAMERA / "camera_report.json").read_text(encoding="utf-8")),
    )
    assert session.offer(frame, context)
    assert session.process_latest() is not None
    assert session.get_observation() is not None
    now[0] += 2
    assert session.get_observation() is None
