"""Offline overlay for REJECT_TABLE: flange start, reject samples, visible table edge.

No motion. Uses archived live-A RGB-D + recorded q. Classifies whether negative
flange-to-plane clearance occurs inside the observed tabletop footprint or only
outside the visible board (below-plane but off-table).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

from h_shadow_localizer import (  # noqa: E402
    fit_plane,
    localize,
    red_mask,
    largest_component,
)
from h_shadow_path import fk, load, matrix, plan  # noqa: E402
from brick_stacking.localization.camera_projection import backproject  # noqa: E402


def _project_base_to_uv(xyz_base: np.ndarray, cam_from_base: np.ndarray, k: np.ndarray):
    xyz = (cam_from_base @ np.r_[xyz_base, 1.0])[:3]
    if xyz[2] <= 1e-6:
        return None
    uv = (k @ xyz)[:2] / xyz[2]
    return np.rint(uv).astype(int)


def _table_geometry(capture: Path, frame_name: str, calibration: Path) -> dict:
    """Rebuild table support cloud + image contour for the chosen observation frame."""
    with np.load(capture / frame_name, allow_pickle=False) as data:
        rgb = data["rgb"]
        depth = data["depth_m"].astype(np.float32)
        k = data["k"].astype(np.float64)
    mask = red_mask(rgb, depth)
    comp, _ = largest_component(mask)
    ys, xs = np.where(comp)
    # Same neighborhood table sampling as localizer (non-red valid depth near brick).
    yy, xx = np.mgrid[0 : depth.shape[0], 0 : depth.shape[1]]
    near = (
        (~comp)
        & np.isfinite(depth)
        & (depth > 0.65)
        & (depth < 1.05)
        & (np.abs(xx - xs.mean()) < 180)
        & (np.abs(yy - ys.mean()) < 140)
    )
    # Dominant local plane support (same idea as fixed localizer).
    table_pts = backproject(np.column_stack((xx[near], yy[near])), depth[yy, xx][near], k)
    if len(table_pts) < 200:
        raise ValueError(f"too few table points: {len(table_pts)}")
    centroid, normal = fit_plane(table_pts)
    original_p95 = float(np.quantile(np.abs((table_pts - centroid) @ normal), 0.95))
    table_fraction = 1.0
    if original_p95 > 0.005:
        rng = np.random.default_rng(0)
        sample = table_pts[rng.choice(len(table_pts), min(2048, len(table_pts)), replace=False)]
        best_axis, best_count = None, -1
        for _ in range(64):
            trio = sample[rng.choice(len(sample), 3, replace=False)]
            axis = np.cross(trio[1] - trio[0], trio[2] - trio[0])
            nrm = np.linalg.norm(axis)
            if nrm < 1e-9:
                continue
            axis = axis / nrm
            if axis[1] > 0:
                axis = -axis
            count = int(np.sum(np.abs((table_pts - trio[0]) @ axis) <= 0.015))
            if count > best_count:
                best_count, best_axis, anchor = count, axis, trio[0]
        support = np.abs((table_pts - anchor) @ best_axis) <= 0.015
        table_fraction = float(support.mean())
        if table_fraction < 0.70:
            raise ValueError("insufficient tabletop support")
        table_pts = table_pts[support]
        centroid, normal = fit_plane(table_pts)
    residual_p95 = float(np.percentile(np.abs((table_pts - centroid) @ normal), 95))

    # Image-space contour of the retained table support pixels.
    support_mask = np.zeros(depth.shape, np.uint8)
    # Re-select near pixels that land near the refined plane.
    cand_uv = np.column_stack((xx[near], yy[near]))
    cand_pts = backproject(cand_uv, depth[yy, xx][near], k)
    keep = np.abs((cand_pts - centroid) @ normal) <= 0.015
    keep_uv = cand_uv[keep]
    support_mask[keep_uv[:, 1], keep_uv[:, 0]] = 255
    support_mask = cv2.morphologyEx(support_mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(support_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("no table contour")
    contour = max(contours, key=cv2.contourArea)

    cal = load(calibration)
    t_base_cam = np.asarray(cal["T_base_camera"], float)
    cam_from_base = np.linalg.inv(t_base_cam)
    # Table points in L_arm_root for horizontal footprint test.
    ones = np.ones((len(table_pts), 1))
    pts_h = np.hstack([table_pts, ones])
    table_base = (t_base_cam @ pts_h.T).T[:, :3]
    # Orthonormal tangent basis on table.
    axis = np.eye(3)[int(np.argmin(np.abs(normal)))]
    axis = axis - normal * float(axis @ normal)
    axis = axis / np.linalg.norm(axis)
    basis = np.column_stack((axis, np.cross(normal, axis)))
    # Use base-frame normal/origin for clearance consistency with h_shadow_path.
    # Convert plane to base: n_base = R * n_cam, p_base = T * p_cam
    R = t_base_cam[:3, :3]
    n_base = R @ normal
    n_base = n_base / np.linalg.norm(n_base)
    if n_base[2] > 0:  # prefer "up" toward +Z of L_arm_root? field A top is lower z; keep as-is from brick height convention
        pass
    p_base = (t_base_cam @ np.r_[centroid, 1.0])[:3]
    xy = (table_base - p_base) @ (R @ basis)
    lo, hi = np.quantile(xy, [0.02, 0.98], axis=0)
    return {
        "k": k,
        "rgb": rgb,
        "cam_from_base": cam_from_base,
        "t_base_cam": t_base_cam,
        "table_origin_base": p_base,
        "table_normal_base": n_base,
        "table_origin_camera": centroid,
        "table_normal_camera": normal,
        "support_fraction": table_fraction,
        "residual_p95_m": residual_p95,
        "unfiltered_p95_m": original_p95,
        "contour_uv": contour.reshape(-1, 2),
        "footprint_lo_m": lo.tolist(),
        "footprint_hi_m": hi.tolist(),
        "tangent_basis_camera": basis,
        "table_points_base": table_base,
    }


def _inside_footprint(xyz_base: np.ndarray, geo: dict) -> bool:
    p = geo["table_origin_base"]
    n = geo["table_normal_base"]
    # Rebuild tangent in base from camera basis mapped by R.
    R = geo["t_base_cam"][:3, :3]
    basis_base = R @ geo["tangent_basis_camera"]
    xy = (xyz_base - p) @ basis_base
    lo = np.asarray(geo["footprint_lo_m"])
    hi = np.asarray(geo["footprint_hi_m"])
    return bool(np.all(xy >= lo) and np.all(xy <= hi))


def _instrumented_reject_samples(poses, record, candidate) -> dict:
    """Replay plan lift segment and return every flange sample that caused REJECT_TABLE."""
    relative = matrix(candidate["T_L8_block"])
    centers = np.array([p["model_center_base_m"] for p in poses])
    i = int(np.argmin(np.linalg.norm(centers - np.median(centers, axis=0), axis=1)))
    obs = poses[i]
    block = matrix(obs["base_block"])
    target = block @ np.linalg.inv(relative)
    normal = block[:3, 2]
    table_point = np.asarray(obs["top_center_base_m"]) - obs["top_fit"]["height_m"] * normal
    q = np.array(record["q_rad"], float)
    start = fk(q).matrix
    height = max(start[:3, 3] @ normal, target[:3, 3] @ normal) + 0.03
    raised_start = start[:3, 3] + (height - start[:3, 3] @ normal) * normal

    from brick_stacking.localization.rigid_transforms import RigidTransform
    from brick_stacking.planning.numerical_ik import solve_pose_ik
    from h_shadow_path import limits

    samples = []
    prev = start[:3, 3]
    end, rot = raised_start, start[:3, :3]
    count = max(1, int(np.ceil(np.linalg.norm(end - prev) / 0.015)))
    rejected = None
    for xyz in np.linspace(prev, end, count + 1)[1:]:
        goal = np.eye(4)
        goal[:3, :3] = rot
        goal[:3, 3] = xyz
        sol = solve_pose_ik(
            fk,
            RigidTransform("L_arm_root", "L8_Link", goal, "offline"),
            q,
            limits,
            position_tolerance_m=0.002,
            rotation_tolerance_rad=0.02,
            orientation_weight_m_per_rad=0.1,
            damping=0.008,
            max_step_rad=0.10,
            max_iterations=80,
            difference_step_rad=0.0001,
        )
        if sol["ik"] != "PASS":
            return {"status": "REJECT_IK", "samples": samples}
        next_q = np.array(sol["positions_rad"], float)
        for v in np.linspace(q, next_q, 9):
            flange = fk(v).matrix[:3, 3]
            clearance = float((flange - table_point) @ normal)
            samples.append(
                {
                    "q_rad": v.tolist(),
                    "flange_xyz_m": flange.tolist(),
                    "clearance_m": clearance,
                }
            )
            if clearance <= 0 and rejected is None:
                rejected = samples[-1]
        if min(s["clearance_m"] for s in samples[-9:]) <= 0:
            break
        q = next_q
    return {
        "status": "REJECT_TABLE" if rejected else "NO_REJECT",
        "observation": obs["source_frame"],
        "start_flange_xyz_m": start[:3, 3].tolist(),
        "raised_start_xyz_m": raised_start.tolist(),
        "table_point_base_m": table_point.tolist(),
        "table_normal_base": normal.tolist(),
        "min_clearance_m": min(s["clearance_m"] for s in samples) if samples else None,
        "rejected_sample": rejected,
        "samples": samples,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--capture",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/rgbd",
    )
    p.add_argument(
        "--record",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/shadow_report.json",
    )
    p.add_argument(
        "--candidate",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/candidate_preshape_relative.json",
    )
    p.add_argument(
        "--calibration",
        type=Path,
        default=ROOT
        / "calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/table_reject_overlay",
    )
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    record_doc = load(args.record)
    record = record_doc.get("after") or record_doc
    candidate = load(args.candidate)

    observations = []
    for frame in sorted(args.capture.glob("frame_*.npz")):
        dest = args.output / f"{frame.stem}_localize.json"
        localize(
            argparse.Namespace(
                capture_dir=args.capture,
                frame=frame.name,
                edge_m=0.05,
                calibration=args.calibration,
                output=dest,
            )
        )
        observations.append(load(dest))

    path = plan(observations, record, candidate)
    diag = _instrumented_reject_samples(observations, record, candidate)
    frame_name = path.get("observation") or diag["observation"]
    geo = _table_geometry(args.capture, frame_name, args.calibration)

    # Classify samples relative to visible footprint.
    classified = []
    for s in diag["samples"]:
        xyz = np.asarray(s["flange_xyz_m"], float)
        inside = _inside_footprint(xyz, geo)
        classified.append(
            {
                **s,
                "inside_visible_table_footprint": inside,
                "class": (
                    "below_plane_inside_table"
                    if s["clearance_m"] <= 0 and inside
                    else "below_plane_outside_table"
                    if s["clearance_m"] <= 0 and not inside
                    else "above_plane_inside_table"
                    if inside
                    else "above_plane_outside_table"
                ),
            }
        )
    below = [c for c in classified if c["clearance_m"] <= 0]
    below_inside = [c for c in below if c["inside_visible_table_footprint"]]
    verdict = (
        "PATH_ENTERS_TABLE_VOLUME"
        if below_inside
        else "BELOW_PLANE_BUT_OUTSIDE_VISIBLE_TABLE"
        if below
        else "NO_NEGATIVE_CLEARANCE"
    )

    # Draw overlay.
    image = cv2.cvtColor(geo["rgb"], cv2.COLOR_RGB2BGR)
    cv2.drawContours(image, [geo["contour_uv"].reshape(-1, 1, 2)], -1, (0, 255, 0), 2)
    start_uv = _project_base_to_uv(
        np.asarray(diag["start_flange_xyz_m"]), geo["cam_from_base"], geo["k"]
    )
    raised_uv = _project_base_to_uv(
        np.asarray(diag["raised_start_xyz_m"]), geo["cam_from_base"], geo["k"]
    )
    if start_uv is not None:
        cv2.drawMarker(image, tuple(start_uv), (255, 255, 0), cv2.MARKER_TILTED_CROSS, 22, 2)
        cv2.putText(image, "flange_start", tuple(start_uv + np.array([8, -8])), 0, 0.5, (255, 255, 0), 1)
    if raised_uv is not None:
        cv2.drawMarker(image, tuple(raised_uv), (0, 255, 255), cv2.MARKER_TRIANGLE_UP, 20, 2)
        cv2.putText(image, "lift_target", tuple(raised_uv + np.array([8, -8])), 0, 0.5, (0, 255, 255), 1)
    if start_uv is not None and raised_uv is not None:
        cv2.arrowedLine(image, tuple(start_uv), tuple(raised_uv), (0, 200, 255), 2)

    for c in classified:
        uv = _project_base_to_uv(np.asarray(c["flange_xyz_m"]), geo["cam_from_base"], geo["k"])
        if uv is None:
            continue
        if c["clearance_m"] <= 0:
            color = (0, 0, 255) if c["inside_visible_table_footprint"] else (0, 140, 255)
            cv2.circle(image, tuple(uv), 5, color, -1)
        else:
            cv2.circle(image, tuple(uv), 3, (180, 180, 180), -1)

    legend = [
        "green=visible table support edge",
        "yellow=flange start  cyan=lift target",
        "red=below plane INSIDE table  orange=below plane OUTSIDE",
        f"verdict={verdict}",
        f"min_clearance_m={diag['min_clearance_m']}",
    ]
    for i, line in enumerate(legend):
        cv2.putText(image, line, (12, 24 + 18 * i), 0, 0.5, (255, 255, 255), 1)

    overlay_path = args.output / "table_reject_overlay.png"
    cv2.imwrite(str(overlay_path), image)

    report = {
        "schema": "h-shadow-table-reject-overlay-0.1",
        "control_ready": False,
        "motion_commanded": False,
        "motion_enabled": False,
        "plan_status": path.get("status"),
        "observation_frame": frame_name,
        "verdict": verdict,
        "min_clearance_m": diag["min_clearance_m"],
        "n_samples": len(classified),
        "n_below_plane": len(below),
        "n_below_plane_inside_table": len(below_inside),
        "start_flange_xyz_m": diag["start_flange_xyz_m"],
        "raised_start_xyz_m": diag["raised_start_xyz_m"],
        "table_point_base_m": diag["table_point_base_m"],
        "table_normal_base": diag["table_normal_base"],
        "table_fit": {
            "unfiltered_p95_m": geo["unfiltered_p95_m"],
            "residual_p95_m": geo["residual_p95_m"],
            "support_fraction": geo["support_fraction"],
            "footprint_lo_m": geo["footprint_lo_m"],
            "footprint_hi_m": geo["footprint_hi_m"],
        },
        "rejected_sample": diag["rejected_sample"],
        "samples_classified": classified,
        "overlay_png": str(overlay_path.as_posix()),
        "note": (
            "Flange-only vs infinite table plane + visible support footprint. "
            "Does not certify palm/fingertip/arm-link clearance (#36)."
        ),
    }
    out_json = args.output / "table_reject_overlay.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "min_clearance_m": diag["min_clearance_m"], "overlay": str(overlay_path), "report": str(out_json)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
