"""Offline-only trajectory execution with feedback-confirmed completion."""

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from threading import Lock
import time
from typing import Literal, Protocol, cast
from uuid import uuid4

from brick_stacking.contracts import ArmState, ExecutionResult, ExecutionStatus, JointName, Permit, StopResult, Trajectory
from brick_stacking.hardware.mock_devices import MockArm as JointMock

JOINT_NAMES: tuple[JointName, ...] = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")
FaultKind = Literal["TIMEOUT", "EXPIRED", "DISCONNECTED"]


@dataclass(frozen=True)
class ArmFault:
    kind: FaultKind
    stop: StopResult


class ArmAdapter(Protocol):
    def read_state(self) -> ArmState: ...
    def validate_trajectory(self, trajectory: Trajectory) -> Trajectory: ...
    def execute_trajectory(
        self, trajectory: Trajectory, permit: Permit, *,
        valid_until_host_monotonic_s: float | None = None,
    ) -> str: ...
    def cancel(self, command_id: str) -> bool: ...
    def get_execution_status(self, command_id: str) -> ExecutionStatus: ...
    def get_execution_result(self, command_id: str) -> ExecutionResult: ...


def _number(value: float, field: str) -> float:
    try:
        if type(value) in (float, int) and math.isfinite(value):
            return float(value)
    except OverflowError:
        pass
    raise ValueError(f"{field} requires finite numbers")


def _positions(values: Sequence[float]) -> tuple[float, ...]:
    if len(values) != len(JOINT_NAMES):
        raise ValueError("q_rad requires seven joint positions")
    return tuple(_number(value, "q_rad") for value in values)


def validate_trajectory(trajectory: Trajectory) -> Trajectory:
    """Validate and copy the payload before it can be scheduled or hashed."""
    if tuple(trajectory["joint_names"]) != JOINT_NAMES:
        raise ValueError("trajectory joint order must be J1 through J7")
    if not trajectory["points"]:
        raise ValueError("trajectory requires at least one point")

    points = []
    previous = -1.0
    for point in trajectory["points"]:
        offset = _number(point["time_from_start_s"], "time_from_start_s")
        if offset < 0 or offset <= previous:
            raise ValueError("trajectory times must be nonnegative and strictly increasing")
        points.append({"time_from_start_s": offset, "q_rad": _positions(point["q_rad"])})
        previous = offset
    return {"joint_names": JOINT_NAMES, "points": tuple(points)}


