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


@pytest.fixture
def feedback_mock():
    driver = SimpleNamespace(now=0.0, sample=None)
    arm = MockArm((0.3,) * 7, clock=lambda: driver.now,
                  feedback_reader=lambda: driver.sample, goal_tolerance_rad=0.01)
    return arm, driver


def test_ack_and_outside_tolerance_wait_for_fresh_feedback(feedback_mock, trajectory, permit):
    arm, driver = feedback_mock
    command = arm.execute_trajectory(trajectory, permit)
    assert arm.get_execution_status(command) == "RUNNING"
    driver.now = 2
    result = arm.step(command)
    assert result["status"] == "RUNNING" and result["feedback"] is None
    assert result["reason"] == "awaiting mock feedback"

    driver.now = 2.01
    driver.sample = arm.read_state()
    driver.sample["q_rad"] = (-0.2,) * 6 + (-0.18,)
    result = arm.step(command)
    assert result["status"] == "RUNNING" and result["reason"] == "mock feedback outside goal tolerance"
    assert result["feedback"]["q_rad"][-1] == -0.18

    driver.now = 2.02
    driver.sample = arm.read_state()
    driver.sample["q_rad"] = (-0.2,) * 6 + (-0.195,)
    result = arm.step(command)
    assert arm.get_execution_status(command) == "SUCCEEDED"
    assert result["feedback"]["q_rad"][-1] == -0.195
    assert result["reason"] is None and result["ended_host_monotonic_s"] == 2.02
    assert len(arm._joints.events) == len(trajectory["points"])


@pytest.mark.parametrize(("field", "value"), [
    ("host_receive_stamp", 1.99),  # Fresh by age, but earlier than final dispatch.
    ("host_receive_stamp", 2),  # Same timestamp cannot prove it followed dispatch.
    ("host_receive_stamp", 2.05),
    ("host_receive_stamp", float("nan")),
    ("device_id", "another-arm"),
    ("frame_id", "another-frame"),
    ("epoch", "old-epoch"),
    ("source", "recorded"),
    ("source", "real"),
    ("clock_domain", "device"),
    ("validity", "INVALID"),
    ("fault", "mock-fault"),
    ("joint_names", JOINT_NAMES[::-1]),
    ("q_rad", (-0.2,) * 6 + (None,)),
    ("q_rad", (-0.2,) * 6 + (float("inf"),)),
])
def test_invalid_feedback_never_confirms_arrival(feedback_mock, trajectory, permit, field, value):
    arm, driver = feedback_mock
    command = arm.execute_trajectory(trajectory, permit)
    driver.now = 2
    arm.step(command)
    driver.now = 2.01
    driver.sample = arm.read_state()
    driver.sample[field] = value
    result = arm.step(command)
    assert result["status"] == "RUNNING" and result["reason"] and result["feedback"] is None


def test_stale_and_repeated_feedback_cannot_confirm_arrival(feedback_mock, trajectory, permit):
    arm, driver = feedback_mock
    command = arm.execute_trajectory(trajectory, permit)
    driver.now = 2
    arm.step(command)
    driver.sample = arm.read_state()
    driver.now = 2.2
    assert arm.step(command)["reason"] == "stale or future mock feedback"

    driver.sample = arm.read_state()
    driver.sample["q_rad"] = (0.0,) * 7
    arm.step(command)
    driver.now = 2.21
    driver.sample.update(host_receive_stamp=2.21, q_rad=(-0.2,) * 7)
    result = arm.step(command)
    assert result["reason"] == "repeated or out-of-order mock feedback"
    assert result["feedback"]["q_rad"] == (0.0,) * 7


def test_cancel_after_dispatch_ignores_late_feedback(feedback_mock, trajectory, permit):
    arm, driver = feedback_mock
    command = arm.execute_trajectory(trajectory, permit)
    driver.now = 2
    arm.step(command)
    assert arm.cancel(command)
    driver.now = 2.01
    driver.sample = arm.read_state()
    result = arm.step(command)
    assert result["status"] == "CANCELLED" and result["feedback"] is None


def test_feedback_returning_at_permit_deadline_cannot_complete(trajectory, permit):
    clock = SimpleNamespace(now=0.0, sample=None)

    def delayed_feedback():
        clock.now = 4
        return clock.sample

    arm = MockArm((0.3,) * 7, clock=lambda: clock.now, feedback_reader=delayed_feedback)
    command = arm.execute_trajectory(trajectory, permit)
    clock.now = 2
    clock.sample = arm.read_state()
    clock.sample.update(host_receive_stamp=3.99, q_rad=(-0.2,) * 7)
    result = arm.step(command)
    assert arm.get_execution_status(command) == "FAILED"
    assert result["ended_host_monotonic_s"] == 4 and "expired" in result["reason"]
