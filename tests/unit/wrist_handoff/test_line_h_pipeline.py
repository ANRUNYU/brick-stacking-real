"""Unit tests for Line H wrist handoff pipeline (#28/#29/#31/#32/#33 software)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.wrist_handoff.freeze_from_teach import freeze_grasp_relative_from_teach
from brick_stacking.wrist_handoff.table_board import build_table_board, check_table_height, compose_base_board_from_camera
from brick_stacking.wrist_handoff.wrist_path_check import check_wrist_path
from brick_stacking.wrist_handoff.wrist_target import (
    canonical_sha256,
    pose_dict_from_transform,
    wrist_target_from_block_and_cross,
)
from brick_stacking.wrist_handoff.constants import PARENT_FRAME
from brick_stacking.wrist_handoff.pose_math import transform_from_pose_dict

FIXTURE = Path("tests/fixtures/line_h/synthetic_teach_bundle.json")


def test_freeze_and_wrist_target_roundtrip():
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rel = freeze_grasp_relative_from_teach(
        relative_version="syn-rel-0.1",
        pack_version="syn-hand-0.1",
        samples=bundle["samples"],
    )
    assert rel["schema_version"] == "grasp-relative-0.1"
    assert rel["rejects_c49_two_finger"] is True
    assert rel["hand_preset_pack"]["presets"]["preshape"]["position"]["values"][2] == 65.0

    pre = next(s for s in bundle["samples"] if s["phase"] == "preshape_at_block")
    place = next(s for s in bundle["samples"] if s["phase"] == "place_ready_at_cross")
    hang = next(s for s in bundle["samples"] if s["phase"] == "hang")
    base_block = transform_from_pose_dict(pre["block_pose_base"], parent_frame=PARENT_FRAME, child_frame="block")
    base_cross = transform_from_pose_dict(
        place["cross_pose_base"], parent_frame=PARENT_FRAME, child_frame="table_black_cross_20mm"
    )
    target = wrist_target_from_block_and_cross(
        grasp_relative=rel,
        base_block=base_block,
        base_cross=base_cross,
        table_board_hash="synthetic-board",
        hang_pose=hang["flange_pose"],
        hang_seed_q_rad=hang["q_rad"],
    )
    names = [t["name"] for t in target["targets"]]
    assert names == ["hang", "grasp_ready", "place_ready"]
    assert target["executable"] is False
    grasp = next(t for t in target["targets"] if t["name"] == "grasp_ready")
    assert grasp["translation_m"] == pytest.approx([0.50, 0.05, -0.30], abs=1e-9)


def test_table_board_height_gate():
    ok = check_table_height(table_height_m=-0.45, nominal_table_height_m=-0.452)
    assert ok["ok"] is True
    bad = check_table_height(table_height_m=-0.45, nominal_table_height_m=-0.47)
    assert bad["ok"] is False

    t_cam = RigidTransform(
        "L_arm_root",
        "camera",
        np.eye(4),
        "synthetic",
    )
    m = np.eye(4)
    m[:3, 3] = [0.1, 0.2, -0.45]
    t_board_cam = RigidTransform("camera", "table_board", m, "synthetic")
    t_base = compose_base_board_from_camera(t_base_camera=t_cam, t_camera_board=t_board_cam)
    board = build_table_board(
        board_id="table_checkerboard_primary",
        t_base_board=t_base,
        table_height_m=-0.45,
        nominal_table_height_m=-0.45,
        camera_extrinsic_hash="c35-fit-only",
    )
    assert board["schema_version"] == "table-board-0.1"
    assert board["reject_emit_wrist_target"] is False
    assert len(board["table_board_hash"]) == 64


def test_wrist_path_hash_and_arrival():
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rel = freeze_grasp_relative_from_teach(
        relative_version="syn-rel-0.1",
        pack_version="syn-hand-0.1",
        samples=bundle["samples"],
    )
    pre = next(s for s in bundle["samples"] if s["phase"] == "preshape_at_block")
    place = next(s for s in bundle["samples"] if s["phase"] == "place_ready_at_cross")
    target = wrist_target_from_block_and_cross(
        grasp_relative=rel,
        base_block=transform_from_pose_dict(pre["block_pose_base"], parent_frame=PARENT_FRAME, child_frame="block"),
        base_cross=transform_from_pose_dict(
            place["cross_pose_base"], parent_frame=PARENT_FRAME, child_frame="table_black_cross_20mm"
        ),
        table_board_hash="synthetic-board",
    )
    digest = canonical_sha256(target)
    path = {
        "schema_version": "wrist-path-0.1",
        "request_sha256": digest,
        "motion_enabled": False,
        "joint_names": ["J1", "J2", "J3", "J4", "J5", "J6", "J7"],
        "segments": [
            {
                "from": "hang",
                "to": "grasp_ready",
                "interpolation": "joint",
                "rejected": None,
                "points": [
                    {"time_from_start_s": 0.0, "q_rad": [0.0] * 7},
                    {"time_from_start_s": 1.0, "q_rad": pre["q_rad"]},
                ],
            },
            {
                "from": "grasp_ready",
                "to": "place_ready",
                "interpolation": "cartesian",
                "near_table_final": True,
                "rejected": None,
                "points": [
                    {"time_from_start_s": 0.0, "q_rad": pre["q_rad"]},
                    {"time_from_start_s": 2.0, "q_rad": place["q_rad"]},
                ],
            },
        ],
    }
    tips = {
        "grasp_ready": next(t for t in target["targets"] if t["name"] == "grasp_ready"),
        "place_ready": next(t for t in target["targets"] if t["name"] == "place_ready"),
    }
    report = check_wrist_path(wrist_target=target, wrist_path=path, tip_poses_by_segment_end=tips)
    assert report["ok"] is True

    path_bad = dict(path)
    path_bad["request_sha256"] = "0" * 64
    bad = check_wrist_path(wrist_target=target, wrist_path=path_bad)
    assert bad["ok"] is False
