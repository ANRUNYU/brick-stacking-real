"""Pose dict helpers: metres + quaternion_xyzw (authoritative) / extrinsic ZYX display."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from brick_stacking.localization.rigid_transforms import RigidTransform


def _as_unit_quat(xyzw: Sequence[float]) -> tuple[float, float, float, float]:
    q = np.asarray(xyzw, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all():
        raise ValueError("quaternion_xyzw must be four finite floats")
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        raise ValueError("quaternion_xyzw must be non-zero")
    q = q / n
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def matrix_from_quat_xyzw(xyzw: Sequence[float]) -> np.ndarray:
    x, y, z, w = _as_unit_quat(xyzw)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def quat_xyzw_from_matrix(r: np.ndarray) -> tuple[float, float, float, float]:
    m = np.asarray(r, dtype=float)
    if m.shape != (3, 3) or not np.isfinite(m).all():
        raise ValueError("3x3 rotation required")
    tr = float(m[0, 0] + m[1, 1] + m[2, 2])
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    return _as_unit_quat((x, y, z, w))


def extrinsic_zyx_from_matrix(r: np.ndarray) -> tuple[float, float, float]:
    """Return (rz, ry, rx) for R = Rz(rz) Ry(ry) Rx(rx)."""
    m = np.asarray(r, dtype=float)
    sy = -float(m[2, 0])
    cy = math.sqrt(max(0.0, 1.0 - sy * sy))
    if cy > 1e-8:
        ry = math.asin(np.clip(sy, -1.0, 1.0))
        rx = math.atan2(float(m[2, 1]), float(m[2, 2]))
        rz = math.atan2(float(m[1, 0]), float(m[0, 0]))
    else:
        ry = math.copysign(math.pi / 2.0, sy)
        rx = math.atan2(-float(m[0, 1]), float(m[1, 1]))
        rz = 0.0
    return (rz, ry, rx)


def matrix_from_extrinsic_zyx(rz: float, ry: float, rx: float) -> np.ndarray:
    cz, sz = math.cos(rz), math.sin(rz)
    cy, sy = math.cos(ry), math.sin(ry)
    cx, sx = math.cos(rx), math.sin(rx)
    rz_m = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=float)
    ry_m = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=float)
    rx_m = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=float)
    return rz_m @ ry_m @ rx_m


def homogeneous(translation_m: Sequence[float], quat_xyzw: Sequence[float]) -> np.ndarray:
    t = np.asarray(translation_m, dtype=float)
    if t.shape != (3,) or not np.isfinite(t).all():
        raise ValueError("translation_m must be three finite metres")
    m = np.eye(4)
    m[:3, :3] = matrix_from_quat_xyzw(quat_xyzw)
    m[:3, 3] = t
    return m


def pose_dict_from_matrix(
    matrix: np.ndarray,
    *,
    include_rpy: bool = True,
) -> dict[str, Any]:
    m = np.asarray(matrix, dtype=float)
    if m.shape != (4, 4):
        raise ValueError("4x4 homogeneous matrix required")
    quat = quat_xyzw_from_matrix(m[:3, :3])
    out: dict[str, Any] = {
        "translation_m": [float(m[0, 3]), float(m[1, 3]), float(m[2, 3])],
        "quaternion_xyzw": list(quat),
    }
    if include_rpy:
        out["rpy_extrinsic_zyx_rad"] = list(extrinsic_zyx_from_matrix(m[:3, :3]))
    return out


def transform_from_pose_dict(
    pose: dict[str, Any],
    *,
    parent_frame: str,
    child_frame: str,
    source: str = "derived_unapproved",
    calibration_id: str | None = None,
) -> RigidTransform:
    if "quaternion_xyzw" in pose:
        quat = pose["quaternion_xyzw"]
    elif "rpy_extrinsic_zyx_rad" in pose:
        rz, ry, rx = pose["rpy_extrinsic_zyx_rad"]
        quat = quat_xyzw_from_matrix(matrix_from_extrinsic_zyx(float(rz), float(ry), float(rx)))
    else:
        raise ValueError("pose needs quaternion_xyzw or rpy_extrinsic_zyx_rad")
    return RigidTransform(
        parent_frame,
        child_frame,
        homogeneous(pose["translation_m"], quat),
        source,
        calibration_id,
    )


def translation_error_m(a: RigidTransform, b: RigidTransform) -> float:
    if a.target_frame != b.target_frame or a.source_frame != b.source_frame:
        raise ValueError("frame mismatch for translation error")
    return float(np.linalg.norm(a.matrix[:3, 3] - b.matrix[:3, 3]))
