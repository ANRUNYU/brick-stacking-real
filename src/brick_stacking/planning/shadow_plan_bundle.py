"""Shadow / host-checklist PlanBundle with a hashed offline trajectory.

This is NOT the H3 production lateral-approach PlanBundle (#20). It binds
pre_grasp shadow Inspection identity fields to a machine-readable plan package
whose ``trajectory_hash`` is computed via ``arm.adapter.trajectory_hash``
(never hand-invented). Default ``motion_enabled=false`` / ``executable=false``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brick_stacking.arm.adapter import JOINT_NAMES, trajectory_hash, validate_trajectory
from brick_stacking.contracts import Trajectory

SCHEMA = "m-shadow-plan-bundle-0.1"

# Explicit offline shadow waypoints for host-path wiring only.
# Not an IK solution of the first-placement pose; not H3 clearance-validated.
_SHADOW_OFFLINE_WAYPOINTS_RAD: tuple[tuple[float, ...], ...] = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.02, -0.01, 0.015, 0.0, 0.0, 0.01, -0.01),
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
)
_SHADOW_OFFLINE_TIMES_S: tuple[float, ...] = (0.0, 1.0, 2.0)


def _context_from_diagnostic(diagnostic: dict[str, Any] | None) -> dict[str, Any]:
    diag = diagnostic or {}
    ctx = dict(diag.get("context_present") or {})
    fields = diag.get("live_permit_field_status") or {}
    if not ctx.get("calibration_hash"):
        cal = (fields.get("calibration_hash") or {}).get("value")
        if cal:
            ctx["calibration_hash"] = cal
    if not ctx.get("config_hash_or_profile_hash"):
        cfg = (fields.get("config_hash") or {}).get("value")
        if cfg:
            ctx["config_hash_or_profile_hash"] = cfg
    if not ctx.get("scene_version"):
        scene = (fields.get("scene_version") or {}).get("value")
        if scene:
            ctx["scene_version"] = scene
    return ctx


def _context_from_shadow(shadow: dict[str, Any] | None) -> dict[str, Any]:
    if not shadow:
        return {}
    export = shadow.get("export") or {}
    handoffs = list(export.get("localized_review_handoffs") or [])
    preferred = None
    for row in reversed(handoffs):
        if row.get("scene_consistent") is True:
            preferred = row
            break
    if preferred is None and handoffs:
        preferred = handoffs[-1]
    src = preferred or export
    return {
        "target_id": src.get("target_id") or export.get("target_id"),
        "slot_id": src.get("slot_id") or export.get("slot_id"),
        "region_id": src.get("region_id") or export.get("region_id"),
        "reference_id": src.get("reference_id"),
        "observation_id": src.get("observation_id"),
        "frame_id": src.get("frame_id"),
        "calibration_hash": src.get("calibration_hash") or export.get("calibration_hash"),
        "config_hash_or_profile_hash": src.get("profile_hash") or export.get("profile_hash"),
        "scene_version": src.get("epoch") or export.get("epoch"),
        "epoch": src.get("epoch"),
        "clock_domain": src.get("clock_domain"),
        "shadow_inspection_status": None,
    }


def build_shadow_offline_trajectory() -> Trajectory:
    points = tuple(
        {"time_from_start_s": t, "q_rad": q}
        for t, q in zip(_SHADOW_OFFLINE_TIMES_S, _SHADOW_OFFLINE_WAYPOINTS_RAD, strict=True)
    )
    return validate_trajectory({"joint_names": JOINT_NAMES, "points": points})


def build_shadow_plan_bundle(
    *,
    diagnostic_permit: dict[str, Any] | None = None,
    shadow_report: dict[str, Any] | None = None,
    diagnostic_path: str | None = None,
    shadow_path: str | None = None,
) -> dict[str, Any]:
    """Assemble a non-executable shadow PlanBundle with a real trajectory_hash."""
    ctx = _context_from_shadow(shadow_report)
    ctx.update({k: v for k, v in _context_from_diagnostic(diagnostic_permit).items() if v})

    trajectory = build_shadow_offline_trajectory()
    traj_hash = trajectory_hash(trajectory)
    config_hash = ctx.get("config_hash_or_profile_hash")
    calibration_hash = ctx.get("calibration_hash")
    scene_version = ctx.get("scene_version") or ctx.get("epoch")

    missing_identity = [
        name
        for name, value in (
            ("calibration_hash", calibration_hash),
            ("config_hash_or_profile_hash", config_hash),
            ("scene_version", scene_version),
        )
        if not value
    ]

    return {
        "schema_version": SCHEMA,
        "kind": "shadow_plan_bundle",
        "executable": False,
        "motion_enabled": False,
        "control_ready": False,
        "h3_production_plan": False,
        "trajectory_hash": traj_hash,
        "trajectory": {
            "hash": traj_hash,
            "contract": "contracts.Trajectory",
            "joint_names": list(trajectory["joint_names"]),
            "points": [
                {
                    "time_from_start_s": p["time_from_start_s"],
                    "q_rad": list(p["q_rad"]),
                }
                for p in trajectory["points"]
            ],
            "source": "offline_shadow_waypoints",
            "provenance": (
                "synthetic offline waypoints for host checklist wiring; "
                "not IK of shadow Inspection pose; not H3 clearance-validated"
            ),
        },
        "identity": {
            "target_id": ctx.get("target_id"),
            "slot_id": ctx.get("slot_id"),
            "region_id": ctx.get("region_id"),
            "reference_id": ctx.get("reference_id"),
            "observation_id": ctx.get("observation_id"),
            "frame_id": ctx.get("frame_id"),
            "calibration_hash": calibration_hash,
            "config_hash": config_hash,
            "scene_version": scene_version,
            "epoch": ctx.get("epoch"),
            "clock_domain": ctx.get("clock_domain"),
            "shadow_inspection_status": ctx.get("shadow_inspection_status"),
        },
        "collision_summary": {
            "status": "UNKNOWN",
            "scope": "not_checked_on_shadow_host_path",
            "missing": [
                "lateral_approach_template",
                "ik_of_first_placement",
                "arm_hand_mesh",
                "table_thin_box_clearance",
            ],
        },
        "inputs": {
            "diagnostic_path": diagnostic_path,
            "shadow_path": shadow_path,
        },
        "missing_for_h3_production": [
            "issue #20 lateral approach → descend → lift → retreat template",
            "IK of LocalizedBlock / first-placement pose",
            "clearance + collision PASS (not UNKNOWN)",
            "C49 / grasp_version / O6 preset binding",
        ],
        "identity_gaps": missing_identity,
        "notes": [
            "trajectory_hash is sha256 of validated contracts.Trajectory JSON (arm.adapter).",
            "Do not treat this package as a live-executable PlanBundle.",
            "Do not copy into contracts.Permit without SafetyGate issuance.",
            "Host checklist may mark plan_bundle_trajectory_hash PASS when this hash is present.",
        ],
        "can_opened": False,
        "commands_sent": 0,
    }


def load_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))
