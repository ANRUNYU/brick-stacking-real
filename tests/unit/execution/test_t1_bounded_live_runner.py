"""T1 bounded runner skeleton defaults refuse motion."""
from __future__ import annotations

import pytest

from brick_stacking.execution.t1_bounded_live_runner import (
    MAX_SHORT_COMBO_STEP_DEG,
    MAX_SINGLE_JOINT_STEP_RAD,
    build_t1_bounded_dry_plan,
    build_t1_short_combo_dry_plan,
    default_short_combo_waypoints,
    evaluate_t1_prerequisites,
)


def _capture() -> dict:
    received = [
        {
            "motor_id": mid,
            "position_sdk_rad": 0.01 * (mid - 60),
            "host_receive_monotonic_s": float(mid),
        }
        for mid in range(61, 66)
    ]
    received.extend(
        [
            {"motor_id": 66, "position_raw_u16": 32000, "status": 0, "fault": 0},
            {"motor_id": 67, "position_raw_u16": 33000, "status": 0, "fault": 0},
        ]
    )
    return {"status": "RAW_SEVEN_AXIS_CAPTURED", "received": received}


def test_default_refuses_motion_and_control_ready():
    prereq = evaluate_t1_prerequisites(
        rest_capture=_capture(),
        motion_enabled=True,
        control_ready=True,
        block_present=True,
    )
    assert prereq["live_motion_allowed"] is False
    assert prereq["control_ready"] is False
    assert "motion_enabled_refused_by_default_skeleton" in prereq["blocked_by"]
    assert "control_ready_must_stay_false_here" in prereq["blocked_by"]
    assert "block_present_t1_requires_empty" in prereq["blocked_by"]


def test_dry_plan_step_cap_and_wrist_forbidden():
    capture = _capture()
    prereq = evaluate_t1_prerequisites(rest_capture=capture)
    with pytest.raises(ValueError):
        build_t1_bounded_dry_plan(
            rest_capture=capture, joint="J6", prerequisites=prereq
        )
    with pytest.raises(ValueError):
        build_t1_bounded_dry_plan(
            rest_capture=capture,
            step_rad=MAX_SINGLE_JOINT_STEP_RAD + 0.01,
            prerequisites=prereq,
        )
    plan = build_t1_bounded_dry_plan(
        rest_capture=capture, joint="J1", step_rad=0.02, prerequisites=prereq
    )
    assert plan["executable"] is False
    assert abs(plan["step_rad"] - 0.02) < 1e-12


def test_short_combo_out_and_back_defaults_refuse_motion():
    wps = default_short_combo_waypoints(joints=(1, 2, 3), step_deg=1.0)
    assert len(wps) == 6
    assert [w["joint"] for w in wps] == [1, 2, 3, 3, 2, 1]
    assert [w["direction"] for w in wps] == [1, 1, 1, -1, -1, -1]
    plan = build_t1_short_combo_dry_plan(waypoints=wps, motion_enabled=True)
    assert plan["executable"] is False
    assert plan["motion_enabled"] is False
    assert plan["control_ready"] is False
    assert plan["provenance"]["not_h3_plan_bundle"] is True
    assert "motion_enabled_refused_by_default_skeleton" in (plan["refuse_reason"] or "")


def test_short_combo_rejects_wrist_and_oversized_step():
    with pytest.raises(ValueError):
        default_short_combo_waypoints(joints=(1, 6), step_deg=1.0)
    with pytest.raises(ValueError):
        default_short_combo_waypoints(
            joints=(1,), step_deg=MAX_SHORT_COMBO_STEP_DEG + 0.01
        )
