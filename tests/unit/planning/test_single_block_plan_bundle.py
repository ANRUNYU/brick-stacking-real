"""Single-block PlanBundle emission and flag tests."""
from pathlib import Path

import pytest

from brick_stacking.arm.adapter import trajectory_hash, validate_trajectory
from brick_stacking.planning.single_block_plan_bundle import (
    SCHEMA,
    build_single_block_plan_bundle,
    load_joint_limits_config,
)

ROOT = Path(__file__).resolve().parents[3]
APPROACH = ROOT / "config/planning/single_block_approach.yaml"
LIMITS = ROOT / "config/planning/single_block_joint_limits_synthetic.yaml"


def _build(**kwargs):
    return build_single_block_plan_bundle(
        approach_config_path=APPROACH,
        limits_config_path=LIMITS,
        **kwargs,
    )


def test_bundle_emits_hash_and_non_executable_flags():
    bundle = _build()
    assert bundle["schema_version"] == SCHEMA
    assert bundle["status"] == "PLAN_READY_NON_EXECUTABLE"
    assert bundle["executable"] is False
    assert bundle["motion_enabled"] is False
    assert bundle["control_ready"] is False
    assert bundle["accuracy_claim"] == "FIT_ONLY"
    assert bundle["supply_pose_source"] == "synthetic_offset"
    assert bundle["collision_summary"]["table_clearance"] == "PASS"
    assert bundle["collision_summary"]["full_collision"] == "UNKNOWN"
    traj = validate_trajectory({
        "joint_names": bundle["trajectory"]["joint_names"],
        "points": tuple(
            {"time_from_start_s": p["time_from_start_s"], "q_rad": tuple(p["q_rad"])}
            for p in bundle["trajectory"]["points"]
        ),
    })
    assert bundle["trajectory_hash"] == trajectory_hash(traj)
    assert bundle["poses"]["supply_offset_m"][0] == pytest.approx(0.15)
    assert bundle["identity"]["reference_id"] == "table_black_cross_20mm"


def test_refuse_limits_without_model_version():
    data = load_joint_limits_config(LIMITS)
    data = dict(data)
    data.pop("model_version")
    with pytest.raises(ValueError, match="model_version"):
        build_single_block_plan_bundle(
            approach_config_path=APPROACH,
            limits_config=data,
        )


def test_expired_observation_safe_halt():
    bundle = _build(observation_age_ok=False)
    assert bundle["status"] == "SAFE_HALT"
    assert bundle["trajectory_hash"] is None
    assert bundle["dispatch_allowed"] is False


def test_clearance_failure_safe_halt():
    from brick_stacking.planning.lateral_approach import load_approach_config

    cfg = dict(load_approach_config(APPROACH))
    cfg["approach_height_m"] = 0.001
    cfg["tool_half_extent_m"] = [0.08, 0.08, 0.08]
    # Low approach with fat tool should fail table scrape or template reject.
    bundle = build_single_block_plan_bundle(
        approach_config=cfg,
        limits_config_path=LIMITS,
    )
    assert bundle["status"] == "SAFE_HALT"
    assert bundle["trajectory"] is None
