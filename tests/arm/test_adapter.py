import json
from types import SimpleNamespace

import pytest

from brick_stacking.arm.adapter import JOINT_NAMES, MockArm, replay_execution, trajectory_hash


@pytest.fixture
def trajectory():
    return {"joint_names": JOINT_NAMES, "points": (
        {"time_from_start_s": 0, "q_rad": (0,) * 7},
        {"time_from_start_s": 1, "q_rad": (0.1,) * 7},
        {"time_from_start_s": 2, "q_rad": (-0.2,) * 7},
    )}


@pytest.fixture
def permit(trajectory):
    return {
        "device_id": "mock-arm", "config_hash": "mock-config", "calibration_hash": "mock-calibration",
        "scene_version": "mock-scene", "trajectory_hash": trajectory_hash(trajectory),
        "valid_until_host_monotonic_s": 4,
    }


@pytest.fixture
def mock():
    clock = SimpleNamespace(now=0.0)
    return MockArm((0.3,) * 7, clock=lambda: clock.now), clock


@pytest.mark.parametrize(("field", "value", "message"), [
    ("joint_names", JOINT_NAMES[::-1], "joint order"),
    ("joint_names", JOINT_NAMES[:-1], "joint order"),
    ("points", (), "at least one point"),
    ("time_from_start_s", 0, "strictly increasing"),
    ("time_from_start_s", 3, "strictly increasing"),
    ("time_from_start_s", -1, "nonnegative"),
    ("time_from_start_s", float("nan"), "finite"),
    ("time_from_start_s", float("inf"), "finite"),
    ("q_rad", (0,) * 6, "seven joint positions"),
    ("q_rad", (float("inf"),) * 7, "finite"),
    ("q_rad", (float("nan"),) * 7, "finite"),
    ("q_rad", (True,) * 7, "finite"),
])
def test_rejects_malformed_trajectory(mock, trajectory, permit, field, value, message):
    arm, _ = mock
    if field in trajectory:
        trajectory[field] = value
    else:
        trajectory["points"][1][field] = value
    with pytest.raises(ValueError, match=message):
        arm.execute_trajectory(trajectory, permit)
    assert arm.read_state()["q_rad"] == (0.3,) * 7


@pytest.mark.parametrize("field", ["device_id", "config_hash", "calibration_hash", "scene_version", "trajectory_hash"])
def test_rejects_mismatched_permit(mock, trajectory, permit, field):
    arm, _ = mock
    permit[field] = "wrong"
    with pytest.raises(ValueError, match="permit does not match"):
        arm.execute_trajectory(trajectory, permit)


@pytest.mark.parametrize(("now", "deadline", "reason"), [
    (4, None, "expired"),
    (0, 0, "expired"),
    (0, 2, "cannot finish"),
    (0, float("inf"), "finite"),
])
def test_expiry_before_start(mock, trajectory, permit, now, deadline, reason):
    arm, clock = mock
    clock.now = now
    with pytest.raises(ValueError, match=reason):
        arm.execute_trajectory(trajectory, permit, valid_until_host_monotonic_s=deadline)


def test_execution_respects_timing_and_uses_snapshot(mock, trajectory, permit):
    arm, clock = mock
    command = arm.execute_trajectory(trajectory, permit)
    trajectory["points"][2]["q_rad"] = (1.0,) * 7
    assert arm.read_state()["q_rad"] == (0.3,) * 7
    assert arm.step(command)["feedback"]["q_rad"] == (0.0,) * 7
    clock.now = 0.75
    assert arm.step(command)["feedback"]["host_receive_stamp"] == 0
    clock.now = 1
    result = arm.step(command)
    assert result["status"] == "RUNNING"
    assert result["feedback"]["q_rad"] == (0.1,) * 7
    result["feedback"]["q_rad"] = (123.0,) * 7
    assert arm.get_execution_result(command)["feedback"]["q_rad"] == (0.1,) * 7
    clock.now = 2
    result = arm.step(command)
    assert result["status"] == "SUCCEEDED"
    assert result["feedback"]["q_rad"] == (-0.2,) * 7
    assert result["feedback"]["source"] == "mock"
    assert result["ended_host_monotonic_s"] == 2
    assert not arm.cancel(command)


def test_cancellation_blocks_due_and_future_points(mock, trajectory, permit):
    arm, clock = mock
    command = arm.execute_trajectory(trajectory, permit)
    with pytest.raises(RuntimeError, match="already running"):
        arm.execute_trajectory(trajectory, permit)
    arm.step(command)
    clock.now = 1
    with pytest.raises(KeyError):
        arm.cancel("other-command")
    assert arm.cancel(command)
    assert not arm.cancel(command)
    clock.now = 3
    result = arm.step(command)
    assert result["status"] == "CANCELLED" and result["ended_host_monotonic_s"] == 1
    assert arm.read_state()["q_rad"] == (0.0,) * 7


def test_expiry_during_run_blocks_overdue_points(mock, trajectory, permit):
    arm, clock = mock
    command = arm.execute_trajectory(trajectory, permit, valid_until_host_monotonic_s=3)
    arm.step(command)
    clock.now = 3
    result = arm.step(command)
    assert result["status"] == "FAILED" and "expired" in result["reason"]
    assert arm.read_state()["q_rad"] == (0.0,) * 7


def test_replay_from_json_and_cancel(trajectory, permit):
    trajectory = json.loads(json.dumps(trajectory))
    assert trajectory_hash(trajectory) == permit["trajectory_hash"]
    trace = replay_execution(trajectory, permit, (0.3,) * 7, (
        (0, "step"), (1, "step"), (2, "cancel"), (2, "step"),
    ))
    trace = json.loads(json.dumps(trace))
    assert [row["status"] for row in trace] == ["RUNNING"] * 3 + ["CANCELLED"] * 2
    assert trace[-1]["feedback"]["q_rad"] == [0.1] * 7
    assert trace[-1]["feedback"]["host_receive_stamp"] == 1
    with pytest.raises(ValueError, match="nondecreasing"):
        replay_execution(trajectory, permit, (0,) * 7, ((1, "step"), (0, "cancel")))
