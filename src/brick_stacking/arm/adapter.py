"""A1-02 contract and deterministic, offline-only trajectory execution."""

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from threading import Lock
import time
from typing import Literal, Protocol
from uuid import uuid4

from brick_stacking.contracts import ArmState, ExecutionResult, JointName, Permit, Trajectory
from brick_stacking.hardware.mock_devices import MockArm as JointMock

JOINT_NAMES: tuple[JointName, ...] = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")


class ArmAdapter(Protocol):
    def read_state(self) -> ArmState: ...
    def validate_trajectory(self, trajectory: Trajectory) -> Trajectory: ...
    def execute_trajectory(
        self, trajectory: Trajectory, permit: Permit, *,
        valid_until_host_monotonic_s: float | None = None,
    ) -> str: ...
    def cancel(self, command_id: str) -> bool: ...
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
    ):
        self._joints = JointMock(_positions(initial_joints_rad))
        self._clock = clock
        self._last_stamp = -math.inf
        self._device_id = device_id
        self._context = (device_id, config_hash, calibration_hash, scene_version)
        self._epoch = uuid4().hex
        self._lock = Lock()
        self._run: _Run | None = None

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

    def step(self, command_id: str) -> ExecutionResult:
        """Advance the mock by applying due points in order at the current clock."""
        with self._lock:
            run = self._command(command_id)
            if run.result["status"] != "RUNNING":
                return deepcopy(run.result)
            now = self._now()
            if now >= run.expires:
                run.result.update(status="FAILED", ended_host_monotonic_s=now,
                                  reason="permit or trajectory expired during mock execution")
                return deepcopy(run.result)

            points = run.trajectory["points"]
            previous_point = run.next_point
            while run.next_point < len(points):
                point = points[run.next_point]
                if now < run.started + point["time_from_start_s"]:
                    break
                self._joints.simulate_joint_target(point["q_rad"])
                run.next_point += 1
            if run.next_point != previous_point:
                run.result["feedback"] = self._state(now)
            if run.next_point == len(points):
                run.result.update(status="SUCCEEDED", ended_host_monotonic_s=now)
            return deepcopy(run.result)

    def cancel(self, command_id: str) -> bool:
        with self._lock:
            run = self._command(command_id)
            if run.result["status"] != "RUNNING":
                return False
            now = self._now()
            self._joints.stop()
            run.result.update(status="CANCELLED", ended_host_monotonic_s=now,
                              reason="mock execution cancelled")
            return True

    def get_execution_result(self, command_id: str) -> ExecutionResult:
        with self._lock:
            return deepcopy(self._command(command_id).result)


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
