"""Build grasp-relative-0.1 from Line H teach samples (#28)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from brick_stacking.wrist_handoff.grasp_relative import build_grasp_relative, relative_from_base_poses
from brick_stacking.wrist_handoff.hand_presets import build_hand_preset_pack
from brick_stacking.wrist_handoff.pose_math import transform_from_pose_dict
from brick_stacking.wrist_handoff.constants import CHILD_FRAME, PARENT_FRAME


def _sample(samples: Sequence[Mapping[str, Any]], phase: str) -> Mapping[str, Any]:
    matches = [s for s in samples if s.get("phase") == phase]
    if len(matches) != 1:
        raise ValueError(f"need exactly one teach sample with phase={phase}")
    return matches[0]


def freeze_grasp_relative_from_teach(
    *,
    relative_version: str,
    pack_version: str,
    samples: Sequence[Mapping[str, Any]],
    open_percent: Sequence[float] = (100, 100, 100, 100, 100, 100),
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Require preshape_at_block (+ optional close) and place_ready_at_cross with object poses."""
    pre = _sample(samples, "preshape_at_block")
    place = _sample(samples, "place_ready_at_cross")
    if "block_pose_base" not in pre:
        raise ValueError("preshape_at_block requires block_pose_base")
    if "cross_pose_base" not in place:
        raise ValueError("place_ready_at_cross requires cross_pose_base")

    flange_pre = transform_from_pose_dict(
        pre["flange_pose"], parent_frame=PARENT_FRAME, child_frame=CHILD_FRAME
    )
    block = transform_from_pose_dict(
        pre["block_pose_base"], parent_frame=PARENT_FRAME, child_frame="block"
    )
    flange_place = transform_from_pose_dict(
        place["flange_pose"], parent_frame=PARENT_FRAME, child_frame=CHILD_FRAME
    )
    cross = transform_from_pose_dict(
        place["cross_pose_base"],
        parent_frame=PARENT_FRAME,
        child_frame="table_black_cross_20mm",
    )
    t_l8_block = relative_from_base_poses(base_flange=flange_pre, base_object=block)
    t_l8_cross = relative_from_base_poses(base_flange=flange_place, base_object=cross)

    close_pct = pre["hand"]["values"]
    close_samples = [s for s in samples if s.get("phase") == "close_at_block"]
    if close_samples:
        close_pct = close_samples[0]["hand"]["values"]

    pack = build_hand_preset_pack(
        role="left",
        pack_version=pack_version,
        open_percent=open_percent,
        preshape_percent=pre["hand"]["values"],
        close_percent=close_pct,
        notes=("frozen_from_teach",),
    )

    hang_q = None
    hang_samples = [s for s in samples if s.get("phase") == "hang"]
    if hang_samples:
        hang_q = hang_samples[0]["q_rad"]

    return build_grasp_relative(
        relative_version=relative_version,
        hand_preset_pack=pack,
        t_l8_block=t_l8_block,
        t_l8_cross=t_l8_cross,
        grasp_ready_seed_q_rad=pre["q_rad"],
        place_ready_seed_q_rad=place["q_rad"],
        hang_seed_q_rad=hang_q,
        evidence_refs=[str(s.get("sample_id")) for s in samples],
        notes=list(notes) + ["three_finger_not_c49"],
    )
