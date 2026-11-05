from dataclasses import dataclass
from enum import Enum


class SegmentationStatus(str, Enum):
    UNAMBIGUOUS = "UNAMBIGUOUS"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_DEPTH = "INVALID_DEPTH"


@dataclass(frozen=True)
class BlockDetection:
    """Frame-local candidate. candidate_id is never a persistent object identity."""
    candidate_id: str
    color: str
    camera_id: str
    frame_id: str
    stamp_s: float
    clock_domain: str
    centroid_uv: tuple[float, float]
    bbox_xywh: tuple[int, int, int, int]
    area_px: int
    valid_depth_ratio: float
    status: SegmentationStatus
    reason: str
    surface_point_camera_m: tuple[float, float, float] | None
    estimated_span_m: tuple[float, float] | None
    control_ready: bool = False
