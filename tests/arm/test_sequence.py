from types import SimpleNamespace

import pytest

from brick_stacking.arm.adapter import JOINT_NAMES, MockArm, trajectory_hash
from brick_stacking.arm.recovery import MockRecoverySession
from brick_stacking.arm.sequence import MultiSegmentRun


@pytest.fixture
def scenario():
    clock = SimpleNamespace(now=0.0)
    arm = MockArm((0.0,) * 7, clock=lambda: clock.now)
    segments = tuple({"phase": phase, "trajectory": {
        "joint_names": JOINT_NAMES,
        "points": ({"time_from_start_s": 1.0, "q_rad": (goal,) * 7},),
    }} for phase, goal in (("layer-1", 0.1), ("layer-2", 0.2), ("layer-3", 0.3)))
    context = {"config_hash": "mock-config", "calibration_hash": "mock-calibration", "scene_version": "mock-scene"}
    plan = dict(context, feasible=True, rejection_reason=None, segments=segments,
                collision_model_hash="mock-model", valid_until_host_monotonic_s=10.0)
    permits = [dict(context, device_id="mock-arm", trajectory_hash=trajectory_hash(segment["trajectory"]),
                    valid_until_host_monotonic_s=10.0) for segment in segments]

    def start():
        return MultiSegmentRun(scenario.arm, plan, permits, joint_limits_rad=((-0.5, 0.5),) * 7,
                               max_state_age_s=0.25, clock=lambda: clock.now)

    scenario = SimpleNamespace(arm=arm, clock=clock, plan=plan, permits=permits, start=start)
    return scenario


def test_three_layers_report_order_progress_and_timing(scenario):
    run = scenario.start()
    assert run.progress().status == "PENDING"
    scenario.plan["segments"][2]["trajectory"]["points"][0]["q_rad"] = (-0.4,) * 7
    for index in range(3):
        scenario.clock.now = index * 2.0
        progress = run.step()
        assert progress.status == "RUNNING" and progress.completed_segments == index
        assert run.progress() == progress
        scenario.clock.now += 1.0
        progress = run.step()
        assert progress.completed_segments == index + 1
        assert progress.segments[-1].elapsed_s == 1.0
    assert progress.status == "SUCCEEDED" and progress.total_segments == 3
    assert progress.elapsed_s == 5.0
    assert [segment.phase for segment in progress.segments] == ["layer-1", "layer-2", "layer-3"]
    assert len({segment.command_id for segment in progress.segments}) == 3
    assert scenario.arm.read_state()["q_rad"] == (0.3,) * 7
    scenario.clock.now = 12.0
    assert run.step() == progress and not run.cancel()


@pytest.mark.parametrize("cancel_time", ["pending", "active", "between"])
def test_cancel_prevents_any_later_segment(scenario, cancel_time):
    run = scenario.start()
    if cancel_time != "pending":
        run.step()
    if cancel_time == "between":
        scenario.clock.now = 1.0
        run.step()
    assert run.cancel()
    scenario.clock.now = 5.0
    progress = run.step()
    assert progress.status == "CANCELLED"
    assert progress.completed_segments == (1 if cancel_time == "between" else 0)
    assert len(progress.segments) == (0 if cancel_time == "pending" else 1)
    if cancel_time == "active":
        assert progress.segments[0].status == "CANCELLED"
    assert scenario.arm.read_state()["q_rad"] == ((0.1 if cancel_time == "between" else 0.0),) * 7


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("host_receive_stamp", 0.0, "stale"),
    ("host_receive_stamp", 0.95, "stale"),  # Young enough, but predates the prior segment's finish.
    ("host_receive_stamp", 2.0, "future"),
    ("epoch", "restarted", "epoch"),
    ("q_rad", (0.6,) * 7, "outside joint limits"),
])
def test_second_segment_checks_freshness_and_actual_limits(scenario, monkeypatch, field, value, reason):
    run = scenario.start()
    run.step()
    scenario.clock.now = 1.0
    run.step()
    scenario.clock.now = 1.05
    snapshot = scenario.arm.read_state()
    snapshot[field] = value
    monkeypatch.setattr(scenario.arm, "read_state", lambda: snapshot)
    progress = run.step()
    assert progress.status == "FAILED" and progress.completed_segments == 1
    assert len(progress.segments) == 1 and reason in progress.reason