def _digest(trajectory: Trajectory) -> str:
    payload = json.dumps(trajectory, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def trajectory_hash(trajectory: Trajectory) -> str:
    return _digest(validate_trajectory(trajectory))


@dataclass
class _Run:
    trajectory: Trajectory
    started: float
    expires: float
    result: ExecutionResult
    next_point: int = 0
    final_dispatched_at: float | None = None
    fault: ArmFault | None = None


class MockArm:
    """Apply due points only on step(), with no timers or hardware backend."""

    backend = "mock"
    hardware_enabled = False
    validate_trajectory = staticmethod(validate_trajectory)

    def __init__(
        self, initial_joints_rad: Sequence[float], *,
        clock: Callable[[], float] = time.monotonic,
        device_id: str = "mock-arm", config_hash: str = "mock-config",
        calibration_hash: str = "mock-calibration", scene_version: str = "mock-scene",
        feedback_reader: Callable[[], ArmState | None] | None = None,
        max_feedback_age_s: float = 0.1,
        goal_tolerance_rad: float = 1e-6,
        feedback_timeout_s: float | None = None,
    ):
        self._joints = JointMock(_positions(initial_joints_rad))
        self._clock = clock
        self._last_stamp = -math.inf
        self._device_id = device_id
        self._context = (device_id, config_hash, calibration_hash, scene_version)
        self._epoch = uuid4().hex
        self._lock = Lock()
        self._run: _Run | None = None
        self._feedback_reader = feedback_reader
        self._max_feedback_age_s = _number(max_feedback_age_s, "maximum feedback age")
        self._goal_tolerance_rad = _number(goal_tolerance_rad, "goal tolerance")
        if self._max_feedback_age_s <= 0 or self._goal_tolerance_rad < 0:
            raise ValueError("feedback age must be positive and goal tolerance nonnegative")
        self._feedback_timeout_s = None
        if feedback_timeout_s is not None:
            self._feedback_timeout_s = _number(feedback_timeout_s, "feedback timeout")
            if self._feedback_timeout_s <= 0:
                raise ValueError("feedback timeout must be positive")

    def _now(self) -> float:
        now = _number(self._clock(), "host monotonic clock")
        if now < self._last_stamp:
            raise ValueError("host monotonic clock went backwards")
        self._last_stamp = now
        return now

    def _state(self, now: float) -> ArmState:
        return {
            "sample_id": uuid4().hex, "source": "mock", "device_id": self._device_id,
            "frame_id": "active_arm_base", "device_stamp": None, "host_receive_stamp": now,
            "clock_domain": "host_monotonic", "epoch": self._epoch, "validity": "VALID",
            "reason": None, "joint_names": JOINT_NAMES,
            "joint_bindings": {
                joint: {"sdk_index": index, "device_joint_id": f"mock-{joint}"}
                for index, joint in enumerate(JOINT_NAMES)
            },
            "q_rad": self._joints.get_joint_state(), "dq_rad_s": None,
            "enabled": None, "fault": None,
        }

    def read_state(self) -> ArmState:
        with self._lock:
            return self._state(self._now())

    def execute_trajectory(
        self, trajectory: Trajectory, permit: Permit, *,
        valid_until_host_monotonic_s: float | None = None,
    ) -> str:
        trajectory = self.validate_trajectory(trajectory)
        context = (permit["device_id"], permit["config_hash"],
                   permit["calibration_hash"], permit["scene_version"])
        if context != self._context or permit["trajectory_hash"] != _digest(trajectory):
            raise ValueError("permit does not match the mock context and trajectory")

        expires = _number(permit["valid_until_host_monotonic_s"], "permit deadline")
        if valid_until_host_monotonic_s is not None:
            expires = min(expires, _number(valid_until_host_monotonic_s, "trajectory deadline"))
        with self._lock:
            if self._run and self._run.fault is not None:
                raise RuntimeError("mock arm fault latched; start a fresh recovery session")
            if self._run and self._run.result["status"] == "RUNNING":
                raise RuntimeError("a mock trajectory is already running")
            now = self._now()
            if now >= expires:
                raise ValueError("permit or trajectory expired")
            if now + trajectory["points"][-1]["time_from_start_s"] >= expires:
                raise ValueError("trajectory cannot finish before expiry")
            command_id = uuid4().hex
            self._run = _Run(trajectory, now, expires, {
                "command_id": command_id, "status": "RUNNING", "feedback": None,
                "started_host_monotonic_s": now, "ended_host_monotonic_s": None, "reason": None,
            })
            return command_id

    def _command(self, command_id: str) -> _Run:
        if self._run is None or self._run.result["command_id"] != command_id:
            raise KeyError(command_id)
        return self._run

    def _feedback_problem(self, run: _Run, sample: ArmState | None, now: float) -> str | None:
        if sample is None:
            return "awaiting mock feedback"
        if (sample["source"] != "mock" or sample["device_id"] != self._device_id
                or sample["epoch"] != self._epoch or sample["clock_domain"] != "host_monotonic"
                or sample["frame_id"] != "active_arm_base" or tuple(sample["joint_names"]) != JOINT_NAMES
                or sample["validity"] != "VALID" or sample["fault"] is not None or not sample["sample_id"]):
            return "invalid mock feedback identity, joint order or validity"
        try:
            stamp = _number(sample["host_receive_stamp"], "feedback timestamp")
            _positions(sample["q_rad"])
        except (TypeError, ValueError):
            return "invalid mock feedback timestamp or position"
        lower_bound = run.started if run.final_dispatched_at is None else run.final_dispatched_at
        if stamp < lower_bound or not 0 <= now - stamp <= self._max_feedback_age_s:
            return "stale or future mock feedback"
        if self._feedback_reader is not None and stamp == run.final_dispatched_at:
            return "mock feedback must postdate final dispatch"
        previous = cast(ArmState | None, run.result["feedback"])
        if previous is not None and (
            stamp <= previous["host_receive_stamp"] or sample["sample_id"] == previous["sample_id"]
        ):
            return "repeated or out-of-order mock feedback"
        return None

    def _fail(
        self, run: _Run, now: float, kind: FaultKind, reason: str, *, stop_already_failed: bool = False,
    ) -> ExecutionResult:
        run.result.update(status="FAILED", ended_host_monotonic_s=now, reason=reason)
        request_sent = kind != "DISCONNECTED" and not stop_already_failed
        stop_reason = "mock stop request could not be sent" if stop_already_failed else "mock transport disconnected"
        if request_sent:
            try:
                self._joints.stop()
                stop_reason = "mock stop request only"
            except OSError:
                request_sent = False
                stop_reason = "mock stop request could not be sent"
        run.fault = ArmFault(kind, {
            "request_sent": request_sent, "feedback_confirmed": False, "hold_capable": None,
            "reason": stop_reason,
        })
        return deepcopy(run.result)

    def _transport_fault(self, run: _Run, exc: OSError, operation: str) -> ExecutionResult:
        now = self._now()
        if isinstance(exc, TimeoutError):
            return self._fail(run, now, "TIMEOUT", f"mock {operation} timed out")
        return self._fail(run, now, "DISCONNECTED", f"mock {operation} disconnected")

    def _deadline_fault(self, run: _Run, now: float) -> ExecutionResult | None:
        if now >= run.expires:
            return self._fail(run, now, "EXPIRED", "permit or trajectory expired during mock execution")
        if (self._feedback_timeout_s is not None and run.final_dispatched_at is not None
                and now >= run.final_dispatched_at + self._feedback_timeout_s):
            return self._fail(run, now, "TIMEOUT", "mock completion feedback timed out")
        return None

    def step(self, command_id: str) -> ExecutionResult:
        """Advance the mock by applying due points in order at the current clock."""
        with self._lock:
            run = self._command(command_id)
            if run.result["status"] != "RUNNING":
                return deepcopy(run.result)
            now = self._now()
            if failure := self._deadline_fault(run, now):
                return failure

            points = run.trajectory["points"]
            previous_point = run.next_point
            while run.next_point < len(points):
                point = points[run.next_point]
                if now < run.started + point["time_from_start_s"]:
                    break
                try:
                    self._joints.simulate_joint_target(point["q_rad"])
                except OSError as exc:
                    return self._transport_fault(run, exc, "target transport")
                run.next_point += 1
                now = self._now()
                if run.next_point == len(points):
                    run.final_dispatched_at = now
                if failure := self._deadline_fault(run, now):
                    return failure
            if run.next_point == previous_point and run.final_dispatched_at is None:
                return deepcopy(run.result)

            if self._feedback_reader is None:
                sample = self._state(now)
            else:
                try:
                    sample = self._feedback_reader()
                except OSError as exc:
                    return self._transport_fault(run, exc, "feedback transport")
                now = self._now()
            if failure := self._deadline_fault(run, now):
                return failure

            problem = self._feedback_problem(run, sample, now)
            if problem is not None or sample is None:
                run.result["reason"] = problem
                return deepcopy(run.result)
            run.result.update(feedback=deepcopy(sample), reason=None)
            if run.final_dispatched_at is not None:
                target = points[-1]["q_rad"]
                if all(abs(actual - goal) <= self._goal_tolerance_rad
                       for actual, goal in zip(sample["q_rad"], target, strict=True)):
                    run.result.update(status="SUCCEEDED", ended_host_monotonic_s=now)
                else:
                    run.result["reason"] = "mock feedback outside goal tolerance"
            return deepcopy(run.result)

    def cancel(self, command_id: str) -> bool:
        with self._lock:
            run = self._command(command_id)
            if run.result["status"] != "RUNNING":
                return False
            now = self._now()
            try:
                self._joints.stop()
            except OSError as exc:
                kind = "TIMEOUT" if isinstance(exc, TimeoutError) else "DISCONNECTED"
                self._fail(run, self._now(), kind, "mock cancellation stop failed", stop_already_failed=True)
                return False
            run.result.update(status="CANCELLED", ended_host_monotonic_s=now,
                              reason="mock execution cancelled")
            return True

    def get_execution_result(self, command_id: str) -> ExecutionResult:
        with self._lock:
            return deepcopy(self._command(command_id).result)

    def get_execution_status(self, command_id: str) -> ExecutionStatus:
        with self._lock:
            return self._command(command_id).result["status"]

    def get_execution_fault(self, command_id: str) -> ArmFault | None:
        with self._lock:
            return deepcopy(self._command(command_id).fault)


def replay_execution(
    trajectory: Trajectory, permit: Permit, initial_joints_rad: Sequence[float],
    events: Sequence[tuple[float, Literal["step", "cancel"]]], *,
    valid_until_host_monotonic_s: float | None = None,
) -> list[ExecutionResult]:
    """Replay an ordered script on a new mock with a clock starting at zero."""
    now = 0.0
    arm = MockArm(initial_joints_rad, clock=lambda: now)
    command_id = arm.execute_trajectory(
        trajectory, permit, valid_until_host_monotonic_s=valid_until_host_monotonic_s,
    )
    trace = [arm.get_execution_result(command_id)]
    for stamp, action in events:
        stamp = _number(stamp, "replay timestamp")
        if stamp < now:
            raise ValueError("replay timestamps must be nondecreasing")
        now = stamp
        if action == "step":
            trace.append(arm.step(command_id))
        elif action == "cancel":
            arm.cancel(command_id)
            trace.append(arm.get_execution_result(command_id))
        else:
            raise ValueError(f"unknown replay action: {action!r}")
    return trace
