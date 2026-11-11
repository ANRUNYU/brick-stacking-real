"""Lateral template reject / clearance unit tests."""
from pathlib import Path

import numpy as np
import pytest

from brick_stacking.planning.lateral_approach import (
    LateralTemplateRejected,
    assert_not_vertical_stab_template,
    block_pose,
    build_lateral_tcp_waypoints,
    check_table_clearance,
    load_approach_config,
    pick_center_from_place,
    place_center_from_config,
    tcp_block_transform,
    validate_lateral_waypoints,
)

ROOT = Path(__file__).resolve().parents[3]
CFG = ROOT / "config/planning/single_block_approach.yaml"


def _waypoints(**overrides):
    cfg = load_approach_config(CFG)
    cfg.update(overrides)
    place = place_center_from_config(cfg)
    pick = pick_center_from_place(place, cfg)
    world_pick = block_pose("L_arm_root", pick)
    world_place = block_pose("L_arm_root", place)
    tcp = tcp_block_transform(cfg)
    return build_lateral_tcp_waypoints(
        world_pick, world_place, tcp,
        approach_height_m=float(cfg["approach_height_m"]),
        lift_clearance_m=float(cfg["lift_clearance_m"]),
        side_standoff_m=float(cfg["side_standoff_m"]),
        table_z_m=float(cfg["table_z_m"]),
    ), cfg


def test_legal_template_horizontal_height_and_lift_first():
    waypoints, cfg = _waypoints()
    by = {w["phase"]: w for w in waypoints}
    min_h = cfg["table_z_m"] + cfg["approach_height_m"]
    for name in ("side_wait", "pick_outer", "pick_above", "transfer_outer", "place_above"):
        assert by[name]["tcp_position_m"][2] + 1e-9 >= min_h
    lift = np.asarray(by["pick_lift"]["tcp_position_m"])
    close = np.asarray(by["grasp_close"]["tcp_position_m"])
    transfer = np.asarray(by["transfer_outer"]["tcp_position_m"])
    assert lift[2] - close[2] + 1e-9 >= cfg["lift_clearance_m"]
    assert np.linalg.norm(transfer[:2] - lift[:2]) > 1e-3


def test_reject_missing_lift():
    waypoints, cfg = _waypoints()
    by = {w["phase"]: dict(w) for w in waypoints}
    by["pick_lift"]["tcp_position_m"] = list(by["grasp_close"]["tcp_position_m"])
    ordered = [by[w["phase"]] for w in waypoints]
    with pytest.raises(LateralTemplateRejected, match="lift_clearance"):
        validate_lateral_waypoints(
            ordered,
            approach_height_m=cfg["approach_height_m"],
            lift_clearance_m=cfg["lift_clearance_m"],
            table_z_m=cfg["table_z_m"],
            pick_tcp_z=by["grasp_close"]["tcp_position_m"][2],
            place_tcp_z=by["place_open"]["tcp_position_m"][2],
        )


def test_reject_horizontal_too_low():
    waypoints, cfg = _waypoints()
    by = {w["phase"]: dict(w) for w in waypoints}
    pos = list(by["pick_above"]["tcp_position_m"])
    pos[2] = cfg["table_z_m"] + 0.01
    by["pick_above"]["tcp_position_m"] = pos
    ordered = [by[w["phase"]] for w in waypoints]
    with pytest.raises(LateralTemplateRejected, match="below approach_height"):
        validate_lateral_waypoints(
            ordered,
            approach_height_m=cfg["approach_height_m"],
            lift_clearance_m=cfg["lift_clearance_m"],
            table_z_m=cfg["table_z_m"],
            pick_tcp_z=by["grasp_close"]["tcp_position_m"][2],
            place_tcp_z=by["place_open"]["tcp_position_m"][2],
        )


def test_reject_vertical_stab_named_template():
    with pytest.raises(LateralTemplateRejected, match="vertical stab"):
        assert_not_vertical_stab_template([
            {"phase": "approach"}, {"phase": "grasp"}, {"phase": "lift"},
        ])


def test_table_clearance_pass_and_full_unknown():
    waypoints, cfg = _waypoints()
    result = check_table_clearance(
        waypoints,
        half_extent_m=cfg["tool_half_extent_m"],
        table_z_m=cfg["table_z_m"],
        table_half_thickness_m=cfg["table_half_thickness_m"],
    )
    assert result["table_clearance"] == "PASS"
    assert result["full_collision"] == "UNKNOWN"


def test_low_horizontal_scrape_fails_clearance():
    waypoints, cfg = _waypoints()
    by = {w["phase"]: dict(w) for w in waypoints}
    # Force a lateral scrape just above the table plane with a fat tool.
    a = list(by["pick_lift"]["tcp_position_m"])
    b = list(by["transfer_outer"]["tcp_position_m"])
    a[2] = 0.02
    b[2] = 0.02
    by["pick_lift"]["tcp_position_m"] = a
    by["transfer_outer"]["tcp_position_m"] = b
    ordered = [by[w["phase"]] for w in waypoints]
    result = check_table_clearance(
        ordered,
        half_extent_m=[0.05, 0.05, 0.05],
        table_z_m=0.0,
        table_half_thickness_m=0.01,
    )
    assert result["table_clearance"] == "FAIL"
    assert result["full_collision"] == "UNKNOWN"
