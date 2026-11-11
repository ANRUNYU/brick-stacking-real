"""table-board-0.1: chessboard pose in L_arm_root after each table move."""

from __future__ import annotations

from typing import Any, Mapping

from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.wrist_handoff.constants import (
    BOARD_INNER_CORNERS,
    BOARD_SQUARE_SIZE_M,
    DEFAULT_LIMITS,
    PARENT_FRAME,
)
from brick_stacking.wrist_handoff.pose_math import pose_dict_from_matrix, transform_from_pose_dict
from brick_stacking.wrist_handoff.wrist_target import canonical_sha256


def check_table_height(
    *,
    table_height_m: float,
    nominal_table_height_m: float,
    max_delta_m: float | None = None,
) -> dict[str, Any]:
    limit = float(DEFAULT_LIMITS["table_height_check_max_m"] if max_delta_m is None else max_delta_m)
    delta = abs(float(table_height_m) - float(nominal_table_height_m))
    ok = delta <= limit
    return {
        "ok": ok,
        "delta_m": delta,
        "max_delta_m": limit,
        "reason": None if ok else "table_height_delta_exceeds_limit",
    }


def build_table_board(
    *,
    board_id: str,
    t_base_board: Mapping[str, Any] | RigidTransform,
    table_height_m: float,
    nominal_table_height_m: float,
    camera_extrinsic_hash: str,
    square_size_m: float = BOARD_SQUARE_SIZE_M,
    inner_corners: tuple[int, int] = BOARD_INNER_CORNERS,
    evidence_refs: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    if not board_id.strip():
        raise ValueError("board_id required")
    if abs(float(square_size_m) - BOARD_SQUARE_SIZE_M) > 1e-6:
        raise ValueError(f"square_size_m must be {BOARD_SQUARE_SIZE_M} (measured print scale)")
    if isinstance(t_base_board, RigidTransform):
        if t_base_board.target_frame != PARENT_FRAME:
            raise ValueError(f"board parent must be {PARENT_FRAME}")
        pose = pose_dict_from_matrix(t_base_board.matrix)
        child = t_base_board.source_frame
    else:
        child = "table_board"
        tf = transform_from_pose_dict(dict(t_base_board), parent_frame=PARENT_FRAME, child_frame=child)
        pose = pose_dict_from_matrix(tf.matrix)
    height_check = check_table_height(
        table_height_m=table_height_m,
        nominal_table_height_m=nominal_table_height_m,
    )
    doc = {
        "schema_version": "table-board-0.1",
        "board_id": board_id,
        "square_size_m": float(square_size_m),
        "inner_corners": [int(inner_corners[0]), int(inner_corners[1])],
        "parent_frame": PARENT_FRAME,
        "child_frame": child,
        "translation_m": pose["translation_m"],
        "quaternion_xyzw": pose["quaternion_xyzw"],
        "rpy_extrinsic_zyx_rad": pose["rpy_extrinsic_zyx_rad"],
        "table_height_m": float(table_height_m),
        "nominal_table_height_m": float(nominal_table_height_m),
        "height_check": height_check,
        "camera_extrinsic_hash": camera_extrinsic_hash,
        "approved_for_motion": False,
        "reject_emit_wrist_target": not height_check["ok"],
        "evidence_refs": list(evidence_refs or []),
        "notes": list(notes or []),
    }
    doc["table_board_hash"] = canonical_sha256(
        {
            "board_id": doc["board_id"],
            "square_size_m": doc["square_size_m"],
            "translation_m": doc["translation_m"],
            "quaternion_xyzw": doc["quaternion_xyzw"],
            "camera_extrinsic_hash": doc["camera_extrinsic_hash"],
        }
    )
    return doc


def compose_base_board_from_camera(
    *,
    t_base_camera: RigidTransform,
    t_camera_board: RigidTransform,
) -> RigidTransform:
    """T_L_arm_root_board = T_L_arm_root_camera · T_camera_board."""
    return t_base_camera.compose(t_camera_board)
