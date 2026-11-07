"""Explicit offline restart from a new mock observation and plan."""

from collections.abc import Callable, Sequence
from threading import Lock
import time

from brick_stacking.arm.adapter import MockArm, _number
from brick_stacking.arm.sequence import MultiSegmentRun
from brick_stacking.contracts import ArmState, Permit, PlanResult


class MockRecoverySession:
    """Create an empty session. It never reads prior commands or run snapshots."""

    def __init__(
        self, observed_joints_rad: Sequence[float], *,
        joint_limits_rad: Sequence[tuple[float, float]], max_state_age_s: float,
        feedback_timeout_s: float, clock: Callable[[], float] = time.monotonic,
        device_id: str = "mock-arm", config_hash: str = "mock-config",
        calibration_hash: str = "mock-calibration", scene_version: str = "mock-scene",
    ):
        self._arm = MockArm(
            observed_joints_rad, clock=clock, device_id=device_id, config_hash=config_hash,
            calibration_hash=calibration_hash, scene_version=scene_version,
            feedback_timeout_s=feedback_timeout_s,
        )
        self._clock = clock
        self._limits = tuple((low, high) for low, high in joint_limits_rad)
        self._max_age = _number(max_state_age_s, "maximum recovery observation age")
        if self._max_age <= 0:
            raise ValueError("maximum recovery observation age must be positive")
        self._lock = Lock()
        self._observation: tuple[str, float] | None = None
        self._started = False

    def observe(self) -> ArmState:
        with self._lock:
            if self._started:
                raise RuntimeError("recovery session already issued a run")
            state = self._arm.read_state()
            self._observation = (state["sample_id"], state["host_receive_stamp"])
            return state

    def start(
        self, observation_id: str, plan: PlanResult, permits: Sequence[Permit],
    ) -> MultiSegmentRun:
        """Start a newly planned sequence linked to the latest session observation."""
        with self._lock:
            if self._started:
                raise RuntimeError("recovery session already issued a run")
            if self._observation is None or observation_id != self._observation[0]:
                raise ValueError("a new observation from this recovery session is required")
            now = self._arm.read_state()["host_receive_stamp"]
            if now - self._observation[1] > self._max_age:
                raise ValueError("recovery observation expired; observe and replan")
            run = MultiSegmentRun(
                self._arm, plan, permits, joint_limits_rad=self._limits,
                max_state_age_s=self._max_age, clock=self._clock,
            )
            self._started = True
            return run
