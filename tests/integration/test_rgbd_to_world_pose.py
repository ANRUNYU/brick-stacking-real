import numpy as np
import pytest
from brick_stacking.app.offline_runner import synthetic_frame, save_recording
from brick_stacking.hardware.mock_devices import RecordedCamera, MockArm, MockHand
from brick_stacking.localization.block_localization import localize_top_face
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.vision.block_instance_segmentation import BlockDetector


def test_recording_roundtrip_and_diagnostic_center(config, tmp_path):
    f = synthetic_frame()
    path = tmp_path / "frame.npz"
    save_recording(path, f)
    replay = RecordedCamera([path]).get_synced_rgbd()
    np.testing.assert_array_equal(replay.rgb, f.rgb)
    d = next(d for d in BlockDetector(config["vision"]).detect(replay) if d.color == "green")
    # Explicit synthetic camera looking down from z=1; no real calibration claim.
    m = np.diag([1., -1., -1., 1.])
    m[2, 3] = 1
    t = RigidTransform("world", f.frame_id, m, "synthetic")
    pose = localize_top_face(d, t, outward_normal_target=[0, 0, 1], edge_m=.05,
                            top_face_confirmed=True, max_tf_delta_s=.02)
    assert pose.center_m[2] == pytest.approx(.475)
    assert pose.orientation_xyzw is None and not pose.control_ready
    with pytest.raises(ValueError):
        localize_top_face(d, t, outward_normal_target=[0, 0, 1], edge_m=.05,
                          top_face_confirmed=False, max_tf_delta_s=.02)


def test_mock_devices_are_explicit_software_fixtures():
    arm, hand = MockArm([0.] * 7), MockHand()
    arm.simulate_joint_target([.1] * 7)
    hand.simulate_preset("MOCK_HOLD")
    assert arm.get_joint_state() == (.1,) * 7
    assert not hand.get_state()["contact_confirmed"]
    assert not arm.hardware_enabled and not hand.hardware_enabled
    with pytest.raises(ValueError): hand.simulate_preset("real_grasp")
