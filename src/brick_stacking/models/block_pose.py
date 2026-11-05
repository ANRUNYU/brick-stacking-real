from dataclasses import dataclass


@dataclass(frozen=True)
class BlockPose:
    candidate_id: str
    frame_id: str
    stamp_s: float
    center_m: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float] | None
    calibration_id: str | None
    source: str
    control_ready: bool = False
