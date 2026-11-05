import cv2
import numpy as np
import pytest
from brick_stacking.vision.color_segmentation import segment_colors
from brick_stacking.vision.block_instance_segmentation import BlockDetector
from brick_stacking.app.offline_runner import synthetic_frame
from brick_stacking.models.camera_frame import CameraFrame


def test_four_colors_and_red_hue_wrap(config):
    hsv = np.uint8([[[0, 255, 255], [179, 255, 255], [30, 255, 255],
                     [60, 255, 255], [120, 255, 255]]])
    masks = segment_colors(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), config["vision"]["hsv"])
    assert np.count_nonzero(masks["red"]) == 2
    assert all(np.count_nonzero(masks[c]) == 1 for c in ["yellow", "green", "blue"])


def test_isolated_four_faces_and_ambiguous_connected_pair(config):
    detections = BlockDetector(config["vision"]).detect(synthetic_frame())
    assert len(detections) == 5
    assert sum(d.status == "UNAMBIGUOUS" for d in detections) == 4
    ambiguous = [d for d in detections if d.status == "AMBIGUOUS"]
    assert len(ambiguous) == 1 and ambiguous[0].color == "red"
    assert all(not d.control_ready for d in detections)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_depth_preserves_candidate_but_not_pose(config, bad):
    f = synthetic_frame()
    depth = np.full_like(f.depth_m, bad)
    frame = CameraFrame(f.rgb, depth, f.k, f.camera_id, f.frame_id, f.stamp_s,
                        f.clock_domain, f.source, True, True)
    detections = BlockDetector(config["vision"]).detect(frame)
    assert len(detections) == 5
    assert all(d.status == "INVALID_DEPTH" and d.surface_point_camera_m is None for d in detections)


def test_bad_profile_rejected(config):
    config["vision"]["min_valid_depth_ratio"] = 2
    with pytest.raises(ValueError):
        BlockDetector(config["vision"])
