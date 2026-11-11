"""Localize robot-side mid box+cross from head RGB-D into L_arm_root (C35 fit-only).

Does not emit motion permission. executable/control_ready stay false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.rigid_transforms import RigidTransform


def _plus_template(size: int = 21, arm: int = 7, thickness: int = 3) -> np.ndarray:
    t = np.full((size, size), 255, np.uint8)
    c = size // 2
    t[c - thickness // 2 : c + thickness // 2 + 1, c - arm : c + arm + 1] = 0
    t[c - arm : c + arm + 1, c - thickness // 2 : c + thickness // 2 + 1] = 0
    return t


def detect_plus(
    gray: np.ndarray,
    *,
    roi: tuple[int, int, int, int],
) -> dict[str, Any]:
    x0, y0, x1, y1 = roi
    patch = gray[y0:y1, x0:x1]
    tmpl = _plus_template()
    res = cv2.matchTemplate(patch, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    th, tw = tmpl.shape
    u0 = x0 + max_loc[0] + tw / 2.0
    v0 = y0 + max_loc[1] + th / 2.0
    ui, vi = int(round(u0)), int(round(v0))
    # intensity centroid in 11x11 for dark pixels
    half = 5
    win = gray[max(0, vi - half) : vi + half + 1, max(0, ui - half) : ui + half + 1]
    ys, xs = np.where(win < 140)
    if len(xs) >= 3:
        u = float(ui - half + xs.mean())
        v = float(vi - half + ys.mean())
    else:
        u, v = float(u0), float(v0)
    return {
        "u": u,
        "v": v,
        "u_round": int(round(u)),
        "v_round": int(round(v)),
        "template_score": float(max_val),
        "method": "plus template match + intensity centroid in 11x11",
        "roi_xyxy": [x0, y0, x1, y1],
        "gray_center": int(gray[int(round(v)), int(round(u))]),
        "uncertainty_px": 2.0,
    }


def detect_box_around_cross(
    gray: np.ndarray,
    *,
    center_uv: tuple[float, float],
    search: int = 90,
) -> dict[str, Any] | None:
    u, v = center_uv
    ui, vi = int(round(u)), int(round(v))
    h, w = gray.shape
    x0, x1 = max(0, ui - search), min(w, ui + search)
    y0, y1 = max(0, vi - search), min(h, vi + search)
    roi = gray[y0:y1, x0:x1]
    edges = cv2.Canny(roi, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_score = 1e9
    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) != 4:
            continue
        area = float(cv2.contourArea(approx))
        if area < 400 or area > 25000:
            continue
        rect = cv2.minAreaRect(approx)
        (cx, cy), (rw, rh), _ang = rect
        if min(rw, rh) < 15:
            continue
        aspect = max(rw, rh) / max(1e-6, min(rw, rh))
        if aspect > 1.8:
            continue
        # prefer boxes whose center is near the cross
        du = (x0 + cx) - u
        dv = (y0 + cy) - v
        score = abs(du) + abs(dv) + 0.01 * abs(area - 3000)
        if score < best_score:
            best_score = score
            box = np.array(approx, dtype=float).reshape(-1, 2)
            box[:, 0] += x0
            box[:, 1] += y0
            best = {
                "center_uv": [float(x0 + cx), float(y0 + cy)],
                "size_wh_px": [float(rw), float(rh)],
                "corners_uv": box.tolist(),
                "area_px": area,
                "score": float(score),
                "method": "canny_quad_near_cross",
            }
    return best


def fit_plane_near_marker(
    depth_m: np.ndarray,
    k: np.ndarray,
    *,
    u: float,
    v: float,
    radius_px: int = 120,
    depth_lo: float = 0.65,
    depth_hi: float = 1.05,
) -> dict[str, Any]:
    h, w = depth_m.shape
    ui, vi = int(round(u)), int(round(v))
    ys, xs = np.mgrid[max(0, vi - radius_px) : min(h, vi + radius_px + 1),
                      max(0, ui - radius_px) : min(w, ui + radius_px + 1)]
    d = depth_m[ys, xs]
    mask = np.isfinite(d) & (d > depth_lo) & (d < depth_hi)
    # keep points within circular radius
    mask &= (xs - ui) ** 2 + (ys - vi) ** 2 <= radius_px**2
    pts = backproject(np.column_stack((xs[mask], ys[mask])), d[mask], k)
    if len(pts) < 200:
        raise ValueError(f"too few plane points: {len(pts)}")
    centroid = pts.mean(axis=0)
    _, _, vh = np.linalg.svd(pts - centroid, full_matrices=False)
    normal = vh[-1]
    # upward-ish in camera: prefer normal with negative Y or Z pointing toward camera-up/out
    if normal[1] > 0:
        normal = -normal
    normal = normal / np.linalg.norm(normal)
    residuals = np.abs((pts - centroid) @ normal)
    # ray-plane intersection for marker pixel
    ray = backproject(np.array([[u, v]], float), np.array([1.0]), k)[0]
    ray = ray / ray[2]
    denom = float(normal @ ray)
    if abs(denom) < 1e-8:
        raise ValueError("marker ray parallel to plane")
    t = float(normal @ centroid) / denom
    hit = ray * t
    depth_at = float(depth_m[vi, ui]) if np.isfinite(depth_m[vi, ui]) and depth_m[vi, ui] > 0 else None
    neigh = depth_m[max(0, vi - 1) : vi + 2, max(0, ui - 1) : ui + 2]
    return {
        "fit_region": f"pixels within {radius_px}px of marker with depth in [{depth_lo},{depth_hi}] m",
        "n_points": int(len(pts)),
        "point_on_plane_camera_m": centroid.tolist(),
        "upward_normal_camera": normal.tolist(),
        "residual_abs_m": {
            "p50": float(np.percentile(residuals, 50)),
            "p95": float(np.percentile(residuals, 95)),
            "max": float(residuals.max()),
        },
        "marker_ray_plane_intersection_camera_m": hit.tolist(),
        "depth_at_round_pixel_m": depth_at,
        "depth_neighborhood_3x3_m": neigh.astype(float).tolist(),
        "depth_vs_plane_delta_m": None if depth_at is None else float(depth_at - hit[2]),
    }


def pose_from_point_and_normal(
    point_m: np.ndarray,
    normal_cam: np.ndarray,
    *,
    parent_frame: str,
    child_frame: str,
) -> dict[str, Any]:
    z = normal_cam / np.linalg.norm(normal_cam)
    # table frame: +Z outward/up along plane normal; +X from projected camera +X
    x_ref = np.array([1.0, 0.0, 0.0])
    x = x_ref - z * float(x_ref @ z)
    if np.linalg.norm(x) < 1e-6:
        x_ref = np.array([0.0, 1.0, 0.0])
        x = x_ref - z * float(x_ref @ z)
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    y = y / np.linalg.norm(y)
    x = np.cross(y, z)
    R = np.column_stack((x, y, z))
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = point_m
    # quaternion xyzw
    # use matrix -> scipy-free conversion
    m = R
    t = np.trace(m)
    if t > 0:
        s = 0.5 / np.sqrt(t + 1.0)
        qw = 0.25 / s
        qx = (m[2, 1] - m[1, 2]) * s
        qy = (m[0, 2] - m[2, 0]) * s
        qz = (m[1, 0] - m[0, 1]) * s
    else:
        i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
        if i == 0:
            s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
            qw = (m[2, 1] - m[1, 2]) / s
            qx = 0.25 * s
            qy = (m[0, 1] + m[1, 0]) / s
            qz = (m[0, 2] + m[2, 0]) / s
        elif i == 1:
            s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
            qw = (m[0, 2] - m[2, 0]) / s
            qx = (m[0, 1] + m[1, 0]) / s
            qy = 0.25 * s
            qz = (m[1, 2] + m[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
            qw = (m[1, 0] - m[0, 1]) / s
            qx = (m[0, 2] + m[2, 0]) / s
            qy = (m[1, 2] + m[2, 1]) / s
            qz = 0.25 * s
    return {
        "parent_frame": parent_frame,
        "child_frame": child_frame,
        "translation_m": [float(v) for v in point_m],
        "quaternion_xyzw": [float(qx), float(qy), float(qz), float(qw)],
        "rotation_matrix_rows": R.tolist(),
    }


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("capture_dir", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument(
        "--calibration",
        type=Path,
        default=Path("calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json"),
    )
    p.add_argument("--roi", type=int, nargs=4, default=(120, 220, 420, 400), metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--frame", default="frame_000.npz")
    args = p.parse_args()

    cap = args.capture_dir
    npz = np.load(cap / args.frame)
    rgb = npz["rgb"]
    depth = npz["depth_m"]
    k = np.asarray(npz["k"] if "k" in npz.files else json.loads((cap / "camera_report.json").read_text())["calibration"]["K"], float)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    marker = detect_plus(gray, roi=tuple(args.roi))  # type: ignore[arg-type]
    if marker["template_score"] < 0.25:
        raise SystemExit(f"plus template score too low: {marker['template_score']:.3f}")
    box = detect_box_around_cross(gray, center_uv=(marker["u"], marker["v"]))
    plane = fit_plane_near_marker(depth, k, u=marker["u"], v=marker["v"])
    point_cam = np.asarray(plane["marker_ray_plane_intersection_camera_m"], float)
    normal_cam = np.asarray(plane["upward_normal_camera"], float)

    cal = json.loads(args.calibration.read_text(encoding="utf-8"))
    cal_hash = hashlib.sha256(args.calibration.read_bytes()).hexdigest()
    tf = RigidTransform(
        cal["base_frame"],
        cal["camera_frame"],
        np.asarray(cal["T_base_camera"], float),
        "derived_unapproved",
        cal_hash,
        False,
    )
    point_base = tf.apply(point_cam)
    normal_base = tf.matrix[:3, :3] @ normal_cam
    normal_base = normal_base / np.linalg.norm(normal_base)
    # prefer upward (+Z in base if table below camera looking down-ish). L_arm_root Z often up.
    if normal_base[2] < 0:
        normal_base = -normal_base
        normal_cam = -normal_cam

    pose_cam = pose_from_point_and_normal(
        point_cam, normal_cam, parent_frame=cal["camera_frame"], child_frame="mid_box_cross"
    )
    pose_base = pose_from_point_and_normal(
        point_base, normal_base, parent_frame=cal["base_frame"], child_frame="mid_box_cross"
    )

    # overlay
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    u, v = marker["u_round"], marker["v_round"]
    cv2.drawMarker(bgr, (u, v), (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=18, thickness=2)
    cv2.circle(bgr, (u, v), 8, (0, 255, 255), 1)
    if box is not None:
        pts = np.asarray(box["corners_uv"], int)
        cv2.polylines(bgr, [pts], True, (255, 128, 0), 2)
    overlay_path = args.output.with_name(args.output.stem + "_overlay.png")
    cv2.imwrite(str(overlay_path), bgr)

    depth_pt = None
    if plane["depth_at_round_pixel_m"] is not None:
        depth_pt = backproject(
            np.array([[marker["u"], marker["v"]]], float),
            np.array([plane["depth_at_round_pixel_m"]], float),
            k,
        )[0].tolist()

    report = {
        "schema_version": "line-h-mid-zone-localize-0.1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_capture": str(cap).replace("\\", "/"),
        "source_frame": args.frame,
        "camera_id": "CP2L863000KL",
        "camera_frame": cal["camera_frame"],
        "base_frame": cal["base_frame"],
        "child_frame": "mid_box_cross",
        "scene_note": "robot-side mid position marked with box + cross; hand-eye prep only",
        "marker_center_pixel": marker,
        "box_detection": box,
        "table_plane_camera": plane,
        "point_camera_m_from_depth": depth_pt,
        "point_camera_m_plane_intersection": point_cam.tolist(),
        "pose_camera": pose_cam,
        "pose_base_c35": pose_base,
        "calibration": {
            "path": str(args.calibration).replace("\\", "/"),
            "sha256": cal_hash,
            "accuracy_claim": "FIT_ONLY",
            "approved": False,
            "note": "C35 fit-only; not an execution permit",
        },
        "K": k.tolist(),
        "overlay_png": str(overlay_path).replace("\\", "/"),
        "control_ready": False,
        "motion_enabled": False,
        "executable": False,
        "result": "MID_ZONE_LOCALIZED_C35_FIT_ONLY",
        "next_required": [
            "operator confirm overlay hits the intended robot-side mid box+cross",
            "optional independent ruler check of mid mark in L_arm_root",
            "bind as base_cross / handoff mid for wrist-target rebuild after confirm",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    print("pixel", marker["u"], marker["v"], "score", marker["template_score"])
    print("point_camera_m", point_cam.tolist())
    print("point_base_m", point_base.tolist())
    print("overlay", overlay_path)


if __name__ == "__main__":
    main()
