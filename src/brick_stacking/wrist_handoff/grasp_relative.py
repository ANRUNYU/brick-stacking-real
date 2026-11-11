"""Freeze grasp-relative-0.1: T_L8_block and T_L8_cross (not C49 two-finger)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from brick_stacking.localization.calibration import tcp_target_for_block
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.wrist_handoff.constants import CHILD_FRAME, JOINT_NAMES, SEED_PROVENANCE_DEFAULT
from brick_stacking.wrist_handoff.hand_presets import require_pack
from brick_stacking.wrist_handoff.pose_math import pose_dict_from_matrix, transform_from_pose_dict


def _require_seed(seed_q_rad: Sequence[float], provenance: Sequence[str] | None) -> dict[str, Any]:
    q = [float(v) for v in seed_q_rad]
    if len(q) != 7 or any(not np.isfinite(v) for v in q):
        raise ValueError("seed_q_rad must be seven finite radians")
    prov = list(provenance) if provenance is not None else list(SEED_PROVENANCE_DEFAULT)
    if len(prov) != 7:
        raise ValueError("seed_provenance must have seven entries")
    if prov[5] != "sdk_report_not_audited" or prov[6] != "sdk_report_not_audited":
        raise ValueError("J6/J7 provenance must remain sdk_report_not_audited until wrist ranges verified")
    return {
        "seed_joint_names": list(JOINT_NAMES),
        "seed_q_rad": q,
        "seed_provenance": prov,
    }


def relative_from_base_poses(
    *,
    base_flange: RigidTransform,
    base_object: RigidTransform,
) -> RigidTransform:
    """T_flange_object = inverse(T_base_flange) @ T_base_object."""
    if base_flange.target_frame != base_object.target_frame:
        raise ValueError("base poses must share parent frame")
    if base_flange.source_frame != CHILD_FRAME:
        raise ValueError(f"flange child must be {CHILD_FRAME}")
    return base_flange.inverse().compose(base_object)


def build_grasp_relative(
    *,
    relative_version: str,
    hand_preset_pack: Mapping[str, Any],
    t_l8_block: Mapping[str, Any] | RigidTransform,
    t_l8_cross: Mapping[str, Any] | RigidTransform,
    grasp_ready_seed_q_rad: Sequence[float],
    place_ready_seed_q_rad: Sequence[float],
    hang_seed_q_rad: Sequence[float] | None = None,
    block_frame: str = "block",
    cross_frame: str = "table_black_cross_20mm",
    evidence_refs: Sequence[str] = (),
    notes: Sequence[str] = (),
    grasp_seed_provenance: Sequence[str] | None = None,
    place_seed_provenance: Sequence[str] | None = None,
    hang_seed_provenance: Sequence[str] | None = None,
) -> dict[str, Any]:
    pack = require_pack(hand_preset_pack)
    if not relative_version.strip():
        raise ValueError("relative_version required")

    def as_pose(value: Mapping[str, Any] | RigidTransform, child: str) -> dict[str, Any]:
        if isinstance(value, RigidTransform):
            if value.target_frame != CHILD_FRAME or value.source_frame != child:
                raise ValueError(f"relative transform frames must be {CHILD_FRAME} <- {child}")
            return pose_dict_from_matrix(value.matrix)
        tf = transform_from_pose_dict(dict(value), parent_frame=CHILD_FRAME, child_frame=child)
        return pose_dict_from_matrix(tf.matrix)

    out: dict[str, Any] = {
        "schema_version": "grasp-relative-0.1",
        "relative_version": relative_version,
        "side": "left",
        "flange_frame": CHILD_FRAME,
        "block_frame": block_frame,
        "cross_frame": cross_frame,
        "finger_strategy": "three_finger",
        "rejects_c49_two_finger": True,
        "approved_for_motion": False,
        "executable": False,
        "control_ready": False,
        "hand_preset_pack_version": pack["pack_version"],
        "hand_preset_pack": pack,
        "T_L8_block": as_pose(t_l8_block, block_frame),
        "T_L8_cross": as_pose(t_l8_cross, cross_frame),
        "seeds": {
            "grasp_ready": _require_seed(grasp_ready_seed_q_rad, grasp_seed_provenance),
            "place_ready": _require_seed(place_ready_seed_q_rad, place_seed_provenance),
        },
        "evidence_refs": list(evidence_refs),
        "notes": list(notes),
    }
    if hang_seed_q_rad is not None:
        out["seeds"]["hang"] = _require_seed(hang_seed_q_rad, hang_seed_provenance)
    return out


def load_grasp_relative(data: Mapping[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != "grasp-relative-0.1":
        raise ValueError("grasp-relative-0.1 required")
    if data.get("rejects_c49_two_finger") is not True:
        raise ValueError("must explicitly reject C49 two-finger reuse")
    require_pack(data["hand_preset_pack"])
    for key in ("T_L8_block", "T_L8_cross"):
        if key not in data:
            raise ValueError(f"missing {key}")
    seeds = data.get("seeds") or {}
    if "grasp_ready" not in seeds or "place_ready" not in seeds:
        raise ValueError("seeds.grasp_ready and seeds.place_ready required")
    return dict(data)


def flange_target_from_object(
    base_object: RigidTransform,
    t_l8_object_pose: Mapping[str, Any],
    *,
    object_frame: str,
) -> RigidTransform:
    t_l8_object = transform_from_pose_dict(
        dict(t_l8_object_pose),
        parent_frame=CHILD_FRAME,
        child_frame=object_frame,
    )
    return tcp_target_for_block(base_object, t_l8_object)
