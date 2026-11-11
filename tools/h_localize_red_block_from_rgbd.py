"""Localize a single red 50mm cube from head RGB-D into L_arm_root (C35 fit-only)."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.wrist_handoff.pose_math import pose_dict_from_matrix


def red_mask(rgb: np.ndarray, depth: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    m = cv2.bitwise_or(
        cv2.inRange(hsv, np.array([0, 80, 60]), np.array([12, 255, 255])),
        cv2.inRange(hsv, np.array([165, 80, 60]), np.array([179, 255, 255])),
    )
    m = m.astype(bool) & np.isfinite(depth) & (depth > 0.65) & (depth < 1.05)
    out = (m.astype(np.uint8) * 255)
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return out


def largest_component(mask: np.ndarray) -> tuple[np.ndarray, dict]:
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    best_i, best_a = None, 0
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        if a > best_a:
            best_a, best_i = a, i
    if best_i is None or best_a < 80:
        raise ValueError(f"no red blob found (best_area={best_a})")
    comp = lab == best_i
    x, y, w, h = (
        int(stats[best_i, cv2.CC_STAT_LEFT]),
        int(stats[best_i, cv2.CC_STAT_TOP]),
        int(stats[best_i, cv2.CC_STAT_WIDTH]),
        int(stats[best_i, cv2.CC_STAT_HEIGHT]),
    )
    return comp, {
        "area_px": best_a,
        "centroid_uv": [float(cent[best_i, 0]), float(cent[best_i, 1])],
        "bbox_xywh": [x, y, w, h],
    }


def fit_plane(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - c, full_matrices=False)
    n = vh[-1]
    if n[1] > 0:
        n = -n
    n = n / np.linalg.norm(n)
    return c, n


def pose_from_point_normal(point: np.ndarray, normal: np.ndarray, *, parent: str, child: str) -> dict:
    z = normal / np.linalg.norm(normal)
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
    T[:3, 3] = point
    pose = pose_dict_from_matrix(T)
    return {
        "parent_frame": parent,
        "child_frame": child,
        "translation_m": pose["translation_m"],
        "quaternion_xyzw": pose["quaternion_xyzw"],
        "rpy_extrinsic_zyx_rad": pose.get("rpy_extrinsic_zyx_rad"),
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
    p.add_argument("--edge-m", type=float, default=0.05)
    p.add_argument("--frame", default="frame_000.npz")
    args = p.parse_args()

    npz = np.load(args.capture_dir / args.frame)
    rgb, depth, k = npz["rgb"], npz["depth_m"], np.asarray(npz["k"], float)
    mask = red_mask(rgb, depth)
    comp, meta = largest_component(mask)
    ys, xs = np.where(comp)
    u = float(xs.mean())
    v = float(ys.mean())
    dvals = depth[ys, xs]
    dvals = dvals[np.isfinite(dvals) & (dvals > 0)]
    depth_med = float(np.median(dvals))

    # table plane from nearby non-red valid depth
    ui, vi = int(round(u)), int(round(v))
    h, w = depth.shape
    rad = 140
    yy, xx = np.mgrid[max(0, vi - rad) : min(h, vi + rad + 1), max(0, ui - rad) : min(w, ui + rad + 1)]
    near = (
        np.isfinite(depth[yy, xx])
        & (depth[yy, xx] > 0.65)
        & (depth[yy, xx] < 1.05)
        & (~comp[yy, xx])
        & (((xx - ui) ** 2 + (yy - vi) ** 2) <= rad**2)
    )
    table_pts = backproject(np.column_stack((xx[near], yy[near])), depth[yy, xx][near], k)
    if len(table_pts) < 200:
        raise SystemExit(f"too few table points: {len(table_pts)}")
    centroid, normal = fit_plane(table_pts)
    ray = backproject(np.array([[u, v]], float), np.array([1.0]), k)[0]
    ray = ray / ray[2]
    top_plane = ray * (float(normal @ centroid) / float(normal @ ray))
    # Prefer measured top depth along ray if close to plane hit
    top_depth = backproject(np.array([[u, v]], float), np.array([depth_med]), k)[0]
    if abs(float(top_depth[2] - top_plane[2])) < 0.02:
        top = top_depth
    else:
        top = top_plane
    # cube model center:  half-edge below top along upward normal
    center = top - normal * (args.edge_m / 2.0)

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
    top_base = tf.apply(top)
    center_base = tf.apply(center)
    normal_base = tf.matrix[:3, :3] @ normal
    if normal_base[2] < 0:
        normal_base = -normal_base
        normal = -normal
        # recompute center with flipped normal consistency for camera top already measured
        center = top - normal * (args.edge_m / 2.0)
        center_base = tf.apply(center)
    normal_base = normal_base / np.linalg.norm(normal_base)

    pose_cam = pose_from_point_normal(center, normal, parent=cal["camera_frame"], child="block")
    pose_base = pose_from_point_normal(center_base, normal_base, parent=cal["base_frame"], child="block")

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.drawMarker(bgr, (int(round(u)), int(round(v))), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
    x, y, bw, bh = meta["bbox_xywh"]
    cv2.rectangle(bgr, (x, y), (x + bw, y + bh), (0, 255, 0), 1)
    cv2.putText(bgr, "red_block", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    overlay = args.output.with_name(args.output.stem + "_overlay.png")
    cv2.imwrite(str(overlay), bgr)
    cv2.imwrite(str(args.output.with_name(args.output.stem + "_mask.png")), (comp.astype(np.uint8) * 255))

    report = {
        "schema_version": "line-h-red-block-localize-0.1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_capture": str(args.capture_dir).replace("\\", "/"),
        "source_frame": args.frame,
        "camera_id": "CP2L863000KL",
        "camera_frame": cal["camera_frame"],
        "base_frame": cal["base_frame"],
        "child_frame": "block",
        "edge_m": args.edge_m,
        "detection": {
            **meta,
            "method": "hsv_red_mask + largest_component + depth/plane",
            "top_pixel_uv": [u, v],
            "top_depth_median_m": depth_med,
            "n_mask_pixels": int(comp.sum()),
        },
        "table_plane_camera": {
            "n_points": int(len(table_pts)),
            "upward_normal_camera": normal.tolist(),
            "residual_p95_m": float(np.percentile(np.abs((table_pts - centroid) @ normal), 95)),
        },
        "top_center_camera_m": top.tolist(),
        "model_center_camera_m": center.tolist(),
        "top_center_base_m": top_base.tolist(),
        "model_center_base_m": center_base.tolist(),
        "pose_camera": pose_cam,
        "pose_base_c35": pose_base,
        "base_block": pose_base,
        "calibration": {
            "path": str(args.calibration).replace("\\", "/"),
            "sha256": cal_hash,
            "accuracy_claim": "FIT_ONLY",
            "approved": False,
        },
        "K": k.tolist(),
        "overlay_png": str(overlay).replace("\\", "/"),
        "control_ready": False,
        "motion_enabled": False,
        "executable": False,
        "result": "RED_BLOCK_LOCALIZED_C35_FIT_ONLY",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    print("pixel", u, v)
    print("center_camera_m", center.tolist())
    print("center_base_m", center_base.tolist())
    print("overlay", overlay)


if __name__ == "__main__":
    main()
