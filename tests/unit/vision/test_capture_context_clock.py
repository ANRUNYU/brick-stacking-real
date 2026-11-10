"""#7 clock-interface edge cases for CaptureContext; no fabricated error bounds."""
from dataclasses import replace
from pathlib import Path

import pytest

from brick_stacking.app.offline_runner import synthetic_frame
from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.vision.observation_exchange import CaptureContext, observation_exchange, profile_hash


ROOT = Path(__file__).resolve().parents[3]
REAL = ROOT / "tests/fixtures/real/C_20261108_tabletop/camera"


def test_host_arrival_requires_named_clock_domain():
    with pytest.raises(ValueError, match="host arrival"):
        CaptureContext("img.npz", "profile", "hash", "epoch", host_receive_s=1.)


def test_invalid_negative_device_stamp_rejected():
    with pytest.raises(ValueError, match="invalid camera timestamp"):
        CaptureContext("img.npz", "profile", "hash", "epoch", color_device_s=-1.)


def test_zero_depth_scale_rejected():
    with pytest.raises(ValueError, match="depth scale"):
        CaptureContext("img.npz", "profile", "hash", "epoch", depth_scale_m_per_unit=0.)


def test_rgb_depth_delta_and_unknown_exposure_fields():
    context = CaptureContext(
        "img.npz", "profile", "hash", "epoch", 10., "process_monotonic",
        color_device_s=1., depth_device_s=1.004, depth_scale_m_per_unit=0.001,
        clock_unavailable_reason="no_device_to_host_mapping",
    )
    assert context.rgb_depth_delta_s == pytest.approx(0.004)
    frame = replace(synthetic_frame(), stamp_s=1.)
    bundle = observation_exchange(frame, context, (), nominal_edge_m=.05)
    timing = bundle["timing"]
    assert timing["clock_error_bound_s"] is None
    assert timing["exposure_host_stamp_s"] is None
    assert timing["validity"] == "UNKNOWN"
    assert timing["sdk_clock_unavailable_reason"] == "no_device_to_host_mapping"
    assert bundle["control_ready"] is False


def test_recorded_c_clock_observation_preserved_without_bound():
    path = REAL / "frame_000.npz"
    report = __import__("json").loads((REAL / "camera_report.json").read_text(encoding="utf-8"))
    frame, metadata = RecordedCamera.read_recording(path)
    context = CaptureContext.from_recording(
        frame, metadata, image_ref=path.as_posix(), profile="head_replacement_candidate",
        profile_hash="abc", report=report,
    )
    assert context.clock_observation["schema_version"] == "c-orbbec-clock-observation-1"
    assert context.host_receive_s is not None
    assert context.host_clock_domain is not None
    assert context.rgb_depth_delta_s is not None
    assert context.rgb_depth_delta_s >= 0
    bundle = observation_exchange(frame, context, (), nominal_edge_m=.05, recorded=True)
    assert bundle["timing"]["sdk_clock_observation"] is not None
    assert bundle["timing"]["clock_error_bound_s"] is None
    assert bundle["timing"]["exposure_reference"] == (
        "orbbec_color_global_timestamp_mapped_to_process_monotonic"
    )
    assert bundle["timing"]["exposure_host_stamp_s"] is not None
    assert bundle["timing"]["validity"] == "UNKNOWN"
    assert bundle["timing"]["reason"] == "clock_mapping_bound_unvalidated"


def test_unsupported_clock_observation_schema_rejected():
    path = REAL / "frame_000.npz"
    frame, metadata = RecordedCamera.read_recording(path)
    bad = dict(metadata, clock_observation={"schema_version": "other", "frames": {}})
    with pytest.raises(ValueError, match="unsupported SDK clock"):
        CaptureContext.from_recording(
            frame, bad, image_ref=path.as_posix(), profile="p", profile_hash="h",
        )


def test_color_stamp_mismatch_rejected():
    path = REAL / "frame_000.npz"
    frame, metadata = RecordedCamera.read_recording(path)
    bad = dict(metadata, rgb_device_stamp_s=frame.stamp_s + 1.)
    # Clear clock observation so metadata stamp is authoritative.
    bad.pop("clock_observation", None)
    with pytest.raises(ValueError, match="does not match"):
        CaptureContext.from_recording(
            frame, bad, image_ref=path.as_posix(), profile="p", profile_hash="h",
        )


def test_profile_hash_is_stable_for_identical_tables():
    assert profile_hash({"a": 1, "b": [2, 3]}) == profile_hash({"b": [2, 3], "a": 1})
