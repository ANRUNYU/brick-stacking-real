"""Build wrist-target-0.1 from grasp-relative + base block/cross poses (issue #29/#33)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.wrist_handoff.constants import PARENT_FRAME
from brick_stacking.wrist_handoff.pose_math import transform_from_pose_dict
from brick_stacking.wrist_handoff.wrist_target import (
    canonical_sha256,
    wrist_target_from_block_and_cross,
)


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("grasp_relative", type=Path)
    p.add_argument("poses", type=Path, help="JSON with base_block / base_cross pose dicts")
    p.add_argument("output", type=Path)
    p.add_argument("--table-board-hash", default=None)
    p.add_argument("--table-board", type=Path, default=None, help="optional table-board-0.1 JSON")
    args = p.parse_args()

    rel = json.loads(args.grasp_relative.read_text(encoding="utf-8-sig"))
    poses = json.loads(args.poses.read_text(encoding="utf-8-sig"))
    table_hash = args.table_board_hash
    if args.table_board is not None:
        board = json.loads(args.table_board.read_text(encoding="utf-8-sig"))
        if board.get("reject_emit_wrist_target"):
            raise SystemExit("table-board height check failed; refusing wrist-target")
        table_hash = board.get("table_board_hash") or table_hash

    base_block = transform_from_pose_dict(
        poses["base_block"], parent_frame=PARENT_FRAME, child_frame=rel.get("block_frame", "block")
    )
    base_cross = transform_from_pose_dict(
        poses["base_cross"],
        parent_frame=PARENT_FRAME,
        child_frame=rel.get("cross_frame", "table_black_cross_20mm"),
    )
    hang = poses.get("hang")
    hang_seed = None
    if hang is not None:
        hang_seed = hang.get("seed_q_rad")
        hang_pose = hang
    else:
        hang_pose = None

    out = wrist_target_from_block_and_cross(
        grasp_relative=rel,
        base_block=base_block,
        base_cross=base_cross,
        table_board_hash=table_hash,
        hang_pose=hang_pose,
        hang_seed_q_rad=hang_seed,
        source_evidence=[str(args.grasp_relative), str(args.poses)],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(text, encoding="utf-8")
    print(args.output)
    print("canonical_sha256", canonical_sha256(out))
    print("file_sha256_hint: sha256sum the written file for wrist-path.request_sha256")


if __name__ == "__main__":
    main()
