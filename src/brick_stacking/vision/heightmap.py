import numpy as np


def build_heightmap(points_table, *, bounds_xy_m, resolution_m):
    """Table-frame XYZ -> maximum height; unobserved cells remain NaN."""
    p, bounds = np.asarray(points_table, float), np.asarray(bounds_xy_m, float)
    if p.ndim != 2 or p.shape[1] != 3 or bounds.shape != (2, 2) or not np.isfinite(bounds).all():
        raise ValueError("invalid points or xy bounds")
    if not np.isfinite(resolution_m) or resolution_m <= 0 or np.any(bounds[:, 1] <= bounds[:, 0]):
        raise ValueError("invalid grid bounds/resolution")
    shape_xy = np.ceil((bounds[:, 1] - bounds[:, 0]) / resolution_m).astype(int)
    if np.prod(shape_xy) > 10_000_000:
        raise ValueError("heightmap too large")
    grid = np.full((shape_xy[1], shape_xy[0]), -np.inf)
    valid = np.isfinite(p).all(axis=1) & (p[:, :2] >= bounds[:, 0]).all(axis=1) & (p[:, :2] < bounds[:, 1]).all(axis=1)
    q = p[valid]
    index = np.floor((q[:, :2] - bounds[:, 0]) / resolution_m).astype(int)
    np.maximum.at(grid, (index[:, 1], index[:, 0]), q[:, 2])
    grid[~np.isfinite(grid)] = np.nan
    return grid
