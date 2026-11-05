"""Pinhole projection for a validated CameraFrame."""
import numpy as np


def backproject(uv, depth_m, k):
    uv, z, k = np.asarray(uv, float), np.asarray(depth_m, float), np.asarray(k, float)
    if k.shape != (3, 3) or not np.isfinite(k).all() or k[0, 0] <= 0 or k[1, 1] <= 0:
        raise ValueError("invalid intrinsics")
    if not np.allclose(k[2], [0, 0, 1]) or k[0, 1] != 0 or k[1, 0] != 0:
        raise ValueError("requires rectified zero-skew intrinsics")
    if uv.shape[-1:] != (2,) or not np.isfinite(uv).all() or not np.isfinite(z).all() or np.any(z <= 0):
        raise ValueError("finite pixel coordinates and positive optical depth required")
    return np.stack(((uv[..., 0] - k[0, 2]) * z / k[0, 0],
                     (uv[..., 1] - k[1, 2]) * z / k[1, 1],
                     np.broadcast_to(z, uv.shape[:-1])), axis=-1)
