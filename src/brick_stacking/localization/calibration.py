"""Offline candidate solvers. Outputs never grant hardware approval."""
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def _points(value):
    p = np.asarray(value, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 4 or not np.isfinite(p).all():
        raise ValueError("at least four finite xyz points in metres required")
    if np.linalg.matrix_rank(p - p.mean(axis=0), tol=1e-8) < 2:
        raise ValueError("collinear or repeated samples")
    return p


def solve_point_pairs(source_m, target_m, *, source_frame, target_frame, candidate_id):
    """Kabsch fit T_target_source; planar noncollinear targets are allowed."""
    a, b = _points(source_m), _points(target_m)
    if a.shape != b.shape or not candidate_id:
        raise ValueError("paired samples and candidate identity required")
    u, _, vt = np.linalg.svd((a-a.mean(0)).T @ (b-b.mean(0)))
    correction = np.eye(3)
    correction[2, 2] = np.linalg.det(vt.T @ u.T)
    r = vt.T @ correction @ u.T
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = r, b.mean(0) - r @ a.mean(0)
    return RigidTransform(target_frame, source_frame, m, "offline_candidate", candidate_id)


def error_report(transform, source_m, target_m):
    """Caller must supply held-out physical points, not training residuals."""
    a, b = _points(source_m), _points(target_m)
    if a.shape != b.shape:
        raise ValueError("paired validation points required")
    e = np.linalg.norm(transform.apply(a) - b, axis=1)
    return {"n": len(e), "rmse_m": float(np.sqrt(np.mean(e**2))),
            "p50_m": float(np.median(e)), "p95_m": float(np.percentile(e, 95)),
            "max_m": float(e.max()), "approved": False}


def solve_pivot_tcp(base_flange_samples):
    """Solve R_i p_flange_tcp + t_i = fixed pivot in base, metres.

    Returns translation only; TCP rotation is unobservable in a pivot test.
    """
    samples = tuple(base_flange_samples)
    if len(samples) < 4:
        raise ValueError("at least four diverse orientations required")
    if len({(t.target_frame, t.source_frame) for t in samples}) != 1:
        raise ValueError("inconsistent flange/base frames")
    a = np.vstack([np.hstack((t.matrix[:3, :3], -np.eye(3))) for t in samples])
    b = np.concatenate([-t.matrix[:3, 3] for t in samples])
    if np.linalg.matrix_rank(a, tol=1e-8) < 6 or np.linalg.cond(a) > 1e6:
        raise ValueError("degenerate pivot orientations")
    x, _, _, _ = np.linalg.lstsq(a, b, rcond=None)
    residual = (a @ x - b).reshape(-1, 3)
    return {"tcp_translation_flange_m": x[:3].tolist(), "pivot_base_m": x[3:].tolist(),
            "tcp_orientation_xyzw": None, "approved": False,
            "fit_rmse_m": float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))}


def tcp_target_for_block(world_block, tcp_block):
    """T_world_tcp = T_world_block @ inverse(T_tcp_block)."""
    return world_block.compose(tcp_block.inverse())
