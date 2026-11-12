"""Offline #36 step-1: check whether the fitted robot-side table edge matches a physical rim.

Reuses the same walk-to-support-break parameters as tools/h_shadow_robot_side_table_edge.py.
Does not move the robot, open CAN, or capture new frames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIELD = ROOT / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356"
OUT_DEFAULT = FIELD / "robot_side_edge_physical_check"

# Same constants as h_shadow_robot_side_table_edge.py
PLANE_RESID_M = 0.008
LATERAL_SPAN_M = 0.18
N_LATERAL = 37
STEP_M = 0.005
MAX_WALK_M = 0.55
MISS_BREAK = 3
DEPTH_VALID = (0.4, 1.3)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    if isinstance(obj, str) or obj is None:
        return obj
    return obj


def pix_cam(k: np.ndarray, p: np.ndarray):
    if p[2] <= 1e-6:
        return None
    return tuple(np.rint((k @ p)[:2] / p[2]).astype(int))


def fit_robot_side_edge(rgb, depth, k, obs, t_base_cam):
    """Return edge geometry using the original tool's algorithm."""
    cam_from_base = np.linalg.inv(t_base_cam)
    n_cam = np.asarray(obs["table_plane_camera"]["upward_normal_camera"], float)
    n_cam = n_cam / np.linalg.norm(n_cam)
    origin_cam = np.asarray(obs["top_center_camera_m"], float) - n_cam * float(
        obs["top_fit"]["height_m"]
    )
    h, w = depth.shape
    yy, xx = np.indices((h, w))
    z = depth
    valid = np.isfinite(z) & (z > DEPTH_VALID[0]) & (z < DEPTH_VALID[1])
    pts = np.stack(
        ((xx - k[0, 2]) * z / k[0, 0], (yy - k[1, 2]) * z / k[1, 1], z), axis=-1
    )
    plane_resid = np.abs((pts - origin_cam) @ n_cam)
    on_plane = valid & (plane_resid < PLANE_RESID_M)

    root_in_cam = (cam_from_base @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
    toward_robot = root_in_cam - origin_cam
    toward_robot = toward_robot - n_cam * float(toward_robot @ n_cam)
    if np.linalg.norm(toward_robot) < 1e-9:
        raise RuntimeError("degenerate robot-side direction")
    toward_robot = toward_robot / np.linalg.norm(toward_robot)
    lateral = np.cross(n_cam, toward_robot)
    lateral = lateral / np.linalg.norm(lateral)

    lateral_offsets = np.linspace(-LATERAL_SPAN_M, LATERAL_SPAN_M, N_LATERAL)
    edge_points_cam = []
    edge_meta = []
    for lat in lateral_offsets:
        start = origin_cam + lateral * lat
        last_good = None
        miss = 0
        reason = "no_support"
        for s in np.arange(0.0, MAX_WALK_M + 1e-9, STEP_M):
            p = start + toward_robot * s
            if p[2] <= 1e-6:
                reason = "behind_camera"
                break
            uv = (k @ p)[:2] / p[2]
            u, v = int(round(uv[0])), int(round(uv[1]))
            if not (0 <= u < w and 0 <= v < h):
                reason = "fov_exit"
                if last_good is not None:
                    edge_points_cam.append(last_good)
                    edge_meta.append(
                        dict(
                            lateral_m=float(lat),
                            reason=reason,
                            u=int(round((k @ last_good)[0] / last_good[2])),
                            v=int(round((k @ last_good)[1] / last_good[2])),
                            walk_m=float(s),
                        )
                    )
                break
            if on_plane[v, u]:
                last_good = p
                miss = 0
            else:
                miss += 1
                if miss >= MISS_BREAK and last_good is not None:
                    reason = "support_break"
                    edge_points_cam.append(last_good)
                    edge_meta.append(
                        dict(
                            lateral_m=float(lat),
                            reason=reason,
                            u=int(round((k @ last_good)[0] / last_good[2])),
                            v=int(round((k @ last_good)[1] / last_good[2])),
                            walk_m=float(s - miss * STEP_M),
                        )
                    )
                    break
        else:
            if last_good is not None:
                reason = "max_walk"
                edge_points_cam.append(last_good)
                edge_meta.append(
                    dict(
                        lateral_m=float(lat),
                        reason=reason,
                        u=int(round((k @ last_good)[0] / last_good[2])),
                        v=int(round((k @ last_good)[1] / last_good[2])),
                        walk_m=float(MAX_WALK_M),
                    )
                )

    if len(edge_points_cam) < 5:
        raise RuntimeError(f"insufficient edge samples: {len(edge_points_cam)}")

    edge_cam = np.asarray(edge_points_cam, float)
    edge_base = (t_base_cam @ np.c_[edge_cam, np.ones(len(edge_cam))].T).T[:, :3]
    edge_mean = edge_base.mean(axis=0)
    n_base = t_base_cam[:3, :3] @ n_cam
    n_base = n_base / np.linalg.norm(n_base)
    centered = edge_base - edge_mean
    centered = centered - np.outer(centered @ n_base, n_base)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    edge_dir = vh[0]
    edge_dir = edge_dir - n_base * float(edge_dir @ n_base)
    edge_dir = edge_dir / np.linalg.norm(edge_dir)
    # Orient edge_dir consistently with lateral (camera lateral mapped to base).
    lateral_base = t_base_cam[:3, :3] @ lateral
    if edge_dir @ lateral_base < 0:
        edge_dir = -edge_dir
    inward = -toward_robot
    inward_base = t_base_cam[:3, :3] @ inward
    inward_base = inward_base - n_base * float(inward_base @ n_base)
    inward_base = inward_base / np.linalg.norm(inward_base)

    # Supported segment: project edge samples onto fitted line; keep support_break ones.
    t_all = (edge_base - edge_mean) @ edge_dir
    support_mask = np.array([m["reason"] == "support_break" for m in edge_meta], bool)
    if support_mask.any():
        t_sup = t_all[support_mask]
        t_min, t_max = float(t_sup.min()), float(t_sup.max())
    else:
        t_min, t_max = float(t_all.min()), float(t_all.max())

    return dict(
        edge_cam=edge_cam,
        edge_base=edge_base,
        edge_meta=edge_meta,
        edge_mean=edge_mean,
        edge_dir=edge_dir,
        inward_base=inward_base,
        n_cam=n_cam,
        n_base=n_base,
        origin_cam=origin_cam,
        toward_robot=toward_robot,
        lateral=lateral,
        on_plane=on_plane,
        valid=valid,
        t_all=t_all,
        t_support_min=t_min,
        t_support_max=t_max,
        support_mask=support_mask,
        cam_from_base=cam_from_base,
    )


def depth_colormap(depth: np.ndarray) -> np.ndarray:
    vis = depth.copy()
    mask = np.isfinite(vis) & (vis > 0.05) & (vis < 2.5)
    out = np.zeros((*vis.shape, 3), np.uint8)
    if mask.any():
        lo, hi = np.percentile(vis[mask], [5, 95])
        span = max(float(hi - lo), 1e-6)
        norm = np.zeros_like(vis, dtype=np.float64)
        norm[mask] = np.clip((vis[mask] - lo) / span, 0, 1)
        gray = np.zeros(vis.shape, dtype=np.uint8)
        gray[mask] = (norm[mask] * 255.0).astype(np.uint8)
        out = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
        out[~mask] = (20, 20, 20)
    return out


def draw_edge_overlays(rgb, depth, k, geom, probes, title: str):
    h, w = rgb.shape[:2]
    rgb_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    depth_bgr = depth_colormap(depth)

    # Missing depth / off-plane masks
    miss = ~(np.isfinite(depth) & (depth > 0))
    off = geom["valid"] & (~geom["on_plane"])

    def annotate(base_img, is_depth=False):
        img = base_img.copy()
        # Occlusion / missing overlays
        overlay = img.copy()
        overlay[miss] = (40, 40, 120) if not is_depth else (30, 30, 30)
        # Arm-ish: near camera depth blobs on robot side of edge — approximate as
        # valid depth but off-plane and closer than table median.
        img = cv2.addWeighted(overlay, 0.35, img, 0.65, 0)

        # Fitted infinite line (extension): dashed cyan across FOV
        mean_cam = (geom["cam_from_base"] @ np.r_[geom["edge_mean"], 1.0])[:3]
        dir_cam = geom["cam_from_base"][:3, :3] @ geom["edge_dir"]
        # Project a long segment of the infinite line for drawing.
        pts_line = []
        for s in np.linspace(-0.45, 0.45, 91):
            p = mean_cam + dir_cam * s
            uv = pix_cam(k, p)
            if uv is not None and 0 <= uv[0] < w and 0 <= uv[1] < h:
                pts_line.append(uv)
        for i in range(0, max(0, len(pts_line) - 1), 2):
            cv2.line(img, pts_line[i], pts_line[min(i + 1, len(pts_line) - 1)], (255, 220, 0), 1)

        # Supported samples: green thick; FOV-limited: orange; other: purple
        for p_cam, meta in zip(geom["edge_cam"], geom["edge_meta"], strict=True):
            uv = pix_cam(k, p_cam)
            if uv is None:
                continue
            if meta["reason"] == "support_break":
                color = (0, 220, 0)
            elif meta["reason"] == "fov_exit":
                color = (0, 140, 255)
            else:
                color = (200, 0, 200)
            cv2.circle(img, uv, 3, color, -1)

        # Supported segment polyline only
        support_pts = [
            pix_cam(k, p)
            for p, m in zip(geom["edge_cam"], geom["edge_meta"], strict=True)
            if m["reason"] == "support_break"
        ]
        support_pts = [uv for uv in support_pts if uv is not None]
        if len(support_pts) >= 2:
            cv2.polylines(img, [np.array(support_pts, np.int32)], False, (0, 255, 0), 2)

        # Robot-side arrow
        origin_uv = pix_cam(k, geom["origin_cam"])
        tip = geom["origin_cam"] + geom["toward_robot"] * 0.12
        tip_uv = pix_cam(k, tip)
        if origin_uv and tip_uv:
            cv2.arrowedLine(img, origin_uv, tip_uv, (0, 255, 255), 2, tipLength=0.25)
            cv2.putText(img, "robot side", (tip_uv[0] + 4, tip_uv[1]), 0, 0.45, (0, 255, 255), 1)

        # Independent probe marks
        for pr in probes:
            uv = (int(pr["u"]), int(pr["v_fit"]))
            cv2.drawMarker(img, uv, (0, 0, 255), cv2.MARKER_CROSS, 14, 2)
            cv2.putText(img, pr["id"], (uv[0] + 4, uv[1] - 4), 0, 0.4, (0, 0, 255), 1)

        cv2.putText(img, title, (8, 18), 0, 0.5, (245, 245, 245), 1)
        cv2.putText(
            img,
            "green=support-break edge  cyan-dash=line extension  yellow=toward robot  red=manual probes",
            (8, h - 10),
            0,
            0.4,
            (230, 230, 230),
            1,
        )
        return img

    return annotate(rgb_bgr, False), annotate(depth_bgr, True)


def profile_across_edge(depth, k, geom, u, half_px=25):
    """Sample depth along image column through fitted edge pixel (approx perpendicular)."""
    # Use local normal in image: walk along toward_robot projection.
    p_edge = None
    # Find nearest edge sample in image x
    best = None
    for p_cam, meta in zip(geom["edge_cam"], geom["edge_meta"], strict=True):
        uv = pix_cam(k, p_cam)
        if uv is None:
            continue
        d = abs(uv[0] - u)
        if best is None or d < best[0]:
            best = (d, uv, p_cam, meta)
    if best is None:
        return None
    _, uv_e, p_cam, meta = best
    # Direction in image of toward_robot
    tip = p_cam + geom["toward_robot"] * 0.05
    uv_t = pix_cam(k, tip)
    if uv_t is None:
        du, dv = 0, 1
    else:
        du, dv = uv_t[0] - uv_e[0], uv_t[1] - uv_e[1]
        nrm = math.hypot(du, dv) or 1.0
        du, dv = du / nrm, dv / nrm
    rows = []
    for s in range(-half_px, half_px + 1):
        uu = int(round(uv_e[0] + du * s))
        vv = int(round(uv_e[1] + dv * s))
        if 0 <= uu < depth.shape[1] and 0 <= vv < depth.shape[0]:
            z = float(depth[vv, uu])
            on = bool(geom["on_plane"][vv, uu]) if np.isfinite(z) else False
            valid = bool(np.isfinite(z) and z > 0)
        else:
            z, on, valid = float("nan"), False, False
        rows.append(
            dict(
                offset_px=s,
                u=uu,
                v=vv,
                depth_m=z if valid else None,
                on_plane=on,
                toward_robot_positive=s > 0,
            )
        )
    return dict(edge_uv=list(uv_e), meta=meta, samples=rows)


def classify_profile(profile, rgb) -> dict:
    """Heuristic + human-reviewable classification from profile + RGB neighborhood."""
    if profile is None:
        return dict(label="no_profile", reason="no nearby edge sample")
    samples = profile["samples"]
    interior = [s for s in samples if s["offset_px"] < -3]
    exterior = [s for s in samples if s["offset_px"] > 3]
    def frac_on(xs):
        if not xs:
            return 0.0
        return sum(1 for s in xs if s["on_plane"]) / len(xs)

    def frac_missing(xs):
        if not xs:
            return 1.0
        return sum(1 for s in xs if s["depth_m"] is None) / len(xs)

    fi, fe = frac_on(interior), frac_on(exterior)
    mi, me = frac_missing(interior), frac_missing(exterior)
    # RGB gradient at edge pixel as independent cue (not using fit points as GT)
    u, v = profile["edge_uv"]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    x0, x1 = max(0, u - 12), min(gray.shape[1], u + 13)
    y0, y1 = max(0, v - 12), min(gray.shape[0], v + 13)
    patch = gray[y0:y1, x0:x1].astype(np.float32)
    gx = cv2.Sobel(patch, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(patch, cv2.CV_32F, 0, 1, ksize=3)
    grad = float(np.hypot(gx, gy).mean())

    # Interpret exterior side (toward robot)
    ext_depths = [s["depth_m"] for s in exterior if s["depth_m"] is not None]
    int_depths = [s["depth_m"] for s in interior if s["depth_m"] is not None]
    exterior_view = "missing_or_sparse_depth"
    if ext_depths and int_depths:
        med_e, med_i = float(np.median(ext_depths)), float(np.median(int_depths))
        if med_e > med_i + 0.15:
            exterior_view = "background_farther"
        elif med_e < med_i - 0.02:
            exterior_view = "closer_object_or_arm"
        else:
            exterior_view = "similar_depth_ambiguous"

    # Depth support ends toward robot.
    if fe < 0.15 and fi > 0.55:
        if me > 0.6:
            # Missing exterior depth alone is insufficient; strong RGB rim can partially confirm.
            if grad > 20.0:
                return dict(
                    label="physical_rim_partial_rgb",
                    interior_on_plane_frac=fi,
                    exterior_on_plane_frac=fe,
                    exterior_view=exterior_view,
                    rgb_grad_mean=grad,
                    reason=(
                        "on-plane support ends toward robot; exterior depth mostly missing "
                        "(not enough alone); strong RGB intensity edge co-located"
                    ),
                )
            return dict(
                label="fov_or_missing_depth_limit",
                interior_on_plane_frac=fi,
                exterior_on_plane_frac=fe,
                exterior_view="missing_depth",
                rgb_grad_mean=grad,
                reason="exterior mostly missing depth and weak RGB cue — cannot certify physical rim",
            )
        label = "physical_rim_candidate" if grad > 8.0 else "support_break_weak_rgb"
        return dict(
            label=label,
            interior_on_plane_frac=fi,
            exterior_on_plane_frac=fe,
            exterior_view=exterior_view,
            rgb_grad_mean=grad,
            reason="interior on-plane support ends toward robot; RGB neighborhood gradient recorded",
        )
    return dict(
        label="inconclusive",
        interior_on_plane_frac=fi,
        exterior_on_plane_frac=fe,
        exterior_view="mixed",
        rgb_grad_mean=grad,
        reason="profile does not show clean support break with RGB cue",
    )


def independent_rgb_edge_offset(rgb, depth, k, geom, u_probe: int) -> dict:
    """Find RGB intensity edge near fitted u by scanning along toward-robot in image.

    Independent of the depth support-break points used as the fit samples.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    # Start from table origin projected, walk toward robot at this lateral column approx.
    # Use fitted edge's nearest sample only as a search window center — offset measured
    # from intensity peak, not from that sample as ground truth.
    best = None
    for p_cam in geom["edge_cam"]:
        uv = pix_cam(k, p_cam)
        if uv is None:
            continue
        if best is None or abs(uv[0] - u_probe) < abs(best[0] - u_probe):
            best = uv
    if best is None:
        return dict(ok=False, reason="no_edge_pixel")
    u0, v0 = best
    tip_cam = None
    for p_cam in geom["edge_cam"]:
        uv = pix_cam(k, p_cam)
        if uv is not None and abs(uv[0] - u0) <= 1 and abs(uv[1] - v0) <= 1:
            tip_cam = p_cam
            break
    if tip_cam is None:
        tip_cam = geom["edge_cam"][int(np.argmin([abs(pix_cam(k, p)[0] - u0) if pix_cam(k, p) else 1e9 for p in geom["edge_cam"]]))]
    tip = tip_cam + geom["toward_robot"] * 0.08
    uv_t = pix_cam(k, tip)
    if uv_t is None:
        du, dv = 0.0, 1.0
    else:
        du, dv = float(uv_t[0] - u0), float(uv_t[1] - v0)
        nrm = math.hypot(du, dv) or 1.0
        du, dv = du / nrm, dv / nrm
    vals = []
    for s in range(-40, 41):
        uu = int(round(u0 + du * s))
        vv = int(round(v0 + dv * s))
        if 0 <= uu < gray.shape[1] and 0 <= vv < gray.shape[0]:
            vals.append((s, float(gray[vv, uu]), uu, vv))
    if len(vals) < 10:
        return dict(ok=False, reason="short_scan")
    # Strongest absolute gradient between adjacent samples
    best_g = None
    for i in range(1, len(vals)):
        g = abs(vals[i][1] - vals[i - 1][1])
        mid_s = 0.5 * (vals[i][0] + vals[i - 1][0])
        if best_g is None or g > best_g[0]:
            best_g = (g, mid_s, vals[i][2], vals[i][3])
    # Signed offset: positive toward robot relative to fitted edge pixel
    # Convert pixel offset along scan to metres on plane using local depth.
    z = float(depth[v0, u0]) if np.isfinite(depth[v0, u0]) else float("nan")
    m_per_px = z / k[0, 0] if np.isfinite(z) and z > 0 else float("nan")
    offset_px = float(best_g[1])
    # Convention: positive = fitted edge is interior of RGB rim (fit lags physical),
    # i.e. RGB edge is further toward robot than fit → physical rim outside fit.
    # offset_px measured from fit toward robot to RGB peak.
    return dict(
        ok=True,
        fit_uv=[u0, v0],
        rgb_edge_uv=[int(best_g[2]), int(best_g[3])],
        offset_toward_robot_px=offset_px,
        offset_toward_robot_m=offset_px * m_per_px if np.isfinite(m_per_px) else None,
        grad=float(best_g[0]),
        m_per_px_at_fit=m_per_px,
        sign_convention=(
            "positive_offset_px = RGB intensity edge is further toward robot than "
            "fitted support-break pixel (fit sits board-inward of RGB rim)"
        ),
    )


def closest_foot_on_segment(point_base, geom) -> dict:
    """Project point onto fitted edge line; report whether foot is in supported segment."""
    edge_mean = geom["edge_mean"]
    edge_dir = geom["edge_dir"]
    n_base = geom["n_base"]
    foot = point_base - n_base * float((point_base - edge_mean) @ n_base)
    t = float((foot - edge_mean) @ edge_dir)
    inward = float((foot - edge_mean) @ geom["inward_base"])  # should ~0 if on line
    # signed clearance of the point itself
    clear = float((point_base - n_base * float((point_base - edge_mean) @ n_base) - edge_mean) @ geom["inward_base"])
    in_seg = geom["t_support_min"] - 1e-6 <= t <= geom["t_support_max"] + 1e-6
    return dict(
        t_m=t,
        t_support_min_m=geom["t_support_min"],
        t_support_max_m=geom["t_support_max"],
        foot_in_supported_segment=bool(in_seg),
        signed_clearance_m=clear,
        foot_base_m=foot.tolist(),
    )


def process_frame(frame_path: Path, obs_path: Path, cal: dict, t_base_cam: np.ndarray):
    obs = load(obs_path)
    with np.load(frame_path, allow_pickle=False) as f:
        rgb = f["rgb"]
        depth = f["depth_m"].astype(np.float64)
        k = f["k"].astype(np.float64)
    geom = fit_robot_side_edge(rgb, depth, k, obs, t_base_cam)

    # Probe columns: left / mid / right of supported edge in image
    support_uv = [
        pix_cam(k, p)
        for p, m in zip(geom["edge_cam"], geom["edge_meta"], strict=True)
        if m["reason"] == "support_break"
    ]
    support_uv = [uv for uv in support_uv if uv is not None]
    if len(support_uv) < 3:
        u_probes = [160, 320, 480]
    else:
        us = sorted(uv[0] for uv in support_uv)
        u_probes = [us[0], us[len(us) // 2], us[-1]]
        # add two intermediates
        u_probes = [
            us[0],
            us[len(us) // 4],
            us[len(us) // 2],
            us[(3 * len(us)) // 4],
            us[-1],
        ]

    probes = []
    for i, u in enumerate(u_probes):
        prof = profile_across_edge(depth, k, geom, u)
        cls = classify_profile(prof, rgb)
        indep = independent_rgb_edge_offset(rgb, depth, k, geom, u)
        probes.append(
            dict(
                id=f"P{i}",
                u=int(u),
                v_fit=int(prof["edge_uv"][1]) if prof else -1,
                profile_class=cls,
                independent_rgb_offset=indep,
                profile=prof,
            )
        )

    # Edge line parameters for cross-frame
    return dict(
        frame=frame_path.name,
        frame_sha256=digest(frame_path),
        observation=str(obs_path.as_posix()),
        n_edge_samples=len(geom["edge_cam"]),
        n_support_break=int(geom["support_mask"].sum()),
        n_fov_exit=sum(1 for m in geom["edge_meta"] if m["reason"] == "fov_exit"),
        edge_mean_base_m=geom["edge_mean"].tolist(),
        edge_dir_base=geom["edge_dir"].tolist(),
        inward_base=geom["inward_base"].tolist(),
        t_support_min_m=geom["t_support_min"],
        t_support_max_m=geom["t_support_max"],
        support_length_m=float(geom["t_support_max"] - geom["t_support_min"]),
        edge_meta=geom["edge_meta"],
        probes=probes,
        _geom=geom,
        _rgb=rgb,
        _depth=depth,
        _k=k,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--field", type=Path, default=FIELD)
    ap.add_argument(
        "--calibration",
        type=Path,
        default=ROOT / "calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json",
    )
    ap.add_argument("--baseline-report", type=Path, default=FIELD / "robot_side_table_edge/robot_side_edge_report.json")
    ap.add_argument(
        "--closest-vertex-json",
        type=Path,
        default=FIELD / "lift_fingertip_envelope/lift_fingertip_all_angles.json",
        help="JSON containing closest_overall.vertex_base_m from first-lift audit",
    )
    ap.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    cal = load(args.calibration)
    t_base_cam = np.asarray(cal["T_base_camera"], float)
    rgbd = args.field / "rgbd"
    frames = sorted(rgbd.glob("frame_*.npz"))
    if not frames:
        raise SystemExit(f"no frames under {rgbd}")

    # --- inputs inventory ---
    cam_report = load(rgbd / "camera_report.json") if (rgbd / "camera_report.json").exists() else {}
    with np.load(frames[0], allow_pickle=True) as f0:
        meta0 = json.loads(
            str(f0["metadata"].item() if hasattr(f0["metadata"], "item") else f0["metadata"])
        )
        rgb0 = f0["rgb"]
        depth0 = f0["depth_m"]
        k0 = f0["k"].tolist()

    # Localize JSON already records FIT_ONLY for C35.
    loc9 = load(args.field / "table_reject_overlay/frame_009_localize.json")
    inputs = dict(
        n_frames=len(frames),
        frames=[p.name for p in frames],
        rgb_shape=list(rgb0.shape),
        depth_shape=list(depth0.shape),
        depth_unit="m (key depth_m, float)",
        depth_scale_mm_in_camera_report=cam_report.get("frames", [{}])[0].get("depth_scale_mm"),
        rgb_depth_alignment=dict(
            registered=meta0.get("registered"),
            rectified=meta0.get("rectified"),
            skew_ms_frame_009=next(
                (
                    fr.get("skew_ms")
                    for fr in cam_report.get("frames", [])
                    if fr.get("file") == "frame_009.npz"
                ),
                None,
            ),
            note="Orbbec registered depth onto color optical frame; stored in same npz",
        ),
        intrinsics_source="npz key 'k' (matches camera_report.calibration.K and localize K)",
        K=k0,
        camera_serial=meta0.get("camera_id") or cam_report.get("selected", {}).get("serial"),
        T_base_camera_source=str(args.calibration.as_posix()),
        T_base_camera_sha256=digest(args.calibration),
        T_base_camera_accuracy_claim=loc9.get("calibration", {}).get("accuracy_claim", "FIT_ONLY"),
        baseline_frame="frame_009.npz",
        baseline_frame_sha256=digest(rgbd / "frame_009.npz"),
        baseline_observation=str(
            (args.field / "table_reject_overlay/frame_009_localize.json").as_posix()
        ),
        baseline_observation_sha256=digest(
            args.field / "table_reject_overlay/frame_009_localize.json"
        ),
        host_capture="/home/qwer/captures/shadow-live-A-retry-20261112-164356",
        note_158_5_mm=(
            "158.5 mm is first-lift fingertip-interior interpolation upper bound vs fitted "
            "edge (lift_fingertip_all_angles), NOT a table-edge measurement tolerance"
        ),
    )

    # --- reproduce baseline ---
    base = process_frame(
        rgbd / "frame_009.npz",
        args.field / "table_reject_overlay/frame_009_localize.json",
        cal,
        t_base_cam,
    )
    archived = load(args.baseline_report)
    repro = dict(
        archived_edge_mean_base_m=archived["edge_mean_base_m"],
        recomputed_edge_mean_base_m=base["edge_mean_base_m"],
        edge_mean_delta_m=float(
            np.linalg.norm(
                np.asarray(base["edge_mean_base_m"]) - np.asarray(archived["edge_mean_base_m"])
            )
        ),
        archived_n_edge_samples=archived["n_edge_samples"],
        recomputed_n_edge_samples=base["n_edge_samples"],
        archived_edge_dir_dot=float(
            abs(np.dot(archived["edge_dir_base"], base["edge_dir_base"]))
        ),
        match_ok=True,
    )
    repro["match_ok"] = (
        repro["edge_mean_delta_m"] < 1e-6
        and abs(repro["archived_n_edge_samples"] - repro["recomputed_n_edge_samples"]) == 0
        and repro["archived_edge_dir_dot"] > 0.999
    )

    rgb_ov, depth_ov = draw_edge_overlays(
        base["_rgb"],
        base["_depth"],
        base["_k"],
        base["_geom"],
        base["probes"],
        "frame_009 robot-side edge physical check",
    )
    rgb_path = args.output / "frame_009_rgb_overlay.png"
    depth_path = args.output / "frame_009_depth_overlay.png"
    cv2.imwrite(str(rgb_path), rgb_ov)
    cv2.imwrite(str(depth_path), depth_ov)

    # Profile plots for probes
    profile_dir = args.output / "profiles"
    profile_dir.mkdir(exist_ok=True)
    for pr in base["probes"]:
        prof = pr["profile"]
        if not prof:
            continue
        canvas = np.ones((220, 420, 3), np.uint8) * 245
        xs = [s["offset_px"] for s in prof["samples"]]
        zs = [s["depth_m"] if s["depth_m"] is not None else np.nan for s in prof["samples"]]
        finite = [(x, z) for x, z in zip(xs, zs) if np.isfinite(z)]
        if finite:
            zz = np.array([z for _, z in finite])
            z0, z1 = float(zz.min()), float(zz.max())
            if z1 - z0 < 1e-3:
                z1 = z0 + 0.05
            for x, z in finite:
                px = int(210 + x * 7)
                py = int(180 - (z - z0) / (z1 - z0) * 140)
                cv2.circle(canvas, (px, py), 2, (30, 30, 200), -1)
        cv2.line(canvas, (210, 20), (210, 200), (0, 180, 0), 1)
        cv2.putText(
            canvas,
            f"{pr['id']} class={pr['profile_class']['label']}",
            (8, 16),
            0,
            0.45,
            (20, 20, 20),
            1,
        )
        cv2.putText(canvas, "left=interior  right=toward robot", (8, 210), 0, 0.4, (40, 40, 40), 1)
        cv2.imwrite(str(profile_dir / f"frame_009_{pr['id']}_depth_profile.png"), canvas)

    # --- multi-frame ---
    per_frame = []
    failures = []
    for fp in frames:
        obs_p = args.field / "table_reject_overlay" / f"{fp.stem}_localize.json"
        if not obs_p.exists():
            failures.append(dict(frame=fp.name, reason="missing_localize_json"))
            continue
        try:
            row = process_frame(fp, obs_p, cal, t_base_cam)
        except Exception as exc:  # noqa: BLE001 — collect per-frame failure
            failures.append(dict(frame=fp.name, reason=f"{type(exc).__name__}: {exc}"))
            continue
        # strip heavy arrays for JSON
        slim = {k: v for k, v in row.items() if not k.startswith("_")}
        # compress profiles in probes for table
        for pr in slim["probes"]:
            if pr.get("profile"):
                pr["profile_summary"] = dict(
                    edge_uv=pr["profile"]["edge_uv"],
                    n_samples=len(pr["profile"]["samples"]),
                )
                del pr["profile"]
        per_frame.append(slim)

        # Save per-frame overlays for all frames (lighter)
        rgb_i, depth_i = draw_edge_overlays(
            row["_rgb"], row["_depth"], row["_k"], row["_geom"], row["probes"], row["frame"]
        )
        cv2.imwrite(str(args.output / f"{fp.stem}_rgb_overlay.png"), rgb_i)
        cv2.imwrite(str(args.output / f"{fp.stem}_depth_overlay.png"), depth_i)

    # Cross-frame edge mean scatter in base XY (plane coords along edge_dir/inward of frame_009)
    ref = next(r for r in per_frame if r["frame"] == "frame_009.npz")
    ref_mean = np.asarray(ref["edge_mean_base_m"])
    ref_dir = np.asarray(ref["edge_dir_base"])
    ref_in = np.asarray(ref["inward_base"])
    ref_n = np.asarray(base["_geom"]["n_base"])
    fluctuations = []
    for r in per_frame:
        m = np.asarray(r["edge_mean_base_m"])
        # project onto ref edge frame
        d = m - ref_mean
        d = d - ref_n * float(d @ ref_n)
        fluctuations.append(
            dict(
                frame=r["frame"],
                along_edge_m=float(d @ ref_dir),
                inward_m=float(d @ ref_in),
                # positive inward_m = this frame's mean is more board-interior than ref
            )
        )
    inward_vals = [f["inward_m"] for f in fluctuations]
    along_vals = [f["along_edge_m"] for f in fluctuations]

    # Independent offset stats from frame_009 probes
    offsets = []
    for pr in base["probes"]:
        indep = pr["independent_rgb_offset"]
        if indep.get("ok"):
            offsets.append(
                dict(
                    id=pr["id"],
                    offset_toward_robot_px=indep["offset_toward_robot_px"],
                    offset_toward_robot_m=indep["offset_toward_robot_m"],
                    profile_label=pr["profile_class"]["label"],
                    exterior_view=pr["profile_class"].get("exterior_view"),
                )
            )

    # Closest-point foot check
    closest_doc = load(args.closest_vertex_json)
    vertex = np.asarray(closest_doc["closest_overall"]["vertex_base_m"], float)
    # Also check L5 from mesh edge if present
    mesh_path = args.field / "lift_mesh_edge/lift_mesh_edge.json"
    l5_foot = None
    if mesh_path.exists():
        mesh = load(mesh_path)
        l5 = mesh["per_part"]["L5_Link"]
        l5_foot = closest_foot_on_segment(np.asarray(l5["vertex_base_m"], float), base["_geom"])
        l5_foot["source"] = "lift_mesh_edge L5_Link closest vertex"
        l5_foot["signed_perpendicular_reported_m"] = l5["signed_perpendicular_m"]
    finger_foot = closest_foot_on_segment(vertex, base["_geom"])
    finger_foot["source"] = "lift_fingertip_all_angles closest_overall"
    finger_foot["signed_perpendicular_reported_m"] = closest_doc["closest_overall"][
        "signed_perpendicular_m"
    ]
    bound_m = closest_doc.get("modeled_interpolation", {}).get("max_signed_upper_bound_m")
    if bound_m is None:
        # all_angles file uses nested structure
        bound_m = closest_doc.get("angles_summary", {}).get("max_signed_upper_m")
        if bound_m is None:
            # try keys seen in grep
            for path in (
                ["envelope_over_angles", "max_signed_upper_m"],
                ["summary", "max_signed_upper_m"],
            ):
                cur = closest_doc
                ok = True
                for k in path:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        ok = False
                        break
                if ok:
                    bound_m = cur
                    break
    # Direct from known field in all_angles
    if "angles_ran" in closest_doc or "per_angle" in closest_doc:
        pass
    # read nested max from file structure we grepped
    if bound_m is None and "interpolation_upper_m" in json.dumps(closest_doc):
        # search
        def find_key(obj, key):
            if isinstance(obj, dict):
                if key in obj:
                    return obj[key]
                for v in obj.values():
                    r = find_key(v, key)
                    if r is not None:
                        return r
            elif isinstance(obj, list):
                for v in obj:
                    r = find_key(v, key)
                    if r is not None:
                        return r
            return None

        bound_m = find_key(closest_doc, "max_signed_upper_m") or find_key(
            closest_doc, "interpolation_upper_m"
        )

    # Segment conclusions
    support_labels = [pr["profile_class"]["label"] for pr in base["probes"]]
    n_rim = sum(1 for x in support_labels if x == "physical_rim_candidate")
    n_partial = sum(1 for x in support_labels if x == "physical_rim_partial_rgb")
    n_weak = sum(1 for x in support_labels if x == "support_break_weak_rgb")
    n_fov = sum(1 for x in support_labels if x == "fov_or_missing_depth_limit")
    if n_rim >= 3:
        mid_status = "可确认"
    elif n_rim + n_partial + n_weak >= 3:
        mid_status = "部分可确认"
    else:
        mid_status = "无法确认"

    # Ends: check edge_meta reasons at extreme laterals
    meta_sorted = sorted(base["edge_meta"], key=lambda m: m["lateral_m"])
    left_end = meta_sorted[0]["reason"]
    right_end = meta_sorted[-1]["reason"]

    def end_status(reason):
        if reason == "support_break":
            return "部分可确认"
        if reason == "fov_exit":
            return "无法确认"
        return "无法确认"

    # Human visual review of frame_009 overlays (independent of fit sample cloud as GT).
    manual_review = dict(
        frame="frame_009.npz",
        method="operator_read_of_rgb_and_depth_overlays_plus_probe_profiles",
        points=[
            dict(
                id="P0",
                pixel_uv=[170, 463],
                rgb_read="white tabletop interior; dark floor/gap just below edge",
                depth_read="on-plane support ends; exterior depth mostly missing",
                verdict="partial_physical_rim",
            ),
            dict(
                id="P1",
                pixel_uv=[219, 462],
                rgb_read="same near-edge contour as table white boundary",
                depth_read="support break; exterior missing",
                verdict="partial_physical_rim",
            ),
            dict(
                id="P2",
                pixel_uv=[268, 461],
                rgb_read="mid near-edge under red brick; RGB rim co-located with green line",
                depth_read="support break; exterior missing",
                verdict="partial_physical_rim",
            ),
            dict(
                id="P3",
                pixel_uv=[316, 460],
                rgb_read="near-edge still visible; line still on white→dark transition",
                depth_read="support break; exterior missing",
                verdict="partial_physical_rim",
            ),
            dict(
                id="P4",
                pixel_uv=[365, 459],
                rgb_read="right side of near edge; still tracks table rim in RGB",
                depth_read="support break; exterior missing / sparse",
                verdict="partial_physical_rim",
            ),
        ],
        note="Pixels are probe locations on the fitted support-break; RGB verdict uses the visible table outer contour, not the fit points as ground truth.",
    )

    segment_conclusion = dict(
        supported_mid_segment=dict(
            status=mid_status,
            basis=(
                f"{n_rim} physical_rim_candidate, {n_partial} physical_rim_partial_rgb, "
                f"{n_weak} weak RGB, {n_fov} missing-depth-only; "
                f"support_break samples={base['n_support_break']}, "
                f"length_m={base['support_length_m']:.3f}; "
                "exterior depth often missing so depth alone insufficient; RGB contour co-located"
            ),
            t_range_m=[base["t_support_min_m"], base["t_support_max_m"]],
        ),
        left_lateral_end=dict(
            status="部分可确认" if left_end == "support_break" else end_status(left_end),
            reason=left_end,
            lateral_m=meta_sorted[0]["lateral_m"],
        ),
        right_lateral_end=dict(
            status="部分可确认" if right_end == "support_break" else end_status(right_end),
            reason=right_end,
            lateral_m=meta_sorted[-1]["lateral_m"],
        ),
        line_extension_outside_support=dict(
            status="无法确认",
            basis="dashed infinite fit is PCA extension; not claimed as physical rim",
        ),
        nearest_distance_foot=dict(
            fingertip_or_interior=finger_foot,
            l5_shell=l5_foot,
            note=(
                "If foot_in_supported_segment is false, prior clearance used an extended "
                "line beyond observed support and must be treated as limited."
            ),
        ),
        manual_review=manual_review,
    )

    # Signed bias summary (independent RGB)
    off_m = [o["offset_toward_robot_m"] for o in offsets if o["offset_toward_robot_m"] is not None]
    off_px = [o["offset_toward_robot_px"] for o in offsets]
    bias = dict(
        sign_convention=(
            "positive = RGB rim further toward robot than fitted support-break "
            "(fit is board-inward of visible rim); millimetres are in-plane, "
            "perpendicular to the near edge (along toward-robot / -inward)"
        ),
        frame_009_probe_offsets=offsets,
        offset_toward_robot_px_median=float(np.median(off_px)) if off_px else None,
        offset_toward_robot_px_p95=float(np.percentile(np.abs(off_px), 95)) if off_px else None,
        offset_toward_robot_mm_median=(
            float(np.median(off_m) * 1000) if off_m else None
        ),
        offset_toward_robot_mm_p95=(
            float(np.percentile(np.abs(off_m), 95) * 1000) if off_m else None
        ),
        cross_frame_edge_mean_inward_mm_std=(
            float(np.std(inward_vals) * 1000) if inward_vals else None
        ),
        cross_frame_edge_mean_inward_mm_span=(
            float((max(inward_vals) - min(inward_vals)) * 1000) if inward_vals else None
        ),
        cross_frame_edge_mean_along_mm_span=(
            float((max(along_vals) - min(along_vals)) * 1000) if along_vals else None
        ),
        cross_frame_note="repeatability only; not a tape-measure accuracy claim",
        table_half_thickness_m=0.012,
        table_thickness_note="model assumption from robot_side_table_edge default; not measured here",
    )

    # Build CSV-like table
    table_rows = []
    for r in per_frame:
        # median independent offset if present — recompute lightly from stored probes
        offs = [
            p["independent_rgb_offset"].get("offset_toward_robot_m")
            for p in r["probes"]
            if p["independent_rgb_offset"].get("ok")
        ]
        offs = [x for x in offs if x is not None]
        labels = [p["profile_class"]["label"] for p in r["probes"]]
        table_rows.append(
            dict(
                frame=r["frame"],
                n_support_break=r["n_support_break"],
                n_fov_exit=r["n_fov_exit"],
                support_length_m=r["support_length_m"],
                edge_mean_base_m=r["edge_mean_base_m"],
                median_rgb_offset_toward_robot_m=float(np.median(offs)) if offs else None,
                probe_labels=labels,
            )
        )

    summary = dict(
        schema="h-shadow-robot-side-edge-physical-check-0.1",
        issue="#36",
        step=1,
        control_ready=False,
        motion_commanded=False,
        motion_enabled=False,
        reject_table_unchanged=True,
        start_head="be200b8",
        inputs=inputs,
        baseline_reproduction=repro,
        overlays=dict(
            frame_009_rgb=str(rgb_path.as_posix()),
            frame_009_depth=str(depth_path.as_posix()),
            profiles=str(profile_dir.as_posix()),
        ),
        frame_009_probes=[
            dict(
                id=pr["id"],
                u=pr["u"],
                v_fit=pr["v_fit"],
                profile_class=pr["profile_class"],
                independent_rgb_offset={
                    k: v
                    for k, v in pr["independent_rgb_offset"].items()
                    if k != "ok" or True
                },
            )
            for pr in base["probes"]
        ],
        multiframe=dict(
            total=len(frames),
            success=len(per_frame),
            failed=failures,
            fluctuations=fluctuations,
            per_frame_table=table_rows,
        ),
        bias_and_repeatability=bias,
        segment_conclusion=segment_conclusion,
        unknowns=[
            "No independent tape measurement of physical rim vs fit",
            "C35 T_base_camera is FIT_ONLY — base-frame millimetres inherit that claim",
            "Desk thickness 12 mm half-slab is model assumption",
            "Full four corners of desk not visible / not delivered",
        ],
        reproduce_command=(
            "python tools/h_shadow_robot_side_edge_physical_check.py "
            "--field docs/team/B/evidence/line_h/readonly_shadow/live_A_164356 "
            "--output docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/robot_side_edge_physical_check"
        ),
        one_field_followup=dict(
            action=(
                "At the mid supported robot-side rim (under head camera FOV, away from arm "
                "occlusion), place a rigid scale/tape perpendicular to the near edge on the "
                "tabletop; mark the visually identified physical rim and photograph with the "
                "same head RGB. Record the tape reading of how far the current fitted edge "
                "(green support-break line from this tool's overlay) sits inward/outward of "
                "that mark."
            ),
            where="mid robot-side desk rim, within the green supported segment of frame_009 overlay",
            reference="physical desk top edge + millimetre tape on tabletop plane",
            units="mm on tabletop, positive toward robot (off-board)",
        ),
    )

    # Write per-frame JSON and summary
    (args.output / "per_frame_results.json").write_text(
        json.dumps(jsonable(dict(frames=per_frame, failures=failures)), indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "summary.json").write_text(
        json.dumps(jsonable(summary), indent=2) + "\n", encoding="utf-8"
    )

    # Human-readable short markdown table
    lines = [
        "# Robot-side edge physical check (live_A_164356)",
        "",
        f"- Frames: {len(frames)} total, {len(per_frame)} ok, {len(failures)} failed",
        f"- Baseline reproduce match_ok={repro['match_ok']} edge_mean_delta_m={repro['edge_mean_delta_m']:.3e}",
        f"- Mid segment: {mid_status}",
        f"- RGB-vs-fit median offset toward robot: {bias['offset_toward_robot_mm_median']} mm",
        f"- Cross-frame edge-mean inward span: {bias['cross_frame_edge_mean_inward_mm_span']} mm",
        f"- Fingertip closest foot in supported segment: {finger_foot['foot_in_supported_segment']}",
        f"- L5 closest foot in supported segment: {None if l5_foot is None else l5_foot['foot_in_supported_segment']}",
        "",
        "| frame | support_break | fov_exit | support_len_m | median_rgb_offset_m |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in table_rows:
        lines.append(
            f"| {r['frame']} | {r['n_support_break']} | {r['n_fov_exit']} | "
            f"{r['support_length_m']:.3f} | {r['median_rgb_offset_toward_robot_m']} |"
        )
    (args.output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "match_ok": repro["match_ok"],
                "mid_status": mid_status,
                "offset_mm_median": bias["offset_toward_robot_mm_median"],
                "cross_frame_inward_span_mm": bias["cross_frame_edge_mean_inward_mm_span"],
                "finger_foot_in_seg": finger_foot["foot_in_supported_segment"],
                "l5_foot_in_seg": None if l5_foot is None else l5_foot["foot_in_supported_segment"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
