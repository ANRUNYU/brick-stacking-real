"""Loop-safe asymmetric celebration choreography for the dual P7 arms.

The entrance and exit run once.  The repeatable body starts and ends at the
same asymmetric anchor pose, so changing ``loops`` never introduces a joint
position discontinuity at a loop boundary.

This module does not import the vendor SDK.  The caller owns arm construction,
per-run operator authorization, CAN interfaces, and closing the arms.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

MAX_LOOPS = 10
RETURN_TOLERANCE_RAD = 0.08
MAX_START_VELOCITY_RAD_S = 0.35
MAX_TEMPERATURE_C = 70.0

_LEFT_LIMITS = (
    (-2.91, 2.91),
    (-0.07, 3.20),
    (-2.69, 2.69),
    (-2.05, 2.05),
    (-2.69, 2.69),
    (-1.59, 1.59),
    (-1.59, 1.59),
)
_RIGHT_LIMITS = (
    (-2.91, 2.91),
    (-3.20, 0.07),
    (-2.69, 2.69),
    (-2.05, 2.05),
    (-2.69, 2.69),
    (-1.59, 1.59),
    (-1.59, 1.59),
)

EventCallback = Callable[[dict[str, Any]], None]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class MotionSegment:
    """One blocking keyframe transition for either or both arms."""

    name: str
    left_target: tuple[float, ...] | None = None
    right_target: tuple[float, ...] | None = None
    left_speed: float | None = None
    right_speed: float | None = None
    hold_s: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "left_target": list(self.left_target) if self.left_target is not None else None,
            "right_target": list(self.right_target) if self.right_target is not None else None,
            "left_speed": self.left_speed,
            "right_speed": self.right_speed,
            "hold_s": self.hold_s,
        }


@dataclass(frozen=True)
class CelebrationPlan:
    """Entrance-once, closed repeat body, and exit-once choreography."""

    loops: int
    left_start: tuple[float, ...]
    right_start: tuple[float, ...]
    left_anchor: tuple[float, ...]
    right_anchor: tuple[float, ...]
    entrance: tuple[MotionSegment, ...]
    cycle: tuple[MotionSegment, ...]
    exit: tuple[MotionSegment, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "celebration-asymmetric-loop-plan-0.1",
            "loops": self.loops,
            "loop_boundary": {
                "left_anchor": list(self.left_anchor),
                "right_anchor": list(self.right_anchor),
                "position_continuous": True,
            },
            "entrance": [segment.as_dict() for segment in self.entrance],
            "cycle_template": [segment.as_dict() for segment in self.cycle],
            "exit": [segment.as_dict() for segment in self.exit],
        }


def validate_loop_count(loops: int) -> int:
    """Require an explicit, bounded positive integer loop count."""
    if isinstance(loops, bool) or not isinstance(loops, int):
        raise TypeError("loops must be an integer")
    if not 1 <= loops <= MAX_LOOPS:
        raise ValueError(f"loops must be in [1, {MAX_LOOPS}]")
    return loops


def _joint_vector(values: Sequence[float], name: str) -> tuple[float, ...]:
    if len(values) != 7:
        raise ValueError(f"{name} must contain seven joint angles")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} contains a non-finite joint angle")
    return result


def _pose(start: tuple[float, ...], **joints: float) -> tuple[float, ...]:
    values = list(start)
    for name, value in joints.items():
        if not name.startswith("j"):
            raise ValueError(f"invalid joint override {name!r}")
        index = int(name[1:]) - 1
        if not 0 <= index < 7:
            raise ValueError(f"invalid joint override {name!r}")
        values[index] = float(value)
    return tuple(values)


def _validate_target(
    side: str,
    target: tuple[float, ...],
    *,
    name: str,
    margin_rad: float = 0.10,
) -> None:
    limits = _LEFT_LIMITS if side == "left" else _RIGHT_LIMITS
    for index, (value, (low, high)) in enumerate(zip(target, limits), start=1):
        if not low + margin_rad <= value <= high - margin_rad:
            raise ValueError(
                f"{name}: {side} J{index}={value:.4f} outside safe range "
                f"[{low + margin_rad:.4f}, {high - margin_rad:.4f}]"
            )


def build_celebration_plan(
    left_start: Sequence[float],
    right_start: Sequence[float],
    *,
    loops: int,
) -> CelebrationPlan:
    """Build the tested asymmetric pose sequence around measured start angles."""
    loops = validate_loop_count(loops)
    left_start_q = _joint_vector(left_start, "left_start")
    right_start_q = _joint_vector(right_start, "right_start")

    # Entrance staging keeps the large shoulder travel split into two arcs.
    left_mid = _pose(left_start_q, j2=1.35)
    right_safe = _pose(right_start_q, j2=-0.85, j3=0.40, j4=-0.65)

    # Asymmetric loop anchor: left arm is the high hero, right fist stays near
    # the chest.  Unspecified joints retain the measured start state.
    left_anchor = _pose(left_start_q, j2=2.45)
    right_anchor = _pose(right_start_q, j2=-1.55, j3=0.40, j4=-1.60)

    left_wave_front = _pose(left_anchor, j4=left_start_q[3] + 0.22)
    left_wave_back = _pose(left_anchor, j4=left_start_q[3] - 0.22)
    right_pump_up = _pose(right_anchor, j2=-1.70, j4=-1.82)
    right_pump_down = _pose(right_anchor, j2=-1.45, j4=-1.45)

    # A short two-arm accent adds flourish without restoring mirror symmetry:
    # the left shoulder rises and sweeps forward while the right fist pumps in.
    left_accent = _pose(left_anchor, j2=2.58, j4=left_start_q[3] + 0.12)

    entrance = (
        MotionSegment(
            "asymmetric_setup",
            left_mid,
            right_safe,
            left_speed=0.50,
            right_speed=0.50,
            hold_s=0.12,
        ),
        MotionSegment(
            "hero_pose",
            left_anchor,
            right_anchor,
            left_speed=0.50,
            right_speed=0.50,
            hold_s=0.30,
        ),
    )
    cycle = (
        MotionSegment("left_wave_front_1", left_target=left_wave_front, left_speed=0.42),
        MotionSegment("left_wave_back", left_target=left_wave_back, left_speed=0.42),
        MotionSegment("left_wave_front_2", left_target=left_wave_front, left_speed=0.42),
        MotionSegment(
            "left_wave_settle",
            left_target=left_anchor,
            left_speed=0.42,
            hold_s=0.10,
        ),
        MotionSegment("right_pump_up_1", right_target=right_pump_up, right_speed=0.62),
        MotionSegment("right_pump_down", right_target=right_pump_down, right_speed=0.62),
        MotionSegment("right_pump_up_2", right_target=right_pump_up, right_speed=0.62),
        MotionSegment(
            "right_pump_settle",
            right_target=right_anchor,
            right_speed=0.62,
            hold_s=0.10,
        ),
        MotionSegment(
            "finale_accent",
            left_target=left_accent,
            right_target=right_pump_up,
            left_speed=0.46,
            right_speed=0.62,
            hold_s=0.12,
        ),
        MotionSegment(
            "loop_anchor",
            left_target=left_anchor,
            right_target=right_anchor,
            left_speed=0.44,
            right_speed=0.56,
            hold_s=0.18,
        ),
    )
    exit_segments = (
        MotionSegment(
            "asymmetric_release",
            left_mid,
            right_safe,
            left_speed=0.50,
            right_speed=0.50,
            hold_s=0.10,
        ),
        MotionSegment(
            "return",
            left_start_q,
            right_start_q,
            left_speed=0.50,
            right_speed=0.50,
            hold_s=0.20,
        ),
    )

    for segment in (*entrance, *cycle, *exit_segments):
        # The measured neutral J2 pose is intentionally close to the asymmetric
        # hardware limit around zero.  It is preflighted with the tighter
        # measured-start margin and must remain a valid return target.
        margin = 0.05 if segment.name == "return" else 0.10
        if segment.left_target is not None:
            _validate_target(
                "left", segment.left_target, name=segment.name, margin_rad=margin
            )
        if segment.right_target is not None:
            _validate_target(
                "right", segment.right_target, name=segment.name, margin_rad=margin
            )

    last = cycle[-1]
    if last.left_target != left_anchor or last.right_target != right_anchor:
        raise AssertionError("celebration cycle must end exactly at its anchor")

    return CelebrationPlan(
        loops=loops,
        left_start=left_start_q,
        right_start=right_start_q,
        left_anchor=left_anchor,
        right_anchor=right_anchor,
        entrance=entrance,
        cycle=cycle,
        exit=exit_segments,
    )


def _preflight_arm(arm: Any, side: str) -> dict[str, Any]:
    angles = _joint_vector(arm.get_angles(), f"{side}_angles")
    velocities = _joint_vector(arm.get_velocities(), f"{side}_velocities")
    temperatures = _joint_vector(arm.get_temperatures(), f"{side}_temperatures")
    if any(abs(value) > MAX_START_VELOCITY_RAD_S for value in velocities):
        raise RuntimeError(f"{side} arm is already moving: {velocities!r}")
    if any(value > MAX_TEMPERATURE_C for value in temperatures):
        raise RuntimeError(f"{side} arm temperature too high: {temperatures!r}")
    if abs(angles[1]) > 0.20:
        raise RuntimeError(
            f"{side} shoulder J2 must start near the validated neutral pose; "
            f"got {angles[1]:.4f} rad"
        )
    _validate_target(side, angles, name="measured_start", margin_rad=0.05)
    return {
        "angles": angles,
        "velocities": velocities,
        "temperatures": temperatures,
    }


def _hold_all(arms: Mapping[str, Any]) -> None:
    for arm in arms.values():
        try:
            arm.emergency_stop()
        except Exception:  # noqa: BLE001 - best effort after motion failure
            pass


def _run_segment(
    arms: Mapping[str, Any],
    segment: MotionSegment,
    *,
    emit: EventCallback,
    sleep_fn: SleepFn,
    loop_index: int | None,
) -> None:
    targets = {
        "left": segment.left_target,
        "right": segment.right_target,
    }
    speeds = {
        "left": segment.left_speed,
        "right": segment.right_speed,
    }
    active = [side for side, target in targets.items() if target is not None]
    emit(
        {
            "event": "stage_start",
            "stage": segment.name,
            "loop_index": loop_index,
            "active_arms": active,
        }
    )
    for side in active:
        speed = speeds[side]
        if speed is None or speed <= 0:
            raise ValueError(f"{segment.name}: missing positive {side} speed")
        arms[side].set_velocities([float(speed)] * 7)

    def move(side: str) -> None:
        arms[side].move_j(list(targets[side]), blocking=True)

    if len(active) == 2:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(move, side) for side in active]
            for future in futures:
                future.result()
    elif len(active) == 1:
        move(active[0])
    else:
        raise ValueError(f"{segment.name}: segment has no active arm")

    if segment.hold_s > 0:
        sleep_fn(segment.hold_s)
    emit(
        {
            "event": "stage_done",
            "stage": segment.name,
            "loop_index": loop_index,
            "active_arms": active,
        }
    )


def run_celebration(
    left_arm: Any,
    right_arm: Any,
    *,
    loops: int,
    event_callback: EventCallback | None = None,
    sleep_fn: SleepFn = time.sleep,
) -> dict[str, Any]:
    """Preflight, execute a bounded number of cycles, and return to start."""
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        events.append(dict(event))
        if event_callback is not None:
            event_callback(dict(event))

    arms = {"left": left_arm, "right": right_arm}
    try:
        preflight = {
            "left": _preflight_arm(left_arm, "left"),
            "right": _preflight_arm(right_arm, "right"),
        }
        plan = build_celebration_plan(
            preflight["left"]["angles"],
            preflight["right"]["angles"],
            loops=loops,
        )
        emit(
            {
                "event": "preflight_ok",
                "loops": plan.loops,
                "temperatures_c": {
                    side: list(state["temperatures"])
                    for side, state in preflight.items()
                },
            }
        )
        for arm in arms.values():
            arm.set_velocities([0.50] * 7)
            arm.set_accelerations([1.0] * 7)
            arm.enable()
        sleep_fn(0.30)

        for segment in plan.entrance:
            _run_segment(arms, segment, emit=emit, sleep_fn=sleep_fn, loop_index=None)
        for loop_index in range(1, plan.loops + 1):
            emit({"event": "loop_start", "loop_index": loop_index, "loops": plan.loops})
            for segment in plan.cycle:
                _run_segment(
                    arms,
                    segment,
                    emit=emit,
                    sleep_fn=sleep_fn,
                    loop_index=loop_index,
                )
            emit({"event": "loop_done", "loop_index": loop_index, "loops": plan.loops})
        for segment in plan.exit:
            _run_segment(arms, segment, emit=emit, sleep_fn=sleep_fn, loop_index=None)

        sleep_fn(0.30)
        final = {
            "left": _joint_vector(left_arm.get_angles(), "left_final"),
            "right": _joint_vector(right_arm.get_angles(), "right_final"),
        }
        errors = {
            "left": max(abs(a - b) for a, b in zip(final["left"], plan.left_start)),
            "right": max(abs(a - b) for a, b in zip(final["right"], plan.right_start)),
        }
        emit(
            {
                "event": "complete",
                "loops": plan.loops,
                "final_max_error_rad": errors,
            }
        )
        if any(error > RETURN_TOLERANCE_RAD for error in errors.values()):
            raise RuntimeError(
                f"return error exceeds {RETURN_TOLERANCE_RAD:.3f} rad: {errors!r}"
            )
        return {
            "verdict": "PASS",
            "loops": plan.loops,
            "final_angles": {side: list(values) for side, values in final.items()},
            "final_max_error_rad": errors,
            "plan": plan.as_dict(),
            "events": events,
        }
    except BaseException as exc:
        emit({"event": "aborted", "error": f"{type(exc).__name__}: {exc}"})
        _hold_all(arms)
        raise
