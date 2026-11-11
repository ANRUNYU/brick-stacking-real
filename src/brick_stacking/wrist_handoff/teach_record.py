"""Teach-sample schema for Line H #28 (arm + hand, no motion command)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from brick_stacking.wrist_handoff.constants import (
    CHILD_FRAME,
    HAND_CHANNEL_NAMES,
    JOINT_NAMES,
    PARENT_FRAME,
    SEED_PROVENANCE_DEFAULT,
)
from brick_stacking.wrist_handoff.pose_math import pose_dict_from_matrix, transform_from_pose_dict


def build_teach_sample(
    *,
    sample_id: str,
    phase: str,
    q_rad: Sequence[float],
    flange_pose: Mapping[str, Any],
    hand_percent: Sequence[float],
    block_pose_base: Mapping[str, Any] | None = None,
    cross_pose_base: Mapping[str, Any] | None = None,
    enabled_during_record: bool = False,
    motion_commanded: bool = False,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    if phase not in ("preshape_at_block", "close_at_block", "place_ready_at_cross", "hang", "open"):
        raise ValueError(f"unsupported teach phase: {phase}")
    if motion_commanded:
        raise ValueError("teach samples must be recorded with motion_commanded=false")
    q = [float(v) for v in q_rad]
    if len(q) != 7 or any(not np.isfinite(v) for v in q):
        raise ValueError("q_rad must be seven finite radians")
    hand = [float(v) for v in hand_percent]
    if len(hand) != 6 or any(not (0.0 <= v <= 100.0) for v in hand):
        raise ValueError("hand_percent must be six values in [0, 100]")
    # Validate flange pose frames via transform construction.
    transform_from_pose_dict(dict(flange_pose), parent_frame=PARENT_FRAME, child_frame=CHILD_FRAME)
    out: dict[str, Any] = {
        "schema_version": "line-h-teach-sample-0.1",
        "sample_id": sample_id,
        "phase": phase,
        "side": "left",
        "iface": "can2",
        "enabled_during_record": bool(enabled_during_record),
        "motion_commanded": False,
        "joint_names": list(JOINT_NAMES),
        "q_rad": q,
        "seed_provenance": list(SEED_PROVENANCE_DEFAULT),
        "flange_pose": {
            "parent_frame": PARENT_FRAME,
            "child_frame": CHILD_FRAME,
            **{
                k: flange_pose[k]
                for k in ("translation_m", "quaternion_xyzw", "rpy_extrinsic_zyx_rad")
                if k in flange_pose
            },
        },
        "hand": {
            "channel_names": list(HAND_CHANNEL_NAMES),
            "unit": "percent",
            "values": hand,
        },
        "notes": list(notes),
    }
    if block_pose_base is not None:
        transform_from_pose_dict(dict(block_pose_base), parent_frame=PARENT_FRAME, child_frame="block")
        out["block_pose_base"] = dict(block_pose_base)
    if cross_pose_base is not None:
        transform_from_pose_dict(
            dict(cross_pose_base), parent_frame=PARENT_FRAME, child_frame="table_black_cross_20mm"
        )
        out["cross_pose_base"] = dict(cross_pose_base)
    return out


def teach_flange_pose_from_matrix(matrix) -> dict[str, Any]:
    return pose_dict_from_matrix(matrix)
