"""Explicit top-face hypothesis, diagnostic only; no invented orientation."""
import numpy as np
from brick_stacking.models.block_detection import SegmentationStatus
from brick_stacking.models.block_pose import BlockPose


def localize_top_face(detection, transform, *, outward_normal_target, edge_m,
                      top_face_confirmed, max_tf_delta_s):
    if top_face_confirmed is not True:
        raise ValueError("top face hypothesis must be confirmed by caller")
    if detection.status != SegmentationStatus.UNAMBIGUOUS or detection.surface_point_camera_m is None:
        raise ValueError("requires a valid single-face candidate")
    if detection.frame_id != transform.source_frame:
        raise ValueError("camera/transform frame mismatch")
    transform.require_capture_time(detection.stamp_s, detection.clock_domain, max_tf_delta_s)
    n = np.asarray(outward_normal_target, float)
    if n.shape != (3,) or not np.isfinite(n).all() or not np.isclose(np.linalg.norm(n), 1):
        raise ValueError("explicit unit table outward normal required")
    if not np.isfinite(edge_m) or edge_m <= 0:
        raise ValueError("positive edge length required")
    center = transform.apply(detection.surface_point_camera_m) - n * edge_m / 2
    return BlockPose(detection.candidate_id, transform.target_frame, detection.stamp_s,
                     tuple(center.tolist()), None, transform.calibration_id,
                     "derived_top_face_hypothesis", False)
