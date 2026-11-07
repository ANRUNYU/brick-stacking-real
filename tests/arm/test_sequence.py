from types import SimpleNamespace

import pytest

from brick_stacking.arm.adapter import JOINT_NAMES, MockArm, trajectory_hash
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
        return MultiSegmentRun(arm, plan, permits, joint_limits_rad=((-0.5, 0.5),) * 7,
                               max_state_age_s=0.25, clock=lambda: clock.now)

    return SimpleNamespace(arm=arm, clock=clock, plan=plan, permits=permits, start=start)


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
