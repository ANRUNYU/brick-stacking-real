"""Build grasp-relative-0.1 from Line H teach samples (#28)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from brick_stacking.wrist_handoff.grasp_relative import build_grasp_relative, relative_from_base_poses
from brick_stacking.wrist_handoff.hand_presets import build_hand_preset_pack
from brick_stacking.wrist_handoff.pose_math import transform_from_pose_dict
from brick_stacking.wrist_handoff.constants import CHILD_FRAME, PARENT_FRAME
from brick_stacking.wrist_handoff.wrist_target import build_wrist_target


def _sample(samples: Sequence[Mapping[str, Any]], phase: str) -> Mapping[str, Any]:
    matches = [s for s in samples if s.get("phase") == phase]
    if len(matches) != 1:
        raise ValueError(f"need exactly one teach sample with phase={phase}")
    return matches[0]


def _optional_sample(samples: Sequence[Mapping[str, Any]], phase: str) -> Mapping[str, Any] | None:
    matches = [s for s in samples if s.get("phase") == phase]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"need at most one teach sample with phase={phase}")
    return matches[0]


def _target_from_sample(sample: Mapping[str, Any], *, name: str, note: str | None = None) -> dict[str, Any]:
    pose = dict(sample["flange_pose"])
    entry: dict[str, Any] = {
        "name": name,
        "translation_m": list(pose["translation_m"]),
        "quaternion_xyzw": list(pose["quaternion_xyzw"]),
        "seed_q_rad": list(sample["q_rad"]),
    }
    if pose.get("rpy_extrinsic_zyx_rad") is not None:
        entry["rpy_extrinsic_zyx_rad"] = list(pose["rpy_extrinsic_zyx_rad"])
    if sample.get("seed_provenance") is not None:
        entry["seed_provenance"] = list(sample["seed_provenance"])
    if note:
        entry["note"] = note
    return entry


def freeze_provisional_handoff_wrist_target_from_teach(
    *,
    samples: Sequence[Mapping[str, Any]],
    pack_version: str,
    open_percent: Sequence[float] | None = None,
    table_board_hash: str | None = None,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Absolute hang → grasp_ready → handoff_ready package for mid-zone development.

    Uses taught flange poses directly (no block/cross relative freeze). Marked
    handoff_provisional; not a competition place_ready package.
    """
    hang = _sample(samples, "hang")
    pre = _sample(samples, "preshape_at_block")
    handoff = _sample(samples, "handoff_ready")
    close = _optional_sample(samples, "close_at_block")

    open_pct = list(open_percent) if open_percent is not None else list(hang["hand"]["values"])
    close_pct = list(close["hand"]["values"]) if close is not None else list(pre["hand"]["values"])
    pack = build_hand_preset_pack(
        role="left",
        pack_version=pack_version,
        open_percent=open_pct,
        preshape_percent=pre["hand"]["values"],
        close_percent=close_pct,
        notes=("frozen_from_teach_provisional_handoff", "three_finger_not_c49"),
    )

    targets = [
        _target_from_sample(hang, name="hang"),
        _target_from_sample(
            pre,
            name="grasp_ready",
            note="preshape_at_block flange; block_pose_base deferred",
        ),
        _target_from_sample(
            handoff,
            name="handoff_ready",
            note="provisional mid handoff; not final competition mid-zone",
        ),
    ]
    evidence = [str(s.get("sample_id")) for s in (hang, pre, close, handoff) if s is not None]
    out = build_wrist_target(
        targets=targets,
        table_board_hash=table_board_hash,
        relative_version=None,
        hand_preset_pack_version=pack_version,
        source_evidence=evidence,
        status="LINE_H_PROVISIONAL_HANDOFF_EXECUTABLE_FALSE",
        notes=list(notes)
        + [
            "handoff_provisional=true",
            "absolute teach poses; grasp-relative freeze deferred until block/cross measured",
            "segments expected: hang->grasp_ready, grasp_ready->handoff_ready",
        ],
    )
    out["handoff_provisional"] = True
    out["hand_preset_pack"] = pack
    return out


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
