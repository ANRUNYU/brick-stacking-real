import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.camera_projection import backproject


def transform(target, source, translation, **kw):
    m = np.eye(4)
    m[:3, 3] = translation
    return RigidTransform(target, source, m, "synthetic", **kw)


def test_noncommuting_chain_and_inverse():
    a = transform("world", "arm", [1, 0, 0])
    m = np.eye(4)
    m[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    b = RigidTransform("arm", "camera", m, "synthetic")
    c = a.compose(b)
    np.testing.assert_allclose(c.apply([1, 0, 0]), [1, 1, 0])
    np.testing.assert_allclose(c.inverse().apply(c.apply([2, 3, 4])), [2, 3, 4])
    with pytest.raises(ValueError):
        b.compose(a)


@pytest.mark.parametrize("mode", ["reflection", "scale", "nan", "bottom_row"])
def test_invalid_rotation_and_matrix_rejected(mode):
    m = np.eye(4)
    if mode == "reflection": m[0, 0] = -1
    if mode == "scale": m[0, 0] = 2
    if mode == "nan": m[0, 3] = np.nan
    if mode == "bottom_row": m[3, 0] = 1
    with pytest.raises(ValueError):
        RigidTransform("a", "b", m, "synthetic")


def test_dynamic_tf_capture_time_and_clock():
    t = transform("a", "b", [0, 0, 0], stamp_s=1, clock_domain="epoch1")
    t.require_capture_time(1.01, "epoch1", .02)
    for stamp, clock in [(1.1, "epoch1"), (1, "epoch2")]:
        with pytest.raises(ValueError):
            t.require_capture_time(stamp, clock, .02)
    with pytest.raises(ValueError):
        t.compose(transform("b", "c", [0, 0, 0], stamp_s=2, clock_domain="epoch1"))


def test_synthetic_transform_cannot_be_approved():
    with pytest.raises(ValueError):
        transform("a", "b", [0, 0, 0], approved=True, calibration_id="fake")


def test_projection_metres_and_optical_z():
    k = np.array([[100, 0, 50], [0, 100, 40], [0, 0, 1]])
    np.testing.assert_allclose(backproject([60, 60], .5, k), [.05, .1, .5])
    with pytest.raises(ValueError):
        backproject([60, 60], 0, k)
