import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from brick_stacking.app.offline_runner import synthetic_frame
from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.vision.block_instance_segmentation import BlockDetector
from brick_stacking.vision.observation_exchange import CaptureContext, observation_exchange, profile_hash
from brick_stacking.vision.tabletop_segmentation import TabletopDetector


ROOT = Path(__file__).resolve().parents[3]
REAL_CAMERA = ROOT / "tests/fixtures/real/C_20261108_tabletop/camera"
GOLDEN = ROOT / "tests/fixtures/vision_exchange"


def synthetic_examples():
    frame = synthetic_frame()
    config = load_config(ROOT / "config/defaults.yaml")["vision"]
    detector = BlockDetector(config)
    context = CaptureContext("synthetic_rgbd.npz", "synthetic", profile_hash(config), frame.clock_domain)
    cases = {"normal_and_ambiguous": observation_exchange(
        frame, context, detector.detect(frame), nominal_edge_m=.05,
    )}
    missing = replace(frame, depth_m=np.full(frame.depth_m.shape, np.nan))
    cases["invalid_depth"] = observation_exchange(
        missing, replace(context, image_ref="synthetic_invalid_depth.npz"),
        detector.detect(missing), nominal_edge_m=.05,
    )
    cases["expired"] = observation_exchange(
        frame, context, detector.detect(frame), nominal_edge_m=.05, stale=True,
    )
    return cases


def test_synthetic_exchange_matches_golden():
    expected = json.loads((GOLDEN / "synthetic_status_v0.1.json").read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(synthetic_examples(), allow_nan=False))
    assert actual == expected
    assert actual["expired"]["rgbd"]["validity"] == "INVALID"
    assert actual["invalid_depth"]["rgbd"]["reason"] == "invalid_depth"
    normal = actual["normal_and_ambiguous"]
    assert {row["validity"] for row in normal["blocks"]} == {"VALID", "UNKNOWN"}
    assert all(row["camera_pose"] is None and row["covariance"] is None for row in normal["blocks"])
    assert normal["rgbd"]["host_receive_stamp"] is None


@pytest.mark.parametrize("index", range(3))
def test_recorded_c_sdk_clock_is_only_provisional(index):
    saved = json.loads((GOLDEN / "c_recording_bundles_v0.1.json").read_text(encoding="utf-8"))[index]
    path = REAL_CAMERA / f"frame_{index:03d}.npz"
    report = json.loads((REAL_CAMERA / "camera_report.json").read_text(encoding="utf-8"))
    frame, metadata = RecordedCamera.read_recording(path)
    profile = load_config(ROOT / "config/vision_profiles/head_replacement_candidate.yaml")["tabletop"]
    ref = path.relative_to(ROOT).as_posix()
    context = CaptureContext.from_recording(
        frame, metadata, image_ref=ref, profile="head_replacement_candidate",
        profile_hash=profile_hash(profile), report=report,
    )
    bundle = observation_exchange(
        frame, context, TabletopDetector(profile).detect(frame), nominal_edge_m=.05, recorded=True,
    )
    assert bundle["rgbd"]["source"] == "recorded"
    assert bundle["rgbd"]["rgb_ref"] == saved["rgbd"]["rgb_ref"] == f"{ref}#rgb"
    assert bundle["timing"]["original_source"] == "real_measured"
    for field in ("sdk_clock_observation", "host_receive_stamp_s", "color_device_stamp_s",
                  "depth_device_stamp_s", "raw_intrinsics"):
        assert bundle["timing"][field] == saved["timing"][field]
    assert bundle["timing"]["sdk_clock_observation"]["frames"]["depth"]["global_timestamp_us"] > 0
    assert bundle["timing"]["clock_error_bound_s"] is None
    assert bundle["timing"]["exposure_host_stamp_s"] is None
    assert bundle["control_ready"] is False
    assert bundle["calibration_hash"] is None
    assert len(bundle["blocks"]) == len(saved["blocks"])
    block = next(row for row in bundle["blocks"] if row["validity"] == "VALID")
    extras = block["b_extensions"]
    assert extras["top_surface_point_kind"] == "visible_top_center"
    assert np.linalg.norm(np.array(extras["top_surface_point_camera_m"])
                          - extras["model_center_camera_m"]) == pytest.approx(.025)
    assert len(extras["measured_top_span_m"]) == 2
    assert block["camera_pose"] is None and block["covariance"] is None
    assert block["size_source"] == "nominal_profile"


def test_candidate_from_another_frame_is_rejected():
    frame = synthetic_frame()
    detector = BlockDetector(load_config(ROOT / "config/defaults.yaml")["vision"])
    context = CaptureContext("mock", "profile", "hash", frame.clock_domain)
    with pytest.raises(ValueError, match="does not belong"):
        observation_exchange(replace(frame, stamp_s=2), context, detector.detect(frame), nominal_edge_m=.05)
