"""Validate wrist-path-0.1 against a wrist-target-0.1 package (Line H #31 gate)."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from brick_stacking.wrist_handoff.constants import DEFAULT_LIMITS, JOINT_NAMES, PARENT_FRAME, CHILD_FRAME
from brick_stacking.wrist_handoff.pose_math import translation_error_m
from brick_stacking.wrist_handoff.wrist_target import canonical_sha256, transform_from_pose_dict


def _target_by_name(package: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out = {}
    for row in package.get("targets") or []:
        out[str(row["name"])] = row
    return out


def check_wrist_path(
    *,
    wrist_target: Mapping[str, Any],
    wrist_path: Mapping[str, Any],
    request_sha256: str | None = None,
    tip_poses_by_segment_end: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Offline gate before any live enable.

    If tip_poses_by_segment_end is provided (name -> pose dict of FK at segment end),
    cartesian arrival is checked against limits. Without FK, that check is SKIPPED
    and reported, never silently passed.
    """
    issues: list[str] = []
    if wrist_target.get("schema_version") != "wrist-target-0.1":
        issues.append("wrist_target schema_version must be wrist-target-0.1")
    if wrist_path.get("schema_version") != "wrist-path-0.1":
        issues.append("wrist_path schema_version must be wrist-path-0.1")
    if wrist_path.get("motion_enabled") is True:
        issues.append("wrist_path.motion_enabled must be false")
    if wrist_target.get("executable") is True:
        issues.append("wrist_target.executable must be false until explicit live auth")

    path_hash = wrist_path.get("request_sha256")
    if not path_hash:
        issues.append("request_sha256 missing")
    else:
        expected = request_sha256 or canonical_sha256(wrist_target)
        if str(path_hash) != str(expected):
            issues.append("request_sha256 does not match wrist-target hash")

    joint_names = tuple(wrist_path.get("joint_names") or ())
    if joint_names != JOINT_NAMES:
        issues.append("joint_names must be J1..J7 in order")

    targets = _target_by_name(wrist_target)
    limits = dict(wrist_target.get("limits") or DEFAULT_LIMITS)
    arrival = float(limits["cartesian_arrival_max_m"])
    segments = list(wrist_path.get("segments") or [])
    if not segments:
        issues.append("no segments")

    tip_map = dict(tip_poses_by_segment_end or {})
    arrival_reports: list[dict[str, Any]] = []

    for seg in segments:
        if seg.get("rejected"):
            issues.append(f"segment {seg.get('from')}->{seg.get('to')} is rejected: {seg.get('rejected')}")
            continue
        to_name = str(seg.get("to"))
        points = list(seg.get("points") or [])
        if len(points) < 2:
            issues.append(f"segment to={to_name} needs >=2 points")
            continue
        times = [float(p["time_from_start_s"]) for p in points]
        if any(not np.isfinite(t) for t in times) or any(times[i] >= times[i + 1] for i in range(len(times) - 1)):
            issues.append(f"segment to={to_name} time_from_start_s must be finite and strictly increasing")
        for p in points:
            q = p.get("q_rad") or []
            if len(q) != 7 or any(not np.isfinite(float(v)) for v in q):
                issues.append(f"segment to={to_name} has invalid q_rad")
                break
        if to_name in ("grasp_ready", "place_ready") and to_name not in targets:
            issues.append(f"path ends at unknown target {to_name}")
        interp = seg.get("interpolation")
        if to_name in ("grasp_ready", "place_ready") and interp not in ("joint", "cartesian"):
            issues.append(f"segment to={to_name} interpolation invalid")
        # Near-table final approach to grasp/place should be cartesian when marked.
        if seg.get("near_table_final") is True and interp != "cartesian":
            issues.append(f"near_table_final segment to={to_name} must be cartesian")

        if to_name in tip_map and to_name in targets:
            tip = transform_from_pose_dict(
                tip_map[to_name], parent_frame=PARENT_FRAME, child_frame=CHILD_FRAME
            )
            goal = transform_from_pose_dict(
                targets[to_name],
                parent_frame=PARENT_FRAME,
                child_frame=CHILD_FRAME,
            )
            err = translation_error_m(tip, goal)
            ok = err <= arrival
            arrival_reports.append({"to": to_name, "error_m": err, "limit_m": arrival, "ok": ok})
            if not ok:
                issues.append(f"segment end {to_name} cartesian error {err:.4f}m exceeds {arrival}m")
        elif to_name in ("grasp_ready", "place_ready"):
            arrival_reports.append(
                {
                    "to": to_name,
                    "error_m": None,
                    "limit_m": arrival,
                    "ok": None,
                    "status": "FK_NOT_PROVIDED_SKIPPED",
                }
            )

    return {
        "schema_version": "wrist-path-check-0.1",
        "ok": not issues,
        "issues": issues,
        "arrival_reports": arrival_reports,
        "motion_enabled": False,
        "live_authorized": False,
    }
