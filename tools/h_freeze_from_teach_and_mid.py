"""Freeze grasp-relative from teach samples + vision block/mid poses (Line H #28 provisional)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.wrist_handoff.freeze_from_teach import freeze_grasp_relative_from_teach_and_mid
from brick_stacking.wrist_handoff.wrist_target import (
    build_wrist_target,
    canonical_sha256,
    wrist_target_from_block_and_cross,
)
from brick_stacking.wrist_handoff.constants import PARENT_FRAME
from brick_stacking.wrist_handoff.pose_math import transform_from_pose_dict


def _load_pose(path: Path, *, key: str | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if key is None:
        return data
    if key in data:
        return data[key]
    if "pose_base_c35" in data:
        return data["pose_base_c35"]
    raise KeyError(f"{path}: missing {key}")


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("samples", nargs="+", type=Path)
    p.add_argument("--base-block", type=Path, required=True, help="JSON pose or {base_block:...}")
    p.add_argument("--base-mid", type=Path, required=True, help="mid localize JSON or poses JSON")
    p.add_argument("--relative-version", required=True)
    p.add_argument("--pack-version", required=True)
    p.add_argument("--output-relative", type=Path, required=True)
    p.add_argument("--output-wrist-target", type=Path, default=None)
    p.add_argument("--table-board-hash", default=None)
    p.add_argument("--cross-frame", default="mid_box_cross")
    args = p.parse_args()

    samples = [json.loads(path.read_text(encoding="utf-8-sig")) for path in args.samples]
    block = _load_pose(args.base_block, key="base_block")
    mid_raw = json.loads(args.base_mid.read_text(encoding="utf-8-sig"))
    if "base_cross" in mid_raw:
        mid = dict(mid_raw["base_cross"])
        mid["child_frame"] = args.cross_frame
    elif "pose_base_c35" in mid_raw:
        mid = dict(mid_raw["pose_base_c35"])
        mid["child_frame"] = args.cross_frame
    else:
        mid = mid_raw
        mid["child_frame"] = args.cross_frame

    rel = freeze_grasp_relative_from_teach_and_mid(
        relative_version=args.relative_version,
        pack_version=args.pack_version,
        samples=samples,
        base_block_pose=block,
        base_mid_pose=mid,
        cross_frame=args.cross_frame,
        notes=[f"source_sample={path.as_posix()}" for path in args.samples],
    )
    args.output_relative.parent.mkdir(parents=True, exist_ok=True)
    args.output_relative.write_text(json.dumps(rel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output_relative)

    if args.output_wrist_target is not None:
        hang = next((s for s in samples if s.get("phase") == "hang"), None)
        # Rebuild absolute targets via relative+vision, then rename place_ready -> handoff_ready
        target = wrist_target_from_block_and_cross(
            grasp_relative=rel,
            base_block=transform_from_pose_dict(block, parent_frame=PARENT_FRAME, child_frame="block"),
            base_cross=transform_from_pose_dict(
                mid, parent_frame=PARENT_FRAME, child_frame=args.cross_frame
            ),
            table_board_hash=args.table_board_hash,
            hang_pose=None if hang is None else hang["flange_pose"],
            hang_seed_q_rad=None if hang is None else hang["q_rad"],
            source_evidence=[str(args.output_relative), str(args.base_block), str(args.base_mid)],
            notes=("handoff_provisional=true", "place_ready renamed to handoff_ready"),
        )
        for row in target["targets"]:
            if row["name"] == "place_ready":
                row["name"] = "handoff_ready"
                row["note"] = "vision mid + handoff_ready teach seed"
        # Re-validate via build_wrist_target name rules
        target = build_wrist_target(
            targets=target["targets"],
            table_board_hash=target.get("table_board_hash"),
            relative_version=target.get("relative_version"),
            hand_preset_pack_version=target.get("hand_preset_pack_version"),
            source_evidence=target.get("source_evidence"),
            status="LINE_H_PROVISIONAL_HANDOFF_EXECUTABLE_FALSE",
            notes=target.get("notes") or (),
        )
        target["handoff_provisional"] = True
        args.output_wrist_target.parent.mkdir(parents=True, exist_ok=True)
        args.output_wrist_target.write_text(
            json.dumps(target, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(args.output_wrist_target)
        print("canonical_sha256", canonical_sha256(target))
        print("targets", [t["name"] for t in target["targets"]])


if __name__ == "__main__":
    main()