def test_later_waypoint_and_permit_preflight_before_any_dispatch(scenario):
    trajectory = scenario.plan["segments"][2]["trajectory"]
    trajectory["points"][0]["q_rad"] = (0.7,) * 7
    with pytest.raises(ValueError, match="permit does not match"):
        scenario.start()
    scenario.permits[2]["trajectory_hash"] = trajectory_hash(trajectory)
    with pytest.raises(ValueError, match="outside joint limits"):
        scenario.start()
    assert scenario.arm.read_state()["q_rad"] == (0.0,) * 7


@pytest.mark.parametrize("expiry", ["plan", "permit"])
def test_expiry_between_segments_blocks_new_dispatch(scenario, expiry):
    if expiry == "plan":
        scenario.plan["valid_until_host_monotonic_s"] = 2.0
    else:
        scenario.permits[1]["valid_until_host_monotonic_s"] = 2.0
    run = scenario.start()
    run.step()
    scenario.clock.now = 1.0
    run.step()
    scenario.clock.now = 2.0
    progress = run.step()
    assert progress.status == "FAILED" and progress.completed_segments == 1
    assert len(progress.segments) == 1 and "expired" in progress.reason


def test_active_segment_expiry_freezes_progress(scenario):
    run = scenario.start()
    run.step()
    scenario.clock.now = 10.0
    progress = run.step()
    assert progress.status == "FAILED" and progress.completed_segments == 0
    assert len(progress.segments) == 1 and progress.segments[0].status == "FAILED"
    assert scenario.arm.read_state()["q_rad"] == (0.0,) * 7


def test_limit_violation_in_feedback_aborts_remaining_segments(scenario):
    driver = SimpleNamespace(feedback=None)
    scenario.arm._feedback_reader = lambda: driver.feedback
    run = scenario.start()
    run.step()
    scenario.clock.now = 1.0
    assert run.step().status == "RUNNING"
    scenario.clock.now = 1.01
    driver.feedback = scenario.arm.read_state()
    driver.feedback["q_rad"] = (0.6,) * 7
    progress = run.step()
    assert progress.status == "FAILED" and progress.completed_segments == 0
    assert progress.segments[0].status == "CANCELLED" and "feedback J1 outside" in progress.reason


@pytest.mark.parametrize(("error", "kind", "sent"), [
    (TimeoutError, "TIMEOUT", True),
    (ConnectionError, "DISCONNECTED", False),
])
def test_transport_fault_latches_and_prevents_later_segments(scenario, error, kind, sent):
    def fail():
        raise error()

    scenario.arm = MockArm((0.0,) * 7, clock=lambda: scenario.clock.now, feedback_reader=fail)
    run = scenario.start()
    run.step()
    scenario.clock.now = 1.0
    progress = run.step()
    assert progress.status == "FAILED" and progress.fault.kind == kind
    assert progress.fault.stop["request_sent"] is sent
    assert not progress.fault.stop["feedback_confirmed"]
    assert progress.fault.stop["hold_capable"] is None
    assert len(progress.segments) == 1 and progress.completed_segments == 0
    assert [event["kind"] for event in scenario.arm._joints.events] == (
        ["mock_target", "mock_stop"] if sent else ["mock_target"]
    )
    scenario.clock.now = 2.0
    assert run.step() == progress and not run.cancel()
    with pytest.raises(RuntimeError, match="fault latched"):
        scenario.arm.execute_trajectory(scenario.plan["segments"][1]["trajectory"], scenario.permits[1])


def test_missing_feedback_times_out_before_permit_expiry(scenario):
    scenario.arm = MockArm((0.0,) * 7, clock=lambda: scenario.clock.now,
                           feedback_reader=lambda: None, feedback_timeout_s=0.5)
    run = scenario.start()
    run.step()
    scenario.clock.now = 1.0
    assert run.step().status == "RUNNING"
    scenario.clock.now = 1.5
    progress = run.step()
    assert progress.status == "FAILED" and progress.fault.kind == "TIMEOUT"
    assert len(progress.segments) == 1


