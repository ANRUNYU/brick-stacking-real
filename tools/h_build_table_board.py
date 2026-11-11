"""Build table-board-0.1 from T_base_camera and T_camera_board (issue #32)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.wrist_handoff.table_board import build_table_board, compose_base_board_from_camera


def _tf(data: dict, *, default_target: str, default_source: str) -> RigidTransform:
    return RigidTransform(
        data.get("target_frame", data.get("parent_frame", default_target)),
        data.get("source_frame", data.get("child_frame", default_source)),
        data["matrix"] if "matrix" in data else _matrix_from_pose(data),
        data.get("source", "derived_unapproved"),
        data.get("calibration_id"),
    )


def _matrix_from_pose(data: dict):
    from brick_stacking.wrist_handoff.pose_math import homogeneous

    return homogeneous(data["translation_m"], data["quaternion_xyzw"])


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("input", type=Path, help="JSON with t_base_camera + t_camera_board or t_base_board")
    p.add_argument("output", type=Path)
    p.add_argument("--board-id", default="table_checkerboard_primary")
    p.add_argument("--nominal-table-height-m", type=float, required=True)
    p.add_argument("--table-height-m", type=float, default=None)
    p.add_argument("--camera-extrinsic-hash", required=True)
    args = p.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if "t_base_board" in data:
        t_base_board = _tf(data["t_base_board"], default_target="L_arm_root", default_source="table_board")
    else:
        t_base_cam = _tf(data["t_base_camera"], default_target="L_arm_root", default_source="camera")
        t_cam_board = _tf(data["t_camera_board"], default_target="camera", default_source="table_board")
        t_base_board = compose_base_board_from_camera(
            t_base_camera=t_base_cam, t_camera_board=t_cam_board
        )
    table_height = args.table_height_m
    if table_height is None:
        table_height = float(t_base_board.matrix[2, 3])
    out = build_table_board(
        board_id=args.board_id,
        t_base_board=t_base_board,
        table_height_m=table_height,
        nominal_table_height_m=args.nominal_table_height_m,
        camera_extrinsic_hash=args.camera_extrinsic_hash,
        evidence_refs=[str(args.input)],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    print("table_board_hash", out["table_board_hash"])
    print("reject_emit_wrist_target", out["reject_emit_wrist_target"])


if __name__ == "__main__":
    main()
