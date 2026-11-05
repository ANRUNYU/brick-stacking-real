"""Conservative head/top-view prototype. Touching components stay ambiguous.

Metric span check assumes a near-frontoparallel visible square face. It is a
candidate quality filter, not a general six-degree cube pose estimator.
"""
import cv2
import numpy as np
from brick_stacking.models.block_detection import BlockDetection, SegmentationStatus
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.vision.color_segmentation import segment_colors


class BlockDetector:
    def __init__(self, profile):
        self.profile = profile
        for key in ("min_area_px", "min_valid_depth_ratio", "min_depth_m", "max_depth_m",
                    "nominal_edge_m", "span_relative_tolerance", "max_depth_spread_m", "hsv"):
            if key not in profile:
                raise ValueError(f"missing vision parameter: {key}")
        vals = [profile[k] for k in ("min_area_px", "min_depth_m", "max_depth_m", "nominal_edge_m", "max_depth_spread_m")]
        if not np.isfinite(vals).all() or min(vals) <= 0 or profile["min_depth_m"] >= profile["max_depth_m"]:
            raise ValueError("invalid vision dimensions")
        if not 0 < profile["min_valid_depth_ratio"] <= 1 or not 0 < profile["span_relative_tolerance"] < 1:
            raise ValueError("invalid quality ratios")

    def detect(self, frame):
        p, detections = self.profile, []
        for color, mask in segment_colors(frame.rgb, p["hsv"]).items():
            count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
            for label in range(1, count):
                x, y, w, h, area = map(int, stats[label])
                if area < p["min_area_px"]:
                    continue
                component = labels == label
                z = frame.depth_m[component]
                valid = np.isfinite(z) & (z >= p["min_depth_m"]) & (z <= p["max_depth_m"])
                ratio = float(valid.mean())
                status, reason = SegmentationStatus.INVALID_DEPTH, "insufficient_valid_depth"
                surface, span = None, None
                if ratio >= p["min_valid_depth_ratio"]:
                    rows, cols = np.where(component)
                    xyz = backproject(np.column_stack((cols[valid], rows[valid])), z[valid], frame.k)
                    surface = tuple(np.median(xyz, axis=0).tolist())
                    depth = float(np.median(z[valid]))
                    span = (w * depth / frame.k[0, 0], h * depth / frame.k[1, 1])
                    span_ok = all(abs(v / p["nominal_edge_m"] - 1) <= p["span_relative_tolerance"] for v in span)
                    spread_ok = float(np.ptp(np.quantile(z[valid], [.1, .9]))) <= p["max_depth_spread_m"]
                    status = SegmentationStatus.UNAMBIGUOUS if span_ok and spread_ok else SegmentationStatus.AMBIGUOUS
                    reason = "single_face_candidate_unverified" if span_ok and spread_ok else "touching_or_nonfrontal_or_irregular_geometry"
                detections.append(BlockDetection(
                    f"{color}_{label}", color, frame.camera_id, frame.frame_id, frame.stamp_s,
                    frame.clock_domain, tuple(centers[label]), (x, y, w, h), area,
                    ratio, status, reason, surface, span))
        return detections
