from dataclasses import replace
import json
import numpy as np
import pytest
from brick_stacking.app.offline_runner import synthetic_frame
from brick_stacking.hardware.mock_devices import RecordedCamera


@pytest.mark.parametrize("change", ["unaligned", "distorted", "bad_rgb", "bad_shape", "focal", "stamp", "clock"])
def test_invalid_camera_metadata_rejected(change):
    f = synthetic_frame()
    kw = {}
    if change == "unaligned": kw["registered"] = False
    if change == "distorted": kw["rectified"] = False
    if change == "bad_rgb": kw["rgb"] = f.rgb.astype(float)
    if change == "bad_shape": kw["depth_m"] = np.ones((3, 3))
    if change == "focal":
        k = f.k.copy()
        k[0, 0] = 0
        kw["k"] = k
    if change == "stamp": kw["stamp_s"] = float("nan")
    if change == "clock": kw["clock_domain"] = ""
    with pytest.raises(ValueError): replace(f, **kw)


def test_camera_input_is_immutable_copy():
    f = synthetic_frame()
    with pytest.raises(ValueError): f.depth_m[0, 0] = 2


def test_recording_millimetres_not_guessed(tmp_path):
    f = synthetic_frame()
    meta = dict(camera_id=f.camera_id, frame_id=f.frame_id, stamp_s=1,
                clock_domain="synthetic", source="synthetic", registered=True,
                rectified=True, depth_unit="mm")
    p = tmp_path / "bad_units.npz"
    np.savez(p, rgb=f.rgb, depth_m=f.depth_m * 1000, k=f.k, metadata=json.dumps(meta))
    with pytest.raises(ValueError, match="metres"):
        RecordedCamera([p]).get_synced_rgbd()
