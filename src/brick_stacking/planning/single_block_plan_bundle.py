"""Single-block lateral PlanBundle (software closed-loop).

Schema ``m-single-block-plan-bundle-0.1``. Separate from shadow host checklist
package ``m-shadow-plan-bundle-0.1``. Defaults: executable/motion/control_ready
all false; accuracy_claim=FIT_ONLY; full_collision=UNKNOWN.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml

from brick_stacking.arm.adapter import JOINT_NAMES, trajectory_hash, validate_trajectory
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.joint_trajectory import JointLimits
from brick_stacking.planning.lateral_approach import (
    LateralTemplateRejected,
    block_pose,
    build_lateral_tcp_waypoints,
    check_table_clearance,
    load_approach_config,
    pick_center_from_place,
    place_center_from_config,
    tcp_block_transform,
)
from brick_stacking.planning.pose_path import plan_pose_path

SCHEMA = "m-single-block-plan-bundle-0.1"

# Declared URDF joint order for left arm (execution contracts use J1..J7).
URDF_LEFT_JOINTS = tuple(f"L{i}_Joint" for i in range(1, 8))
J_TO_URDF = dict(zip(JOINT_NAMES, URDF_LEFT_JOINTS, strict=True))
URDF_TO_J = {u: j for j, u in J_TO_URDF.items()}


def load_joint_limits_config(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("joint limits config must be a mapping")
    if not data.get("model_version") or not data.get("source"):
        raise ValueError("joint limits require model_version and source; refusing defaults")
    if data.get("source") not in ("synthetic", "recorded", "real"):
        raise ValueError("joint limits source must be synthetic|recorded|real")
    return data


def joint_limits_from_config(data: dict[str, Any]) -> JointLimits:
    if not data.get("model_version") or not data.get("source"):
        raise ValueError("joint limits require model_version and source; refusing defaults")
    if data.get("source") not in ("synthetic", "recorded", "real"):
        raise ValueError("joint limits source must be synthetic|recorded|real")
    names = tuple(data["joint_names"])
    if names != JOINT_NAMES:
        raise ValueError("joint_names must be J1..J7 in order")
    return JointLimits(
        names,
        tuple(data["lower_rad"]),
        tuple(data["upper_rad"]),
        tuple(data["velocity_rad_s"]),
        tuple(data["acceleration_rad_s2"]),
        str(data["model_version"]),
        str(data["source"]),
    )


def synthetic_tabletop_fk_factory(
    *,
    seed_rad: Any,
    lever_m_per_rad: float,
    base_tcp: RigidTransform,
) -> Callable:
    """Jacobian-friendly synthetic FK for offline software closed-loop tests.

    J1/J2/J3 translate TCP in world XYZ; J4/J5/J6 apply small RPY about seed;
    J7 is a redundant roll. Not a hardware model.
    """
    seed = np.asarray(seed_rad, float)
    if seed.shape != (7,) or not np.isfinite(seed).all():
        raise ValueError("finite 7-vector seed required")
    if not np.isfinite(lever_m_per_rad) or lever_m_per_rad <= 0:
        raise ValueError("positive fk lever required")
    base = np.array(base_tcp.matrix, float, copy=True)

    def fk(q):
        q = np.asarray(q, float)
        if q.shape != (7,) or not np.isfinite(q).all():
            raise ValueError("finite 7-vector q required")
        dq = q - seed
        m = base.copy()
        m[:3, 3] = base[:3, 3] + dq[:3] * lever_m_per_rad
        r, p, y = dq[3], dq[4], dq[5]
        cr, sr = np.cos(r), np.sin(r)
        cp, sp = np.cos(p), np.sin(p)
        cy, sy = np.cos(y + dq[6] * 0.1), np.sin(y + dq[6] * 0.1)
        rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
        ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
        rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        m[:3, :3] = rz @ ry @ rx @ base[:3, :3]
        return RigidTransform(
            base_tcp.target_frame, base_tcp.source_frame, m,
            "synthetic_tabletop_fk", base_tcp.calibration_id, approved=False,
        )

    return fk


def urdf_fk_adapter(
    urdf_path: str | Path,
    *,
    base_frame: str = "L_arm_root",
    tip_frame: str = "L8_Link",
) -> Callable:
    """Wrap urdf_forward_kinematics for J1..J7 vectors (mapped to L*_Joint)."""
    path = Path(urdf_path)

    def fk(q):
        q = np.asarray(q, float)
        if q.shape != (7,) or not np.isfinite(q).all():
            raise ValueError("finite 7-vector q required")
        positions = {J_TO_URDF[name]: float(q[i]) for i, name in enumerate(JOINT_NAMES)}
        pose, _report = urdf_forward_kinematics(
            path, positions, base_frame=base_frame, tip_frame=tip_frame,
        )
        # Re-label tip as tcp for IK frame match against lateral targets.
        return RigidTransform(
            pose.target_frame, "tcp", pose.matrix, pose.source,
            pose.calibration_id, approved=False,
        )

    return fk


def _c_trajectory_to_contract(plan_result: dict[str, Any]) -> dict[str, Any]:
    """Map every IK waypoint (including stationary hand-cue holds) to Trajectory points.

    ``build_offline_trajectory`` drops zero-duration segments; phase_index still
    addresses the full ``joint_waypoints_rad`` list, so holds get a short tick.
    """
    traj = plan_result.get("trajectory")
    waypoints = plan_result.get("joint_waypoints_rad")
    if traj is None or not waypoints:
        raise ValueError("pose path did not produce joint waypoints")
    if tuple(traj["joint_names"]) != JOINT_NAMES:
        raise ValueError("trajectory joint names must be J1..J7")
    hold_s = 0.05
    points = [{"time_from_start_s": 0.0, "q_rad": tuple(float(v) for v in waypoints[0])}]
    seg_by_end = {
        tuple(np.round(seg["end_rad"], 10)): float(seg["start_s"] + seg["duration_s"])
        for seg in traj["segments"]
    }
    t = 0.0
    for prev, curr in zip(waypoints, waypoints[1:]):
        curr_key = tuple(np.round(curr, 10))
        if np.allclose(prev, curr, atol=1e-12):
            t = t + hold_s
        elif curr_key in seg_by_end and seg_by_end[curr_key] > t:
            t = seg_by_end[curr_key]
        else:
            delta = np.max(np.abs(np.asarray(curr) - np.asarray(prev)))
            t = t + max(hold_s, float(delta) * 2.0)
        points.append({
            "time_from_start_s": t,
            "q_rad": tuple(float(v) for v in curr),
        })
    # Ensure strictly increasing times.
    for i in range(1, len(points)):
        if points[i]["time_from_start_s"] <= points[i - 1]["time_from_start_s"]:
            points[i]["time_from_start_s"] = points[i - 1]["time_from_start_s"] + hold_s
    return validate_trajectory({"joint_names": JOINT_NAMES, "points": tuple(points)})

def _default_ik_settings() -> dict[str, Any]:
    return dict(
        position_tolerance_m=1e-4,
        rotation_tolerance_rad=1e-3,
        orientation_weight_m_per_rad=0.05,
        damping=0.05,
        max_step_rad=0.25,
        max_iterations=80,
        difference_step_rad=1e-5,
    )


def build_single_block_plan_bundle(
    *,
    approach_config: dict[str, Any] | None = None,
    approach_config_path: str | Path | None = None,
    limits_config: dict[str, Any] | None = None,
    limits_config_path: str | Path | None = None,
    fk: Callable | None = None,
    world_frame: str = "L_arm_root",
    place_center_m=None,
    pick_center_m=None,
    yaw_rad: float = 0.0,
    scene_version: str = "single-block-synthetic-scene-v1",
    calibration_hash: str = "fit-only-c35-not-approved",
    config_hash: str = "single-block-approach-config-v1",
    observation_id: str | None = "obs-synthetic-single-block",
    observation_age_ok: bool = True,
    ik_settings: dict[str, Any] | None = None,
    now_s: float = 1.0,
    state_stamp_s: float = 1.0,
    max_age_s: float = 1.0,
) -> dict[str, Any]:
    """Assemble a non-executable lateral PlanBundle with hashed trajectory."""
    if approach_config is None:
        if approach_config_path is None:
            raise ValueError("approach config or path required")
        approach_config = load_approach_config(approach_config_path)
    if limits_config is None:
        if limits_config_path is None:
            raise ValueError("joint limits config or path required")
        limits_config = load_joint_limits_config(limits_config_path)

    if not observation_age_ok:
        return _halt_bundle(
            reason="SAFE_HALT: observation expired or rejected",
            approach_config=approach_config,
            limits_config=limits_config,
        )

    limits = joint_limits_from_config(limits_config)
    seed = tuple(float(v) for v in limits_config["seed_rad"])
    if len(seed) != 7:
        raise ValueError("seed_rad must have seven joints")
    if limits_config.get("seed_source") != "synthetic":
        raise ValueError("seed_source must be synthetic for this offline package")

    place = place_center_from_config(approach_config) if place_center_m is None else np.asarray(place_center_m, float)
    pick = pick_center_from_place(place, approach_config) if pick_center_m is None else np.asarray(pick_center_m, float)

    world_pick = block_pose(world_frame, pick, yaw_rad=yaw_rad, calibration_id=calibration_hash)
    world_place = block_pose(world_frame, place, yaw_rad=yaw_rad, calibration_id=calibration_hash)
    tcp_block = tcp_block_transform(approach_config)

    try:
        waypoints = build_lateral_tcp_waypoints(
            world_pick, world_place, tcp_block,
            approach_height_m=float(approach_config["approach_height_m"]),
            lift_clearance_m=float(approach_config["lift_clearance_m"]),
            side_standoff_m=float(approach_config["side_standoff_m"]),
            table_z_m=float(approach_config["table_z_m"]),
        )
    except LateralTemplateRejected as exc:
        return _halt_bundle(
            reason=f"SAFE_HALT: template rejected ({exc})",
            approach_config=approach_config,
            limits_config=limits_config,
        )

    clearance = check_table_clearance(
        waypoints,
        half_extent_m=approach_config["tool_half_extent_m"],
        table_z_m=float(approach_config["table_z_m"]),
        table_half_thickness_m=float(approach_config["table_half_thickness_m"]),
    )
    if clearance["table_clearance"] != "PASS":
        return _halt_bundle(
            reason="SAFE_HALT: table clearance FAIL",
            approach_config=approach_config,
            limits_config=limits_config,
            clearance=clearance,
            waypoints=waypoints,
        )

    if fk is None:
        # Anchor synthetic FK so seed FK equals first TCP waypoint (side wait).
        base_tcp = waypoints[0]["pose"]
        fk = synthetic_tabletop_fk_factory(
            seed_rad=seed,
            lever_m_per_rad=float(limits_config.get("fk_lever_m_per_rad", 0.5)),
            base_tcp=base_tcp,
        )

    targets = [w["pose"] for w in waypoints]
    context = dict(
        scene_version=scene_version,
        calibration_version=calibration_hash,
        clock_domain="host_monotonic",
        epoch="synthetic-single-block",
        state_stamp_s=state_stamp_s,
        now_s=now_s,
        max_age_s=max_age_s,
        start_tolerance_rad=1e-6,
        expected_start_rad=list(seed),
    )
    plan = plan_pose_path(
        fk, targets, list(seed), limits,
        ik_settings=ik_settings or _default_ik_settings(),
        trajectory_context=context,
    )
    if plan.get("ik") != "PASS" or plan.get("trajectory") is None:
        return _halt_bundle(
            reason=f"SAFE_HALT: IK/trajectory failed ({plan.get('reason')})",
            approach_config=approach_config,
            limits_config=limits_config,
            clearance=clearance,
            waypoints=waypoints,
            plan=plan,
        )

    contract_traj = _c_trajectory_to_contract(plan)
    traj_hash = trajectory_hash(contract_traj)

    phase_index = {
        w["phase"]: i for i, w in enumerate(waypoints)
    }
    return {
        "schema_version": SCHEMA,
        "kind": "single_block_plan_bundle",
        "executable": False,
        "motion_enabled": False,
        "control_ready": False,
        "h3_production_plan": False,
        "accuracy_claim": approach_config.get("accuracy_claim", "FIT_ONLY"),
        "supply_pose_source": approach_config.get("supply_pose_source", "synthetic_offset"),
        "trajectory_hash": traj_hash,
        "trajectory": {
            "hash": traj_hash,
            "contract": "contracts.Trajectory",
            "joint_names": list(contract_traj["joint_names"]),
            "points": [
                {
                    "time_from_start_s": p["time_from_start_s"],
                    "q_rad": list(p["q_rad"]),
                }
                for p in contract_traj["points"]
            ],
            "source": "lateral_ik_pose_path",
            "seed_source": "synthetic",
            "limits_model_version": limits.model_version,
            "limits_source": limits.source,
            "ik": "PASS",
        },
        "waypoints": [
            {
                "phase": w["phase"],
                "tcp_position_m": w["tcp_position_m"],
                "hand_preset": w.get("hand_preset"),
            }
            for w in waypoints
        ],
        "phase_index": phase_index,
        "poses": {
            "frame": world_frame,
            "pick_center_m": pick.tolist(),
            "place_center_m": place.tolist(),
            "supply_offset_m": list(approach_config["supply_offset_m"]),
            "yaw_rad": yaw_rad,
            "tcp_geometry_version": approach_config.get("tcp_geometry_version"),
        },
        "identity": {
            "target_id": approach_config.get("target_id"),
            "slot_id": approach_config.get("slot_id"),
            "reference_id": approach_config.get("reference_id"),
            "observation_id": observation_id,
            "frame_id": world_frame,
            "calibration_hash": calibration_hash,
            "config_hash": config_hash,
            "scene_version": scene_version,
            "calibration_candidate_id": approach_config.get("calibration_candidate_id"),
        },
        "collision_summary": {
            "table_clearance": clearance["table_clearance"],
            "full_collision": "UNKNOWN",
            "status": clearance["table_clearance"],
            "scope": clearance["scope"],
            "collisions": clearance["collisions"],
            "missing": clearance["missing"],
            "note": "full_collision must remain UNKNOWN; never rewrite as PASS",
        },
        "dispatch_allowed": False,
        "status": "PLAN_READY_NON_EXECUTABLE",
        "notes": [
            "Separate from m-shadow-plan-bundle-0.1 (host checklist wiring).",
            "C35 accuracy_claim=FIT_ONLY; approved binding not claimed.",
            "control_ready/executable/motion_enabled hard false.",
        ],
    }


def _halt_bundle(
    *,
    reason: str,
    approach_config: dict[str, Any],
    limits_config: dict[str, Any],
    clearance: dict[str, Any] | None = None,
    waypoints: list | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "kind": "single_block_plan_bundle",
        "executable": False,
        "motion_enabled": False,
        "control_ready": False,
        "h3_production_plan": False,
        "accuracy_claim": approach_config.get("accuracy_claim", "FIT_ONLY"),
        "supply_pose_source": approach_config.get("supply_pose_source", "synthetic_offset"),
        "trajectory_hash": None,
        "trajectory": None,
        "waypoints": [
            {"phase": w["phase"], "tcp_position_m": w["tcp_position_m"], "hand_preset": w.get("hand_preset")}
            for w in (waypoints or [])
        ],
        "identity": {
            "target_id": approach_config.get("target_id"),
            "slot_id": approach_config.get("slot_id"),
            "reference_id": approach_config.get("reference_id"),
            "calibration_hash": None,
            "config_hash": None,
            "scene_version": None,
        },
        "collision_summary": {
            "table_clearance": (clearance or {}).get("table_clearance", "UNKNOWN"),
            "full_collision": "UNKNOWN",
            "status": (clearance or {}).get("table_clearance", "UNKNOWN"),
            "collisions": (clearance or {}).get("collisions", []),
            "missing": (clearance or {}).get("missing", ["not_evaluated"]),
        },
        "limits_model_version": limits_config.get("model_version"),
        "limits_source": limits_config.get("source"),
        "dispatch_allowed": False,
        "status": "SAFE_HALT",
        "reason": reason,
        "plan_diagnostics": {
            "ik": (plan or {}).get("ik"),
            "reason": (plan or {}).get("reason"),
        },
        "notes": ["No trajectory dispatched; SAFE_HALT."],
    }
