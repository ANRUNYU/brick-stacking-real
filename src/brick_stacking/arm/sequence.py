"""Sequential execution and timing for a multi-segment mock arm plan."""

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
import math
from threading import Lock
import time
from typing import cast

from brick_stacking.arm.adapter import ArmFault, FaultKind, JOINT_NAMES, MockArm, _number, _positions, trajectory_hash
from brick_stacking.contracts import ArmState, ExecutionResult, ExecutionStatus, Permit, PlanResult


@dataclass(frozen=True)
class SegmentProgress:
    phase: str
    command_id: str
    status: ExecutionStatus
    elapsed_s: float
    reason: str | None


@dataclass(frozen=True)
class SequenceProgress:
    status: ExecutionStatus
    completed_segments: int
    total_segments: int
    elapsed_s: float
    segments: tuple[SegmentProgress, ...]
    reason: str | None
    fault: ArmFault | None = None


class MultiSegmentRun:
    """Own one mock arm for one plan. The caller drives it with step()."""

    def __init__(
        self, arm: MockArm, plan: PlanResult, permits: Sequence[Permit], *,
        joint_limits_rad: Sequence[tuple[float, float]], max_state_age_s: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not isinstance(arm, MockArm):
            raise ValueError("multi-segment execution requires a mock arm")
        if not plan["feasible"] or not plan["segments"]:
            raise ValueError("a feasible nonempty plan is required")
        if len(plan["segments"]) != len(permits):
            raise ValueError("one permit per segment is required")
        self._deadline = _number(plan["valid_until_host_monotonic_s"], "plan deadline")
        self._max_age = _number(max_state_age_s, "maximum start-state age")
        if self._max_age <= 0 or len(joint_limits_rad) != len(JOINT_NAMES):
            raise ValueError("positive maximum state age and seven joint limits are required")
        self._limits = tuple(
            (_number(low, "lower joint limit"), _number(high, "upper joint limit"))
            for low, high in joint_limits_rad
        )
        if any(low >= high for low, high in self._limits):
            raise ValueError("lower joint limits must be below upper joint limits")

        self._segments = []
        device_id = permits[0]["device_id"]
        for segment, permit in zip(plan["segments"], permits, strict=True):
            phase = segment["phase"]
            trajectory = arm.validate_trajectory(segment["trajectory"])
            if (permit["device_id"] != device_id or permit["config_hash"] != plan["config_hash"]
                    or permit["calibration_hash"] != plan["calibration_hash"]
                    or permit["scene_version"] != plan["scene_version"]
                    or permit["trajectory_hash"] != trajectory_hash(trajectory)):
                raise ValueError(f"{phase}: permit does not match plan and segment")
            _number(permit["valid_until_host_monotonic_s"], "permit deadline")
            for point in trajectory["points"]:
                self._check_limits(point["q_rad"])
            self._segments.append((phase, trajectory, permit.copy()))

        self._arm = arm
        self._clock = clock
        self._last_time = -math.inf
        self._lock = Lock()
        self._epoch: str | None = None
        self._start_sample_id: str | None = None
        self._status: ExecutionStatus = "PENDING"
        self._reason: str | None = None
        self._fault: ArmFault | None = None
        self._started: float | None = None
        self._ended: float | None = None
        self._completed = 0
        self._results: list[ExecutionResult] = []

    def _now(self) -> float:
        now = _number(self._clock(), "sequence clock")
        if now < self._last_time:
            raise ValueError("sequence clock went backwards")
        self._last_time = now
        return now

    def _check_limits(self, positions: Sequence[float]) -> None:
        for joint, value, (low, high) in zip(JOINT_NAMES, _positions(positions), self._limits, strict=True):
            if not low <= value <= high:
                raise ValueError(f"{joint} outside joint limits")

    def _check_start(self, state: ArmState, permit: Permit, now: float) -> None:
        if (state["source"] != "mock" or state["device_id"] != permit["device_id"]
                or state["clock_domain"] != "host_monotonic" or state["validity"] != "VALID"
                or state["fault"] is not None or tuple(state["joint_names"]) != JOINT_NAMES
                or state["frame_id"] != "active_arm_base" or not state["epoch"]
                or (self._epoch is not None and state["epoch"] != self._epoch)):
            raise ValueError("invalid segment start-state identity, epoch or validity")
        stamp = _number(state["host_receive_stamp"], "start-state timestamp")
        previous_end = self._results[-1]["ended_host_monotonic_s"] if self._results else None
        if (not 0 <= now - stamp <= self._max_age
                or (previous_end is not None and stamp < previous_end)
                or not state["sample_id"] or state["sample_id"] == self._start_sample_id):
            raise ValueError("stale or future segment start state")
        self._check_limits(state["q_rad"])
        self._epoch = state["epoch"]
        self._start_sample_id = state["sample_id"]

    def _finish(self, status: ExecutionStatus, now: float, reason: str | None = None) -> None:
        self._status, self._ended, self._reason = status, now, reason

    def _fail_before_dispatch(self, phase: str, reason: str, kind: FaultKind) -> SequenceProgress:
        now = self._now()
        self._fault = ArmFault(kind, {
            "request_sent": False, "feedback_confirmed": False, "hold_capable": None,
            "reason": "no active segment to stop",
        })
        self._finish("FAILED", now, f"{phase}: {reason}")
        return self._snapshot(now)

    def _snapshot(self, now: float) -> SequenceProgress:
        end = now if self._ended is None else self._ended
        elapsed = 0.0 if self._started is None else end - self._started
        segments = []
        for index, result in enumerate(self._results):
            started, ended = result["started_host_monotonic_s"], result["ended_host_monotonic_s"]
            duration = 0.0 if started is None else (end if ended is None else ended) - started
            segments.append(SegmentProgress(self._segments[index][0], result["command_id"],
                                            result["status"], duration, result["reason"]))
        return SequenceProgress(self._status, self._completed, len(self._segments), elapsed,
                                tuple(segments), self._reason, deepcopy(self._fault))

    def progress(self) -> SequenceProgress:
        with self._lock:
            return self._snapshot(self._now() if self._ended is None else self._ended)

    def step(self) -> SequenceProgress:
        with self._lock:
            if self._ended is not None:
                return self._snapshot(self._ended)
            now = self._now()
            if self._started is None:
                self._started, self._status = now, "RUNNING"
            phase, trajectory, permit = self._segments[self._completed]
            if len(self._results) == self._completed:
                if now >= min(self._deadline, permit["valid_until_host_monotonic_s"]):
                    return self._fail_before_dispatch(phase, "plan or segment permit expired", "EXPIRED")
                try:
                    state = self._arm.read_state()
                    now = self._now()
                    if now >= min(self._deadline, permit["valid_until_host_monotonic_s"]):
                        return self._fail_before_dispatch(phase, "plan or segment permit expired", "EXPIRED")
                    self._check_start(state, permit, now)
                    command = self._arm.execute_trajectory(
                        trajectory, permit, valid_until_host_monotonic_s=self._deadline,
                    )
                except TimeoutError:
                    return self._fail_before_dispatch(phase, "mock start-state read timed out", "TIMEOUT")
                except OSError:
                    return self._fail_before_dispatch(phase, "mock start-state transport disconnected", "DISCONNECTED")
                except (ValueError, RuntimeError) as exc:
                    now = self._now()
                    self._finish("FAILED", now, f"{phase}: {exc}")
                    return self._snapshot(now)
                self._results.append(self._arm.get_execution_result(command))

            command = self._results[-1]["command_id"]
            result = self._arm.step(command)
            self._results[-1] = result
            now = self._now()
            feedback = cast(ArmState | None, result["feedback"])
            if feedback is not None:
                try:
                    self._check_limits(feedback["q_rad"])
                except ValueError as exc:
                    self._arm.cancel(command)
                    self._results[-1] = self._arm.get_execution_result(command)
                    self._fault = self._arm.get_execution_fault(command)
                    now = self._now()
                    self._finish("FAILED", now, f"{phase}: feedback {exc}")
                    return self._snapshot(now)
            if result["status"] == "SUCCEEDED":
                self._completed += 1
                if self._completed == len(self._segments):
                    self._finish("SUCCEEDED", now)
            elif result["status"] != "RUNNING":
                self._fault = self._arm.get_execution_fault(command)
                self._finish("FAILED", now, f"{phase}: {result['reason'] or result['status']}")
            return self._snapshot(now)

    def cancel(self) -> bool:
        with self._lock:
            if self._ended is not None:
                return False
            if len(self._results) > self._completed:
                command = self._results[-1]["command_id"]
                self._arm.cancel(command)
                self._results[-1] = self._arm.get_execution_result(command)
                self._fault = self._arm.get_execution_fault(command)
                if self._fault is not None:
                    self._finish("FAILED", self._now(), self._results[-1]["reason"])
                    return False
            self._finish("CANCELLED", self._now(), "mock sequence cancelled")
            return True
