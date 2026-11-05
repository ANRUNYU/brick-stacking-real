"""T_target_source maps source points into target. No missing-TF fallback."""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class RigidTransform:
    target_frame: str
    source_frame: str
    matrix: np.ndarray
    source: str
    calibration_id: str | None = None
    approved: bool = False
    stamp_s: float | None = None  # None only for declared static transforms
    clock_domain: str | None = None

    def __post_init__(self):
        m = np.array(self.matrix, float, copy=True)
        if not all(isinstance(x, str) and x.strip() for x in (self.target_frame, self.source_frame, self.source)):
            raise ValueError("frame and provenance required")
        if m.shape != (4, 4) or not np.isfinite(m).all() or not np.allclose(m[3], [0, 0, 0, 1]):
            raise ValueError("finite homogeneous 4x4 required")
        r = m[:3, :3]
        if not np.allclose(r.T @ r, np.eye(3), atol=1e-7) or not np.isclose(np.linalg.det(r), 1, atol=1e-7):
            raise ValueError("rotation must be SO(3), no scale/reflection")
        if self.approved and (not self.calibration_id or self.source != "real_measured"):
            raise ValueError("approved transform needs real measurement and calibration identity")
        if self.stamp_s is not None and (not math.isfinite(self.stamp_s) or self.stamp_s < 0 or not self.clock_domain):
            raise ValueError("dynamic transform needs finite timestamp and clock domain")
        m.setflags(write=False)
        object.__setattr__(self, "matrix", m)

    def inverse(self):
        m = np.eye(4)
        m[:3, :3] = self.matrix[:3, :3].T
        m[:3, 3] = -m[:3, :3] @ self.matrix[:3, 3]
        return RigidTransform(self.source_frame, self.target_frame, m, self.source,
                              self.calibration_id, self.approved, self.stamp_s, self.clock_domain)

    def compose(self, other):
        if self.source_frame != other.target_frame:
            raise ValueError("TF chain frame mismatch")
        dynamic = [t for t in (self, other) if t.stamp_s is not None]
        if len(dynamic) == 2 and (self.clock_domain != other.clock_domain or self.stamp_s != other.stamp_s):
            raise ValueError("dynamic transforms must refer to the same capture instant")
        t = dynamic[0] if dynamic else None
        return RigidTransform(self.target_frame, other.source_frame, self.matrix @ other.matrix,
                              "real_measured" if self.approved and other.approved else "derived_unapproved",
                              "+".join(filter(None, (self.calibration_id, other.calibration_id))) or None,
                              self.approved and other.approved,
                              t.stamp_s if t else None, t.clock_domain if t else None)

    def apply(self, points):
        p = np.asarray(points, float)
        if p.shape[-1:] != (3,) or not np.isfinite(p).all():
            raise ValueError("finite xyz points required")
        return p @ self.matrix[:3, :3].T + self.matrix[:3, 3]

    def require_capture_time(self, stamp_s, clock_domain, max_delta_s):
        if not math.isfinite(max_delta_s) or max_delta_s < 0 or not math.isfinite(stamp_s):
            raise ValueError("invalid time tolerance")
        if self.stamp_s is not None and (self.clock_domain != clock_domain or abs(self.stamp_s - stamp_s) > max_delta_s):
            raise ValueError("stale or clock-mismatched TF")
