"""Build and hash wrist-target-0.1 packages for line P."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.wrist_handoff.constants import (
    CHILD_FRAME,
    DEFAULT_LIMITS,
    JOINT_NAMES,
    LOCKED_URDF_SHA256,
    PARENT_FRAME,
    SDK_MOTOR_IDS,
    SEED_PROVENANCE_DEFAULT,
)
from brick_stacking.wrist_handoff.grasp_relative import (
    flange_target_from_object,
    load_grasp_relative,
)
from brick_stacking.wrist_handoff.pose_math import (
    pose_dict_from_matrix,
    transform_from_pose_dict as _transform_from_pose_dict,
)


def file_sha256(path: Path | str) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(obj: Mapping[str, Any]) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def pose_dict_from_transform(tf: RigidTransform, *, include_rpy: bool = True) -> dict[str, Any]:
    return pose_dict_from_matrix(tf.matrix, include_rpy=include_rpy)


def transform_from_pose_dict(
    pose: Mapping[str, Any],
    *,
    parent_frame: str = PARENT_FRAME,
    child_frame: str = CHILD_FRAME,
) -> RigidTransform:
    return _transform_from_pose_dict(dict(pose), parent_frame=parent_frame, child_frame=child_frame)


def _target_entry(
    *,
    name: str,
    pose: Mapping[str, Any] | RigidTransform,
    seed_q_rad: Sequence[float],
    seed_provenance: Sequence[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if isinstance(pose, RigidTransform):
        if pose.target_frame != PARENT_FRAME or pose.source_frame != CHILD_FRAME:
            raise ValueError(f"{name} must be {PARENT_FRAME} <- {CHILD_FRAME}")
        pose_d = pose_dict_from_matrix(pose.matrix)
    else:
        tf = _transform_from_pose_dict(dict(pose), parent_frame=PARENT_FRAME, child_frame=CHILD_FRAME)
        pose_d = pose_dict_from_matrix(tf.matrix)
    q = [float(v) for v in seed_q_rad]
    if len(q) != 7:
        raise ValueError(f"{name} seed_q_rad must have seven joints")
    prov = list(seed_provenance) if seed_provenance is not None else list(SEED_PROVENANCE_DEFAULT)
    if len(prov) != 7:
        raise ValueError(f"{name} seed_provenance must have seven entries")
    entry: dict[str, Any] = {
        "name": name,
        "translation_m": pose_d["translation_m"],
        "quaternion_xyzw": pose_d["quaternion_xyzw"],
        "rpy_extrinsic_zyx_rad": pose_d["rpy_extrinsic_zyx_rad"],
        "seed_joint_names": list(JOINT_NAMES),
        "seed_q_rad": q,
        "seed_provenance": prov,
    }
    if note:
        entry["note"] = note
    return entry


def build_wrist_target(
    *,
    targets: Sequence[Mapping[str, Any] | dict[str, Any]],
    table_board_hash: str | None,
    relative_version: str | None = None,
    hand_preset_pack_version: str | None = None,
    source_evidence: Sequence[str] | str | None = None,
    urdf_sha256: str = LOCKED_URDF_SHA256,
    limits: Mapping[str, float] | None = None,
    status: str = "LINE_H_PACKAGE_EXECUTABLE_FALSE",
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    if urdf_sha256 != LOCKED_URDF_SHA256:
        raise ValueError("urdf_sha256 must match config/models/p7_left/LOCK.json")
    names = [t["name"] if isinstance(t, Mapping) and "name" in t else None for t in targets]
    if "grasp_ready" not in names:
        raise ValueError("targets must include grasp_ready")
    if "place_ready" not in names and "handoff_ready" not in names:
        raise ValueError("targets must include place_ready or handoff_ready")
    built = []
    for raw in targets:
        if not isinstance(raw, Mapping) or "name" not in raw:
            raise ValueError("each target needs name + pose fields or prebuilt entry")
        if "seed_q_rad" in raw and "translation_m" in raw:
            built.append(_target_entry(
                name=str(raw["name"]),
                pose=raw,
                seed_q_rad=raw["seed_q_rad"],
                seed_provenance=raw.get("seed_provenance"),
                note=raw.get("note"),
            ))
        else:
            raise ValueError(f"target {raw.get('name')} incomplete")
    evidence: Any
    if source_evidence is None:
        evidence = None
    elif isinstance(source_evidence, str):
        evidence = source_evidence
    else:
        evidence = list(source_evidence)
    return {
        "schema_version": "wrist-target-0.1",
        "status": status,
        "side": "left",
        "executable": False,
        "control_ready": False,
        "parent_frame": PARENT_FRAME,
        "child_frame": CHILD_FRAME,
        "rotation_convention": {
            "authoritative": "quaternion_xyzw",
            "rpy_display": "extrinsic_zyx_rad",
        },
        "urdf_sha256": urdf_sha256,
        "joint_names": list(JOINT_NAMES),
        "sdk_motor_ids": list(SDK_MOTOR_IDS),
        "table_board_hash": table_board_hash,
        "relative_version": relative_version,
        "hand_preset_pack_version": hand_preset_pack_version,
        "source_evidence": evidence,
        "limits": dict(limits) if limits is not None else dict(DEFAULT_LIMITS),
        "targets": built,
        "notes": list(notes),
    }


def wrist_target_from_block_and_cross(
    *,
    grasp_relative: Mapping[str, Any],
    base_block: RigidTransform,
    base_cross: RigidTransform,
    table_board_hash: str | None,
    hang_pose: Mapping[str, Any] | RigidTransform | None = None,
    hang_seed_q_rad: Sequence[float] | None = None,
    source_evidence: Sequence[str] | str | None = None,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    rel = load_grasp_relative(grasp_relative)
    grasp_tf = flange_target_from_object(
        base_block,
        rel["T_L8_block"],
        object_frame=rel["block_frame"],
    )
    place_tf = flange_target_from_object(
        base_cross,
        rel["T_L8_cross"],
        object_frame=rel["cross_frame"],
    )
    targets: list[dict[str, Any]] = []
    if hang_pose is not None:
        if hang_seed_q_rad is None and "hang" in rel["seeds"]:
            hang_seed_q_rad = rel["seeds"]["hang"]["seed_q_rad"]
        if hang_seed_q_rad is None:
            raise ValueError("hang_seed_q_rad required when hang_pose provided")
        hang_entry = _target_entry(
            name="hang",
            pose=hang_pose,
            seed_q_rad=hang_seed_q_rad,
            seed_provenance=(rel["seeds"].get("hang") or {}).get("seed_provenance"),
        )
        targets.append(hang_entry)
    targets.append(
        _target_entry(
            name="grasp_ready",
            pose=grasp_tf,
            seed_q_rad=rel["seeds"]["grasp_ready"]["seed_q_rad"],
            seed_provenance=rel["seeds"]["grasp_ready"]["seed_provenance"],
        )
    )
    targets.append(
        _target_entry(
            name="place_ready",
            pose=place_tf,
            seed_q_rad=rel["seeds"]["place_ready"]["seed_q_rad"],
            seed_provenance=rel["seeds"]["place_ready"]["seed_provenance"],
        )
    )
    return build_wrist_target(
        targets=targets,
        table_board_hash=table_board_hash,
        relative_version=rel["relative_version"],
        hand_preset_pack_version=rel["hand_preset_pack_version"],
        source_evidence=source_evidence,
        notes=notes,
    )