def test_expiry_with_active_segment_reports_only_mock_stop(scenario):
    run = scenario.start()
    run.step()
    scenario.clock.now = 10.0
    progress = run.step()
    assert progress.fault.kind == "EXPIRED" and progress.fault.stop["request_sent"]
    assert not progress.fault.stop["feedback_confirmed"]
    assert scenario.arm.read_state()["q_rad"] == (0.0,) * 7


@pytest.mark.parametrize(("error", "kind"), [(ConnectionError, "DISCONNECTED"), (TimeoutError, "TIMEOUT")])
def test_start_state_fault_dispatches_nothing(scenario, monkeypatch, error, kind):
    def fail():
        raise error()

    monkeypatch.setattr(scenario.arm, "read_state", fail)
    progress = scenario.start().step()
    assert progress.status == "FAILED" and progress.fault.kind == kind
    assert not progress.segments and not progress.fault.stop["request_sent"]


def test_stop_transport_failure_does_not_leave_run_active(scenario, monkeypatch):
    def fail():
        raise ConnectionError()

    run = scenario.start()
    run.step()
    monkeypatch.setattr(scenario.arm._joints, "stop", fail)
    assert not run.cancel()
    progress = run.step()
    assert progress.status == "FAILED" and progress.fault.kind == "DISCONNECTED"
    assert not progress.fault.stop["request_sent"]
    assert scenario.arm.read_state()["q_rad"] == (0.0,) * 7


def test_target_transport_failure_does_not_retry_point(scenario, monkeypatch):
    attempts = []

    def fail(target):
        attempts.append(target)
        raise ConnectionError()

    monkeypatch.setattr(scenario.arm._joints, "simulate_joint_target", fail)
    run = scenario.start()
    run.step()
    scenario.clock.now = 1.0
    result = run.step()
    assert result.status == "FAILED" and result.fault.kind == "DISCONNECTED"
    scenario.clock.now = 2.0
    assert run.step() == result and attempts == [(0.1,) * 7]


def test_restart_never_reloads_old_observation_or_command(scenario):
    old_run = scenario.start()
    old_state = scenario.arm.read_state()
    old_command = old_run.step().segments[0].command_id

    session = MockRecoverySession(
        (0.05,) * 7, joint_limits_rad=((-0.5, 0.5),) * 7, max_state_age_s=0.25,
        feedback_timeout_s=0.5, clock=lambda: scenario.clock.now,
    )
    with pytest.raises(ValueError, match="new observation"):
        session.start(old_state["sample_id"], scenario.plan, scenario.permits)
    fresh = session.observe()
    assert fresh["epoch"] != old_state["epoch"] and fresh["q_rad"] == (0.05,) * 7
    with pytest.raises(ValueError, match="new observation"):
        session.start(old_state["sample_id"], scenario.plan, scenario.permits)
    scenario.clock.now = 0.5
    with pytest.raises(ValueError, match="observation expired"):
        session.start(fresh["sample_id"], scenario.plan, scenario.permits)

    fresh = session.observe()
    trajectory = {"joint_names": JOINT_NAMES, "points": (
        {"time_from_start_s": 0.0, "q_rad": fresh["q_rad"]},
        {"time_from_start_s": 1.0, "q_rad": (0.15,) * 7},
    )}
    plan = dict(scenario.plan, segments=({"phase": "replanned", "trajectory": trajectory},))
    permit = dict(scenario.permits[0], trajectory_hash=trajectory_hash(trajectory))
    run = session.start(fresh["sample_id"], plan, (permit,))
    assert run.progress().status == "PENDING" and not run.progress().segments
    assert run.step().segments[0].command_id != old_command
    scenario.clock.now = 1.5
    result = run.step()
    assert result.status == "SUCCEEDED" and result.completed_segments == 1
    assert result.segments[0].phase == "replanned"
    with pytest.raises(RuntimeError, match="already issued"):
        session.start(fresh["sample_id"], plan, (permit,))
