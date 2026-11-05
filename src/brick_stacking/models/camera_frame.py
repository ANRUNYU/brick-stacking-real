"""Rectified, registered RGB-D contract; all depth values are optical Z in metres."""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class CameraFrame:
    rgb: np.ndarray
    depth_m: np.ndarray
    k: np.ndarray
    camera_id: str
    frame_id: str
    stamp_s: float
    clock_domain: str
    source: str
    registered: bool
    rectified: bool

    def __post_init__(self):
        rgb = np.array(self.rgb, copy=True)
        depth = np.array(self.depth_m, dtype=float, copy=True)
        k = np.array(self.k, dtype=float, copy=True)
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("rgb must be HxWx3 uint8 RGB, not BGR")
        if min(rgb.shape[:2]) < 1 or depth.shape != rgb.shape[:2]:
            raise ValueError("RGB/depth dimensions differ or are empty")
        if k.shape != (3, 3) or not np.isfinite(k).all():
            raise ValueError("K must be finite 3x3")
        if k[0, 0] <= 0 or k[1, 1] <= 0 or not np.allclose(k[2], [0, 0, 1]):
            raise ValueError("invalid focal lengths or homogeneous row")
        if abs(k[0, 1]) > 1e-9 or abs(k[1, 0]) > 1e-9:
            raise ValueError("skew intrinsics unsupported; rectify first")
        if not math.isfinite(self.stamp_s) or self.stamp_s < 0:
            raise ValueError("invalid capture timestamp")
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.camera_id, self.frame_id, self.clock_domain, self.source)):
            raise ValueError("camera/frame/clock/source required")
        if self.registered is not True or self.rectified is not True:
            raise ValueError("requires depth registered to rectified RGB optical frame")
        for name, value in (("rgb", rgb), ("depth_m", depth), ("k", k)):
            value.setflags(write=False)
            object.__setattr__(self, name, value)
