from __future__ import annotations

from typing import Any

import pytest

from brick_stacking.motion.celebration import (
    MAX_LOOPS,
    build_celebration_plan,
    run_celebration,
    validate_loop_count,
)


LEFT_START = [-0.0393, -0.0062, 0.0018, -0.0354, 1.5961, -0.03, 0.24]
RIGHT_START = [0.0078, -0.0047, 0.3459, 0.044, -0.1243, -0.27, -0.35]


class FakeArm:
    def __init__(self, start: list[float], *, fail_stage: int | None = None) -> None:
        self.q = list(start)
        self.fail_stage = fail_stage
        self.moves: list[list[float]] = []
        self.velocities: list[list[float]] = []
        self.accelerations: list[list[float]] = []
        self.enabled = False
        self.held = False

    def get_angles(self) -> list[float]:
        return list(self.q)

    def get_velocities(self) -> list[float]:
        return [0.0] * 7

    def get_temperatures(self) -> list[float]:
        return [30.0] * 7

    def set_velocities(self, values: list[float]) -> None:
        self.velocities.append(list(values))

    def set_accelerations(self, values: list[float]) -> None:
        self.accelerations.append(list(values))

    def enable(self) -> None:
        self.enabled = True

    def move_j(self, target: list[float], *, blocking: bool = True) -> None:
        del blocking
        if self.fail_stage is not None and len(self.moves) == self.fail_stage:
            raise RuntimeError("synthetic move failure")
        self.moves.append(list(target))
        self.q = list(target)

    def emergency_stop(self) -> None:
        self.held = True


@pytest.mark.parametrize("loops", [1, 2, MAX_LOOPS])
def test_loop_count_accepts_bounded_integer(loops: int) -> None:
    assert validate_loop_count(loops) == loops


@pytest.mark.parametrize("loops", [0, -1, MAX_LOOPS + 1])
def test_loop_count_rejects_out_of_range(loops: int) -> None:
    with pytest.raises(ValueError):
        validate_loop_count(loops)


@pytest.mark.parametrize("loops", [True, 1.5, "2"])
def test_loop_count_rejects_non_integer(loops: Any) -> None:
    with pytest.raises(TypeError):
        validate_loop_count(loops)


def test_cycle_is_closed_and_asymmetric() -> None:
    plan = build_celebration_plan(LEFT_START, RIGHT_START, loops=3)

    assert plan.cycle[-1].name == "loop_anchor"
    assert plan.cycle[-1].left_target == plan.left_anchor
    assert plan.cycle[-1].right_target == plan.right_anchor
    assert plan.left_anchor[1] == pytest.approx(2.45)
    assert plan.right_anchor[1:4] == pytest.approx((-1.55, 0.40, -1.60))
    assert plan.left_anchor[1] != pytest.approx(abs(plan.right_anchor[1]))
    assert any(segment.left_target is None for segment in plan.cycle)
    assert any(segment.right_target is None for segment in plan.cycle)
    assert plan.cycle[-2].name == "finale_accent"


def test_requested_loop_count_scales_only_the_closed_body() -> None:
    left = FakeArm(LEFT_START)
    right = FakeArm(RIGHT_START)
    result = run_celebration(left, right, loops=3, sleep_fn=lambda _: None)

    assert result["verdict"] == "PASS"
    assert result["loops"] == 3
    assert result["final_max_error_rad"] == {"left": 0.0, "right": 0.0}
    assert left.q == pytest.approx(LEFT_START)
    assert right.q == pytest.approx(RIGHT_START)
    assert sum(event["event"] == "loop_start" for event in result["events"]) == 3
    assert sum(event["event"] == "loop_done" for event in result["events"]) == 3
    # Two entrance + six active left moves per cycle + two exit transitions.
    assert len(left.moves) == 2 + 6 * 3 + 2
    assert len(right.moves) == 2 + 6 * 3 + 2


def test_preflight_rejects_non_neutral_start() -> None:
    left_start = list(LEFT_START)
    left_start[1] = 0.30
    with pytest.raises(RuntimeError, match="must start near"):
        run_celebration(
            FakeArm(left_start),
            FakeArm(RIGHT_START),
            loops=1,
            sleep_fn=lambda _: None,
        )


def test_motion_failure_holds_both_arms() -> None:
    left = FakeArm(LEFT_START, fail_stage=1)
    right = FakeArm(RIGHT_START)

    with pytest.raises(RuntimeError, match="synthetic move failure"):
        run_celebration(left, right, loops=1, sleep_fn=lambda _: None)

    assert left.held is True
    assert right.held is True
