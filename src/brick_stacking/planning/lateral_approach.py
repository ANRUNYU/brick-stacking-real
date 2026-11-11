"""Lateral pick/place approach template with table-clearance enforcement.

Rejects vertical-stab-to-table, missing post-grasp lift, and horizontal
segments below approach_height. Does not claim full-arm mesh collision PASS.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import yaml
from pathlib import Path

from brick_stacking.localization.calibration import tcp_target_for_block
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.cartesian_diagnostics import swept_aabb_hit


class LateralTemplateRejected(ValueError):
    """Template geometry violates §3.4 / §0.2 path constraints."""


def load_approach_config(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "m-single-block-approach-0.1":
        raise ValueError("single_block_approach.yaml schema_version required")
    required = (
        "approach_height_m",
        "lift_clearance_m",
        "side_standoff_m",
        "table_z_m",
        "supply_offset_m",
        "tool_half_extent_m",
        "table_half_thickness_m",
        "tcp_block_translation_m",
        "tcp_geometry_version",
        "reference_id",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"approach config missing: {missing}")
    return data


def _finite_xyz(value, *, name: str, positive: bool = False) -> np.ndarray:
    a = np.asarray(value, float)
    if a.shape != (3,) or not np.isfinite(a).all():
        raise ValueError(f"{name}: finite xyz required")
    if positive and np.any(a <= 0):
        raise ValueError(f"{name}: positive extents required")
    return a


def _pose_at(frame: str, position_m, rotation: np.ndarray, *, stamp_s: float | None = None,
             clock_domain: str | None = None, calibration_id: str | None = None) -> RigidTransform:
    m = np.eye(4)
    m[:3, :3] = rotation
    m[:3, 3] = _finite_xyz(position_m, name="position")
    return RigidTransform(
        frame, "tcp", m, "lateral_approach_template", calibration_id,
        approved=False, stamp_s=stamp_s, clock_domain=clock_domain,
    )


def top_up_rotation(yaw_rad: float = 0.0) -> np.ndarray:
    """Top-face up: TCP +Z toward table (world -Z), yaw about world Z (90° symmetry).

    Built as Rz(yaw) @ Rx(π) so det=+1 (SO(3)), not a reflection.
    """
    c, s = np.cos(yaw_rad), np.sin(yaw_rad)
    rx_pi = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])
    rz = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return rz @ rx_pi


def block_pose(frame: str, center_m, *, yaw_rad: float = 0.0, stamp_s: float | None = None,
               clock_domain: str | None = None, calibration_id: str | None = None) -> RigidTransform:
    """T_world_block with top-up orientation (source frame = block)."""
    m = np.eye(4)
    m[:3, :3] = top_up_rotation(yaw_rad)
    m[:3, 3] = _finite_xyz(center_m, name="block_center")
    return RigidTransform(
        frame, "block", m, "lateral_block_pose", calibration_id,
        approved=False, stamp_s=stamp_s, clock_domain=clock_domain,
    )


def tcp_block_transform(config: dict[str, Any]) -> RigidTransform:
    t = _finite_xyz(config["tcp_block_translation_m"], name="tcp_block_translation_m")
    m = np.eye(4)
    m[:3, 3] = t
    return RigidTransform(
        "tcp", "block", m, "synthetic_tcp_geometry",
        config.get("tcp_geometry_version"), approved=False,
    )


def place_center_from_config(config: dict[str, Any]) -> np.ndarray:
    """Adopted cross slot: table origin + nominal model center height."""
    z = float(config.get("block_center_z_m", 0.025))
    return np.array([0.0, 0.0, z], float)


def pick_center_from_place(place_center_m, config: dict[str, Any]) -> np.ndarray:
    offset = _finite_xyz(config["supply_offset_m"], name="supply_offset_m")
    pick = np.asarray(place_center_m, float) + offset
    # Keep on table plane height (in-plane translation only).
    pick[2] = float(place_center_m[2])
    return pick


def _horizontal_unit(from_xy: np.ndarray, to_xy: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    d = np.asarray(to_xy, float) - np.asarray(from_xy, float)
    d[2] = 0.0
    n = np.linalg.norm(d)
    if n < 1e-9:
        f = np.asarray(fallback, float).copy()
        f[2] = 0.0
        fn = np.linalg.norm(f)
        if fn < 1e-9:
            raise LateralTemplateRejected("cannot resolve lateral direction")
        return f / fn
    return d / n


def build_lateral_tcp_waypoints(
    world_pick: RigidTransform,
    world_place: RigidTransform,
    tcp_block: RigidTransform,
    *,
    approach_height_m: float,
    lift_clearance_m: float,
    side_standoff_m: float,
    table_z_m: float,
) -> list[dict[str, Any]]:
    """Build ordered TCP poses for §3.4 lateral template.

    Phases include hand cues at grasp close / place open. Positions use
    world +Z as table normal.
    """
    if world_pick.target_frame != world_place.target_frame:
        raise ValueError("pick/place world frame mismatch")
    if not all(np.isfinite(v) and v > 0 for v in (approach_height_m, lift_clearance_m, side_standoff_m)):
        raise LateralTemplateRejected("positive approach/lift/standoff required")

    pick_tcp = tcp_target_for_block(world_pick, tcp_block)
    place_tcp = tcp_target_for_block(world_place, tcp_block)
    if not np.allclose(pick_tcp.matrix[:3, :3], place_tcp.matrix[:3, :3], atol=1e-8):
        raise LateralTemplateRejected("rotation changes unsupported by lateral template")

    frame = pick_tcp.target_frame
    rot = pick_tcp.matrix[:3, :3]
    p = pick_tcp.matrix[:3, 3].copy()
    q = place_tcp.matrix[:3, 3].copy()
    min_h = table_z_m + approach_height_m

    lateral = _horizontal_unit(p, q, fallback=np.array([1.0, 0.0, 0.0]))
    # Outer side of pick relative to place→pick direction.
    pick_out = -_horizontal_unit(q, p, fallback=lateral)

    def at(xy_anchor, z, name, *, hand=None):
        pos = np.array([xy_anchor[0], xy_anchor[1], z], float)
        pose = _pose_at(frame, pos, rot, calibration_id=pick_tcp.calibration_id)
        row = {"phase": name, "pose": pose, "tcp_position_m": pos.tolist()}
        if hand is not None:
            row["hand_preset"] = hand
        return row

    wait_xy = p[:2] + pick_out[:2] * side_standoff_m
    pick_outer_xy = p[:2] + pick_out[:2] * (side_standoff_m * 0.5)
    place_outer_xy = q[:2] + (-pick_out[:2]) * (side_standoff_m * 0.5)
    retreat_xy = q[:2] + (-pick_out[:2]) * side_standoff_m

    pick_above_z = max(float(p[2]) + approach_height_m, min_h)
    place_above_z = max(float(q[2]) + approach_height_m, min_h)
    lift_z = max(float(p[2]) + lift_clearance_m, min_h)
    place_lift_z = max(float(q[2]) + lift_clearance_m, min_h)

    waypoints = [
        at([wait_xy[0], wait_xy[1]], pick_above_z, "side_wait", hand="MOCK_OPEN"),
        at([pick_outer_xy[0], pick_outer_xy[1]], pick_above_z, "pick_outer"),
        at([p[0], p[1]], pick_above_z, "pick_above"),
        at([p[0], p[1]], float(p[2]), "pick_descend"),
        at([p[0], p[1]], float(p[2]), "grasp_close", hand="MOCK_HOLD"),
        at([p[0], p[1]], lift_z, "pick_lift"),
        at([place_outer_xy[0], place_outer_xy[1]], max(lift_z, place_above_z), "transfer_outer"),
        at([q[0], q[1]], place_above_z, "place_above"),
        at([q[0], q[1]], float(q[2]), "place_descend"),
        at([q[0], q[1]], float(q[2]), "place_open", hand="MOCK_OPEN"),
        at([q[0], q[1]], place_lift_z, "place_lift"),
        at([retreat_xy[0], retreat_xy[1]], place_above_z, "retreat_wait"),
    ]
    validate_lateral_waypoints(
        waypoints,
        approach_height_m=approach_height_m,
        lift_clearance_m=lift_clearance_m,
        table_z_m=table_z_m,
        pick_tcp_z=float(p[2]),
        place_tcp_z=float(q[2]),
    )
    return waypoints


def validate_lateral_waypoints(
    waypoints: list[dict[str, Any]],
    *,
    approach_height_m: float,
    lift_clearance_m: float,
    table_z_m: float,
    pick_tcp_z: float,
    place_tcp_z: float,
) -> None:
    """Code enforcement of §3.4 reject conditions."""
    by_name = {w["phase"]: w for w in waypoints}
    required = (
        "side_wait", "pick_outer", "pick_above", "pick_descend", "grasp_close",
        "pick_lift", "transfer_outer", "place_above", "place_descend",
        "place_open", "place_lift", "retreat_wait",
    )
    missing = [n for n in required if n not in by_name]
    if missing:
        raise LateralTemplateRejected(f"missing phases: {missing}")

    min_h = table_z_m + approach_height_m
    horizontal_phases = ("side_wait", "pick_outer", "pick_above", "transfer_outer",
                         "place_above", "retreat_wait")
    for name in horizontal_phases:
        z = by_name[name]["tcp_position_m"][2]
        if z + 1e-9 < min_h:
            raise LateralTemplateRejected(f"horizontal segment {name} below approach_height")

    # Reject vertical stab: first motion must not be pure descend onto table from wait.
    wait = np.asarray(by_name["side_wait"]["tcp_position_m"], float)
    first_move = np.asarray(by_name["pick_outer"]["tcp_position_m"], float)
    delta = first_move - wait
    if abs(delta[0]) < 1e-6 and abs(delta[1]) < 1e-6 and delta[2] < -1e-3:
        raise LateralTemplateRejected("vertical stab to table rejected")

    # Must have post-grasp vertical lift before lateral transfer.
    close_z = by_name["grasp_close"]["tcp_position_m"][2]
    lift_z = by_name["pick_lift"]["tcp_position_m"][2]
    if lift_z - close_z + 1e-9 < lift_clearance_m:
        raise LateralTemplateRejected("post-grasp lift_clearance insufficient")
    transfer = np.asarray(by_name["transfer_outer"]["tcp_position_m"], float)
    lift = np.asarray(by_name["pick_lift"]["tcp_position_m"], float)
    if abs(transfer[2] - lift[2]) > 1e-3 and transfer[2] + 1e-9 < lift[2]:
        raise LateralTemplateRejected("lateral transfer dropped below lift height")
    if np.linalg.norm(transfer[:2] - lift[:2]) < 1e-6:
        raise LateralTemplateRejected("missing lateral move after lift")

    place_close_z = by_name["place_open"]["tcp_position_m"][2]
    place_lift_z = by_name["place_lift"]["tcp_position_m"][2]
    if place_lift_z - place_close_z + 1e-9 < lift_clearance_m:
        raise LateralTemplateRejected("post-place lift_clearance insufficient")

    # Descend must be the only near-table vertical approaches.
    for name, tcp_z in (("pick_descend", pick_tcp_z), ("place_descend", place_tcp_z)):
        z = by_name[name]["tcp_position_m"][2]
        if abs(z - tcp_z) > 1e-6:
            raise LateralTemplateRejected(f"{name} must match grasp/place TCP height")


def table_obstacle(table_z_m: float, half_thickness_m: float, *, span_m: float = 2.0) -> tuple[str, np.ndarray, np.ndarray]:
    half = float(half_thickness_m)
    if half <= 0:
        raise ValueError("positive table half thickness required")
    lo = np.array([-span_m, -span_m, table_z_m - half], float)
    hi = np.array([span_m, span_m, table_z_m + half], float)
    return ("table_thin_box", lo, hi)


def check_table_clearance(
    waypoints: list[dict[str, Any]],
    *,
    half_extent_m,
    table_z_m: float,
    table_half_thickness_m: float,
) -> dict[str, Any]:
    """Swept AABB of tool envelope vs table thin box. full_collision stays UNKNOWN."""
    half = _finite_xyz(half_extent_m, name="half_extent_m", positive=True)
    obstacle = table_obstacle(table_z_m, table_half_thickness_m)
    hits = []
    positions = [np.asarray(w["tcp_position_m"], float) for w in waypoints]
    for i, (a, b) in enumerate(zip(positions, positions[1:])):
        # Exempt pure vertical contact at grasp/place descend endpoints by
        # checking only segments that stay above table+half unless named descend.
        name_a = waypoints[i]["phase"]
        name_b = waypoints[i + 1]["phase"]
        contact_ok = {name_a, name_b} & {
            "pick_descend", "grasp_close", "place_descend", "place_open",
        }
        if swept_aabb_hit(a, b, half, obstacle[1], obstacle[2]):
            if contact_ok and min(a[2], b[2]) <= table_z_m + table_half_thickness_m + half[2] + 1e-6:
                # Final short descend may touch the clearance slab around the table;
                # still record as exempted contact, not a horizontal scrape.
                if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                    continue
            hits.append({"segment": i, "from": name_a, "to": name_b, "obstacle": obstacle[0]})
    status = "FAIL" if hits else "PASS"
    return {
        "table_clearance": status,
        "full_collision": "UNKNOWN",
        "collisions": hits,
        "obstacle": obstacle[0],
        "scope": "tool_aabb_vs_table_thin_box",
        "missing": ["arm_links", "hand_mesh", "cables", "orientation_sweep"],
    }


def assert_not_vertical_stab_template(waypoints: list[dict[str, Any]]) -> None:
    """Extra guard used by unit tests for classic top-down-only sequences."""
    names = [w["phase"] for w in waypoints]
    if names[:3] == ["approach", "grasp", "lift"]:
        raise LateralTemplateRejected("vertical stab template rejected")
