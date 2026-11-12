"""Issue #37: fuse stationary RGB-D + bilateral P7/O6 feedback into a scene packet.

Offline. Does not open CAN or move the robot. Matches the Codex session_205857 review
outputs so P can bind table/brick/arms/hand before MoveIt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.wrist_handoff.constants import CHILD_FRAME, PARENT_FRAME

URDF_JOINTS = tuple(f"L{i}_Joint" for i in range(1, 8))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def fk_l8_translation_m(q_rad, *, urdf_path: Path) -> tuple[float, float, float]:
    q = [float(v) for v in q_rad]
    if len(q) != 7 or not all(math.isfinite(v) for v in q):
        raise ValueError("fk needs seven finite radians")
    positions = {URDF_JOINTS[i]: q[i] for i in range(7)}
    pose, _ = urdf_forward_kinematics(
        Path(urdf_path),
        positions,
        base_frame=PARENT_FRAME,
        tip_frame=CHILD_FRAME,
    )
    t = pose.matrix[:3, 3]
    return float(t[0]), float(t[1]), float(t[2])


def visible_support(loc: dict, depth_shape=(480, 640)) -> dict:
    """Rough FOV / support notes from localize report (no new depth fit)."""
    plane = loc.get("table_plane_camera") or {}
    det = loc.get("detection") or {}
    bbox = det.get("bbox_xywh") or [0, 0, 0, 0]
    x, y, w, h = bbox
    H, W = depth_shape
    touches = bool(x <= 1 or y <= 1 or x + w >= W - 2 or y + h >= H - 2)
    # Table support touching image border inferred from plane sample count + FOV note:
    # if residual/support ok but brick near bottom FOV, table near-edge may be FOV-limited.
    top_uv = det.get("top_pixel_uv") or [0, 0]
    near_bottom = float(top_uv[1]) > H * 0.75
    return dict(
        n_plane_points=plane.get("n_points"),
        residual_p95_m=plane.get("residual_p95_m"),
        support_fraction=plane.get("support_fraction"),
        brick_bbox_xywh=bbox,
        brick_touches_image_border=touches,
        brick_near_bottom_fov=near_bottom,
        touches_image_border=touches or near_bottom,
        top_fit_height_m=(loc.get("top_fit") or {}).get("height_m"),
        note="brick FOV flags only; full desk polygon still UNKNOWN without robot-side edge re-fit",
    )


def nearest_sample(samples: list[dict], stamp_host: float | None) -> tuple[dict | None, float | None]:
    if stamp_host is None or not samples:
        return None, None
    best = None
    best_dt = None
    for row in samples:
        # Prefer left-arm host_end as the arm sample clock.
        t = float(row["left"]["host_end_s"])
        dt = abs(t - stamp_host)
        if best is None or dt < best_dt:
            best, best_dt = row, dt
    return best, best_dt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--field", type=Path, required=True)
    p.add_argument("--localized", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--urdf", type=Path, required=True)
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    summary = load(args.field / "summary.json")
    cam = load(args.field / "rgbd" / "camera_report.json")
    request = load(args.request)
    samples = [
        json.loads(line)
        for line in (args.field / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    locs = sorted(args.localized.glob("frame_*.json"))
    if len(locs) != 10:
        raise SystemExit(f"expected 10 localize json, got {len(locs)}")

    goal_xyz = np.asarray(request["goal"]["T_base_L8"], float)[:3, 3]
    start_req = np.asarray(request["start"]["q_rad"], float)

    frames = []
    offsets_ms = []
    skews_ms = []
    for loc_path in locs:
        loc = load(loc_path)
        frame_name = loc.get("source_frame") or loc_path.name.replace(".json", ".npz")
        # Match camera_report frame row
        cam_row = next((fr for fr in cam.get("frames", []) if fr.get("file") == frame_name), {})
        skew_ms = cam_row.get("skew_ms")
        if skew_ms is not None:
            skews_ms.append(float(skew_ms))
        # RGB device stamp is on Orbbec clock; host receive may be in npz metadata.
        npz = args.field / "rgbd" / frame_name
        host_stamp = None
        with np.load(npz, allow_pickle=True) as f:
            meta = json.loads(str(f["metadata"].item()))
            host_stamp = meta.get("host_receive_stamp_s")
        nearest, dt = nearest_sample(samples, host_stamp)
        if dt is not None:
            offsets_ms.append(dt * 1000.0)
        q_left = nearest["left"]["values"] if nearest else None
        tip = (
            list(fk_l8_translation_m(q_left, urdf_path=args.urdf))
            if q_left is not None
            else None
        )
        goal_dist = (
            float(np.linalg.norm(np.asarray(tip) - goal_xyz)) if tip is not None else None
        )
        frames.append(
            dict(
                frame=frame_name,
                localize=str(loc_path.as_posix()),
                localize_result=loc.get("result"),
                red_model_center_base_m=loc.get("model_center_base_m"),
                red_top_center_base_m=loc.get("top_center_base_m"),
                table_plane_camera=loc.get("table_plane_camera"),
                visible_support=visible_support(loc),
                host_receive_stamp_s=host_stamp,
                rgbd_skew_ms=skew_ms,
                nearest_feedback_offset_s=dt,
                left_q_rad=q_left,
                left_xyz_m=tip,
                goal_distance_m=goal_dist,
                right_q_rad=nearest["right"]["values"] if nearest else None,
                hand=nearest["hand"] if nearest else None,
            )
        )

    last = frames[-1]
    packet = dict(
        schema="h-issue37-scene-packet-0.1",
        issue="#37",
        motion_commanded=False,
        motion_enabled=False,
        control_ready=False,
        scene_ready=False,
        capture_summary=summary,
        field_dir=str(args.field.as_posix()),
        n_rgbd_frames=len(frames),
        n_feedback_samples=len(samples),
        calibration_sha256=digest(args.calibration),
        urdf_sha256_lf=file_sha256_lf(args.urdf),
        request_sha256_lf=file_sha256_lf(args.request),
        planning_endpoints=dict(
            start=dict(
                q_rad=last["left_q_rad"],
                xyz_m=last["left_xyz_m"],
                note="most recent frame's nearest host feedback (not the 20:14 precheck)",
            ),
            request_start_q_rad=start_req.tolist(),
            start_q_delta_vs_request=(
                (np.asarray(last["left_q_rad"]) - start_req).tolist()
                if last["left_q_rad"] is not None
                else None
            ),
            goal=request["goal"],
        ),
        most_recent_frame_left_xyz_m=last["left_xyz_m"],
        most_recent_frame_goal_distance_m=last["goal_distance_m"],
        max_nearest_host_offset_ms=max(offsets_ms) if offsets_ms else None,
        max_rgbd_skew_ms=max(skews_ms) if skews_ms else None,
        median_red_model_center_base_m=np.median(
            [f["red_model_center_base_m"] for f in frames], axis=0
        ).tolist(),
        frames=frames,
        gaps_for_moveit=[
            "measured desk polygon / thickness (visible FOV support only)",
            "right-arm collision geometry binding beyond raw q_rad",
            "left O6 URDF rad / fingertip envelope for new path (percent only here)",
            "attachments / cables / other obstacles",
        ],
        reproduce_command=(
            "python tools/review_scene_feedback.py "
            "--field docs/team/B/evidence/line_h/issue37_scene_20261112_205857/field "
            "--localized docs/team/B/evidence/line_h/issue37_scene_20261112_205857/localized "
            "--calibration calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json "
            "--urdf config/models/p7_left/p7__left.urdf "
            "--request docs/team/B/evidence/line_h/left_auto_preposition_20261112/planning_request.json "
            "--output docs/team/B/evidence/line_h/issue37_scene_20261112_205857/scene_packet.json"
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "most_recent_frame_goal_distance_m": packet["most_recent_frame_goal_distance_m"],
                "most_recent_frame_left_xyz_m": packet["most_recent_frame_left_xyz_m"],
                "max_nearest_host_offset_ms": packet["max_nearest_host_offset_ms"],
                "max_rgbd_skew_ms": packet["max_rgbd_skew_ms"],
                "border_frames": sum(
                    1 for x in frames if x["visible_support"]["touches_image_border"]
                ),
                "median_red": packet["median_red_model_center_base_m"],
                "J6_J7_delta_vs_request": packet["planning_endpoints"]["start_q_delta_vs_request"][
                    -2:
                ],
                "hand": last["hand"]["values"] if last["hand"] else None,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
