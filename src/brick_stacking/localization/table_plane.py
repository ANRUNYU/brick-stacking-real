"""Offline RANSAC plane fitting. Normal sign needs an explicit reference vector."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class TablePlane:
    normal: tuple[float, float, float]
    offset_m: float
    inlier_ratio: float
    rms_m: float

    def heights(self, points):
        return np.asarray(points) @ np.asarray(self.normal) + self.offset_m


def fit_table_plane(points, *, normal_hint, distance_threshold_m, iterations, min_inlier_ratio, seed=0,
                    confidence=None, statistics=None):
    p = np.asarray(points, float)
    hint = np.asarray(normal_hint, float)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all() or len(p) < 3:
        raise ValueError("at least three finite xyz samples required")
    if hint.shape != (3,) or not np.isfinite(hint).all() or np.linalg.norm(hint) < 1e-12:
        raise ValueError("normal sign reference required")
    if not np.isfinite(distance_threshold_m) or distance_threshold_m <= 0 or iterations < 1 or not 0 < min_inlier_ratio <= 1:
        raise ValueError("invalid RANSAC parameters")
    if confidence is not None and (not np.isfinite(confidence) or not 0 < confidence < 1):
        raise ValueError('RANSAC confidence must be between zero and one')
    rng, best = np.random.default_rng(seed), np.zeros(len(p), bool)
    limit=iterations
    for trial in range(iterations):
        a, b, c = p[rng.choice(len(p), 3, replace=False)]
        n = np.cross(b - a, c - a)
        norm = np.linalg.norm(n)
        if norm < 1e-12:
            continue
        n /= norm
        mask = np.abs((p - a) @ n) <= distance_threshold_m
        if mask.sum() > best.sum():
            best = mask
            if confidence is not None:
                success=float(best.mean())**3
                required=(1 if success>=1 else int(np.ceil(np.log1p(-confidence)/np.log1p(-success))))
                limit=min(limit,max(64,required))
        if trial+1>=limit:
            break
    if statistics is not None:
        statistics.update(trials=trial+1,budget=iterations,confidence=confidence)
    if best.sum() < 3 or best.mean() < min_inlier_ratio:
        raise ValueError("no sufficiently supported plane")
    center = p[best].mean(axis=0)
    _, singular, vh = np.linalg.svd(p[best] - center, full_matrices=False)
    if singular[1] < 1e-10:
        raise ValueError("collinear plane samples")
    n = vh[-1]
    if n @ hint < 0:
        n = -n
    residual = (p - center) @ n
    inliers = np.abs(residual) <= distance_threshold_m
    if inliers.mean() < min_inlier_ratio:
        raise ValueError("refined plane lacks support")
    return TablePlane(tuple(n.tolist()), float(-n @ center), float(inliers.mean()),
                      float(np.sqrt(np.mean(residual[inliers] ** 2))))
