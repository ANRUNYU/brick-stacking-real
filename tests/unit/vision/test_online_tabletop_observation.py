import json
from pathlib import Path
import time

from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.runtime.config_loader import load_config
from tools.online_tabletop_observation import observe


ROOT = Path(__file__).resolve().parents[3]


def test_same_serial_reconnect_exports_the_published_pair(tmp_path):
    profile = load_config(ROOT / "config/vision_profiles/head_replacement_candidate.yaml")
    source = ROOT / "tests/fixtures/real/C_20261108_tabletop/camera/frame_000.npz"
    frame, metadata = RecordedCamera.read_recording(source)
    profile["tabletop"]["image_size_wh"] = list(frame.rgb.shape[:2][::-1])
    stream = {"width": frame.rgb.shape[1], "height": frame.rgb.shape[0], "fps": 15}
    attempts = []
    report = {}

    def attempt(session, offer):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("mock camera disconnected")
        session["profiles"] = {"color": stream, "depth": stream}
        for index in range(3):
            stamp = 1. + index / 15.
            meta = {
                key: metadata[key] for key in ("camera_id", "frame_id", "registered", "rectified")
            }
            meta.update(stamp_s=stamp, clock_domain="mock-reconnected-epoch", source="mock",
                        rgb_device_stamp_s=stamp, depth_device_stamp_s=stamp + .001,
                        host_receive_stamp_s=time.monotonic(), host_clock_domain="process_monotonic",
                        depth_scale_mm=1.)
            offer(frame.rgb, frame.depth_m, frame.k, meta, session)
        session["result"] = "CAPTURED"

    observe(tmp_path, report, profile, max_age_s=10., max_skew_s=.01, reconnects=1,
            capture_attempt=attempt)
    assert report["result"] == "OBSERVED"
    assert report["capture_attempts"][0]["result"] == "ERROR"
    assert report["capture_attempts"][1]["observation_count"] > 0
    rows = (tmp_path / "observation_bundles.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == report["online_metrics"]["counts"]["published"]
    for row in map(json.loads, rows):
        rgbd = row["rgbd"]
        ref = rgbd["rgb_ref"].split("#")[0]
        saved, meta = RecordedCamera.read_recording(tmp_path / ref)
        assert saved.stamp_s == rgbd["device_stamp"]
        assert rgbd["depth_ref"] == f"{ref}#depth_m"
        assert meta["profile_hash"] == row["profile_hash"]
        assert rgbd["epoch"] == "mock-reconnected-epoch"
        assert row["timing"]["exposure_to_output_s"] is None
        assert row["control_ready"] is False
