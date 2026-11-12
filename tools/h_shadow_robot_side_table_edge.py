"""Estimate robot-facing physical table edge from live-A depth (offline, #36).

Visible support contour alone cannot certify the near-robot desk edge because
rejected flange feet project below the 480 px FOV. This tool:

1. Fits/uses the localized table plane from frame_009.
2. Walks along the plane toward L_arm_root (robot side) and finds where
   contiguous in-plane depth support ends — a candidate physical near edge.
3. Reports signed horizontal clearance of rejected flange samples to that edge
   and vertical clearance vs a thin slab of assumed thickness.
4. Explicitly leaves palm/fingertip/arm-link sweep as UNKNOWN pending O6 mesh.

No motion. Not an execution permit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--frame",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/rgbd/frame_009.npz",
    )
    p.add_argument(
        "--observation",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/table_reject_overlay/frame_009_localize.json",
    )
    p.add_argument(
        "--samples",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/independent_footprint_audit/samples.json",
    )
    p.add_argument(
        "--calibration",
        type=Path,
        default=ROOT
        / "calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json",
    )
    p.add_argument("--table-half-thickness-m", type=float, default=0.012)
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/robot_side_table_edge",
    )
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    obs = load(args.observation)
    samples_doc = load(args.samples)
    cal = load(args.calibration)
    t_base_cam = np.asarray(cal["T_base_camera"], float)
    cam_from_base = np.linalg.inv(t_base_cam)

    with np.load(args.frame, allow_pickle=False) as f:
        rgb = f["rgb"]
        depth = f["depth_m"].astype(np.float64)
        k = f["k"].astype(np.float64)

    n_cam = np.asarray(obs["table_plane_camera"]["upward_normal_camera"], float)
    n_cam = n_cam / np.linalg.norm(n_cam)
    origin_cam = np.asarray(obs["top_center_camera_m"], float) - n_cam * float(
        obs["top_fit"]["height_m"]
    )

    h, w = depth.shape
    yy, xx = np.indices((h, w))
    z = depth
    valid = np.isfinite(z) & (z > 0.4) & (z < 1.3)
    pts = np.stack(((xx - k[0, 2]) * z / k[0, 0], (yy - k[1, 2]) * z / k[1, 1], z), axis=-1)
    plane_resid = np.abs((pts - origin_cam) @ n_cam)
    on_plane = valid & (plane_resid < 0.008)

    # Robot-side direction in camera: from table origin toward L_arm_root origin
    # expressed in camera, then projected onto the table plane.
    root_in_cam = (cam_from_base @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
    toward_robot = root_in_cam - origin_cam
    toward_robot = toward_robot - n_cam * float(toward_robot @ n_cam)
    if np.linalg.norm(toward_robot) < 1e-9:
        raise RuntimeError("degenerate robot-side direction on table plane")
    toward_robot = toward_robot / np.linalg.norm(toward_robot)
    lateral = np.cross(n_cam, toward_robot)
    lateral = lateral / np.linalg.norm(lateral)

    # Sample a strip of plane points: for each lateral offset, walk toward robot
    # until on-plane support breaks for >= 3 consecutive samples.
    lateral_offsets = np.linspace(-0.18, 0.18, 37)
    step = 0.005
    max_walk = 0.55
    edge_points_cam = []
    for lat in lateral_offsets:
        start = origin_cam + lateral * lat
        last_good = None
        miss = 0
        for s in np.arange(0.0, max_walk + 1e-9, step):
            p = start + toward_robot * s
            if p[2] <= 1e-6:
                break
            uv = (k @ p)[:2] / p[2]
            u, v = int(round(uv[0])), int(round(uv[1]))
            if not (0 <= u < w and 0 <= v < h):
                # Leaving image toward robot — mark last in-FOV good as FOV-limited edge.
                if last_good is not None:
                    edge_points_cam.append(last_good)
                break
            if on_plane[v, u]:
                last_good = p
                miss = 0
            else:
                miss += 1
                if miss >= 3 and last_good is not None:
                    edge_points_cam.append(last_good)
                    break
        else:
            if last_good is not None:
                edge_points_cam.append(last_good)

    if len(edge_points_cam) < 5:
        raise RuntimeError(f"insufficient robot-side edge samples: {len(edge_points_cam)}")

    edge_cam = np.asarray(edge_points_cam, float)
    edge_base = (t_base_cam @ np.c_[edge_cam, np.ones(len(edge_cam))].T).T[:, :3]
    # Fit a line in the table plane for the near edge (mean point + principal axis).
    edge_mean = edge_base.mean(axis=0)
    n_base = t_base_cam[:3, :3] @ n_cam
    n_base = n_base / np.linalg.norm(n_base)
    # Edge tangent ≈ PCA of edge points projected to plane.
    centered = edge_base - edge_mean
    centered = centered - np.outer(centered @ n_base, n_base)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    edge_dir = vh[0]
    edge_dir = edge_dir - n_base * float(edge_dir @ n_base)
    edge_dir = edge_dir / np.linalg.norm(edge_dir)
    inward = -toward_robot  # from edge toward table interior (opposite robot)
    inward_base = t_base_cam[:3, :3] @ inward
    inward_base = inward_base - n_base * float(inward_base @ n_base)
    inward_base = inward_base / np.linalg.norm(inward_base)

    def signed_edge_clearance_m(xyz_base: np.ndarray) -> float:
        """Positive = on table interior side of robot-facing edge."""
        foot = xyz_base - n_base * float((xyz_base - edge_mean) @ n_base)
        return float((foot - edge_mean) @ inward_base)

    half_th = float(args.table_half_thickness_m)
    rows = []
    for s in samples_doc["samples"]:
        base = np.asarray(s["base_m"], float)
        height = float(s["height_m"])  # plane-signed from independent audit (camera-consistent)
        # Recompute plane height in base for slab test using obs plane mapped to base.
        origin_base = (t_base_cam @ np.r_[origin_cam, 1.0])[:3]
        height_base = float((base - origin_base) @ n_base)
        horiz = signed_edge_clearance_m(base)
        # Thin slab: surface ± half thickness along normal.
        # If flange is below top surface but still above bottom face while outside
        # the edge, classify as off-board underhang rather than through-board.
        below_top = height_base < 0.0
        above_bottom = height_base > -2.0 * half_th
        rows.append(
            {
                "base_m": base.tolist(),
                "height_plane_m": height_base,
                "height_audit_m": height,
                "signed_robot_edge_clearance_m": horiz,
                "outside_robot_edge": horiz < 0.0,
                "below_top_surface": below_top,
                "within_slab_thickness_band": below_top and above_bottom,
                "class": (
                    "through_or_into_board_candidate"
                    if below_top and horiz >= 0.0
                    else "underhang_outside_robot_edge"
                    if below_top and horiz < 0.0
                    else "above_table"
                ),
            }
        )

    n_outside = sum(1 for r in rows if r["outside_robot_edge"])
    n_into = sum(1 for r in rows if r["class"] == "through_or_into_board_candidate")
    min_horiz = min(r["signed_robot_edge_clearance_m"] for r in rows)
    min_height = min(r["height_plane_m"] for r in rows)
    verdict = (
        "INTO_BOARD_VOLUME_CANDIDATE"
        if n_into
        else "UNDERHANG_OUTSIDE_ROBOT_SIDE_EDGE"
        if n_outside == len(rows)
        else "MIXED_EDGE_RELATION"
    )

    # Overlay: extend canvas downward; draw edge polyline + flange feet.
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    img = cv2.copyMakeBorder(img, 0, 420, 0, 0, cv2.BORDER_CONSTANT, value=(36, 36, 36))
    def pix_cam(p):
        if p[2] <= 1e-6:
            return None
        return tuple(np.rint((k @ p)[:2] / p[2]).astype(int))

    poly = []
    for p_cam in edge_cam:
        uv = pix_cam(p_cam)
        if uv is not None and 0 <= uv[0] < w and 0 <= uv[1] < h + 420:
            poly.append(uv)
            cv2.circle(img, uv, 2, (0, 255, 0), -1)
    if len(poly) >= 2:
        cv2.polylines(img, [np.array(poly, np.int32)], False, (0, 255, 0), 2)

    for r in rows:
        cam = (cam_from_base @ np.r_[r["base_m"], 1.0])[:3]
        # Project flange and its plane foot.
        uv_f = pix_cam(cam)
        foot_cam = cam - n_cam * float((cam - origin_cam) @ n_cam)
        uv_foot = pix_cam(foot_cam)
        color = (0, 140, 255) if r["outside_robot_edge"] else (0, 0, 255)
        if uv_f is not None:
            cv2.drawMarker(img, uv_f, (0, 255, 255), cv2.MARKER_TILTED_CROSS, 16, 2)
        if uv_foot is not None:
            cv2.circle(img, uv_foot, 4, color, -1)

    cv2.putText(img, f"verdict={verdict}", (10, h + 28), 0, 0.55, (240, 240, 240), 1)
    cv2.putText(
        img,
        f"min_edge_clear_m={min_horiz:.4f}  min_height_m={min_height:.4f}  half_th={half_th}",
        (10, h + 52),
        0,
        0.5,
        (220, 220, 220),
        1,
    )
    cv2.putText(
        img,
        "green=robot-side depth edge  cyan=flange  orange=feet outside edge",
        (10, h + 76),
        0,
        0.5,
        (200, 200, 200),
        1,
    )
    cv2.putText(
        img,
        "palm/fingertip/arm sweep: UNKNOWN (#36) — no O6 mesh bound here",
        (10, h + 100),
        0,
        0.5,
        (180, 180, 255),
        1,
    )

    png = args.output / "robot_side_edge_overlay.png"
    cv2.imwrite(str(png), img)

    report = {
        "schema": "h-shadow-robot-side-table-edge-0.1",
        "issue": "#36",
        "control_ready": False,
        "motion_commanded": False,
        "motion_enabled": False,
        "frame": args.frame.name,
        "verdict": verdict,
        "table_half_thickness_m": half_th,
        "n_edge_samples": len(edge_cam),
        "edge_mean_base_m": edge_mean.tolist(),
        "edge_dir_base": edge_dir.tolist(),
        "inward_base": inward_base.tolist(),
        "table_normal_base": n_base.tolist(),
        "min_signed_robot_edge_clearance_m": min_horiz,
        "min_height_plane_m": min_height,
        "n_samples": len(rows),
        "n_outside_robot_edge": n_outside,
        "n_into_board_candidate": n_into,
        "samples": rows,
        "missing_for_full_36": [
            "O6 fingertip frames at live hand angles",
            "palm envelope / O6 collision mesh binding",
            "P7 link capsules along lift/transfer/descend",
            "measured full desk polygon (not FOV-limited depth edge)",
            "right-arm / brick / cable obstacles",
        ],
        "overlay_png": str(png.as_posix()),
        "note": (
            "Robot-side edge is the end of contiguous 8 mm plane-support in depth "
            "walking toward L_arm_root. FOV may still truncate the true desk edge; "
            "treat as lower-bound interior. REJECT_TABLE flange-plane gate unchanged."
        ),
    }
    out_json = args.output / "robot_side_edge_report.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": verdict,
                "min_signed_robot_edge_clearance_m": min_horiz,
                "min_height_plane_m": min_height,
                "n_into_board_candidate": n_into,
                "overlay": str(png),
                "report": str(out_json),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
