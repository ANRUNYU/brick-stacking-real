"""Left-arm single-joint control for the host monitor.

Pattern follows host scripts left_robot_motor_menu.py / p7_test_v1_joints.py
and linkerbot A7Motor / MotorV2 APIs. Does NOT construct the full P7 object
(P7.__init__ has Flash / mode side effects).

Hard gates:
- process must be started with --enable-motion
- web/API must open a control session with confirm=READY
- each joint move requires ENABLE then MOVE then RELEASE
- only one joint enabled at a time; small deltas; URDF limits with margin
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any


LEFT_IFACE = "can2"
LEFT_IDS = {1: 61, 2: 62, 3: 63, 4: 64, 5: 65, 6: 66, 7: 67}
URDF_LIMITS = [
    (-2.91, 2.91),
    (-3.20, 0.07),
    (-2.69, 2.69),
    (-2.05, 2.05),
    (-2.69, 2.69),
    (-1.59, 1.59),
    (-1.59, 1.59),
]
JOINT_MARGIN = math.radians(8)
V1_SPEED = 0.05
V1_ACCEL = 1.0
V1_TIMEOUT_S = 12.0
V2_RATE_HZ = 50
V2_DURATION_S = 4.0
V2_KP = 12.0
DEFAULT_STEP_DEG = {1: 5.0, 2: 5.0, 3: 5.0, 4: 5.0, 5: 5.0, 6: 3.0, 7: 3.0}
MAX_STEP_DEG = {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0, 5: 10.0, 6: 5.0, 7: 5.0}


@dataclass
class JointPlan:
    joint: int
    motor_id: int
    kind: str
    start_rad: float
    target_rad: float
    step_rad: float
    limits: tuple[float, float]
    enabled: bool = False
    moved: bool = False


@dataclass
class ControlSnapshot:
    motion_process_enabled: bool
    session_open: bool
    active_joint: int | None
    plan: dict[str, Any] | None
    last_error: str | None
    notice: str


class JointController:
    def __init__(self, motion_process_enabled: bool, mock: bool = False):
        self.motion_process_enabled = motion_process_enabled
        self.mock = mock
        self._lock = threading.RLock()
        self._session_open = False
        self._busy = False
        self._bus = None
        self._plan: JointPlan | None = None
        self._motor = None
        self._v2_polling = False
        self._last_error: str | None = None
        self._mock_angles = [0.0] * 7
        self._on_session_open = None
        self._on_session_close = None

    def set_hooks(self, on_open, on_close) -> None:
        self._on_session_open = on_open
        self._on_session_close = on_close

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> dict[str, Any]:
        plan = None
        if self._plan is not None:
            p = self._plan
            plan = {
                "joint": p.joint,
                "motor_id": p.motor_id,
                "kind": p.kind,
                "start_rad": p.start_rad,
                "target_rad": p.target_rad,
                "start_deg": math.degrees(p.start_rad),
                "target_deg": math.degrees(p.target_rad),
                "step_deg": math.degrees(p.step_rad),
                "enabled": p.enabled,
                "moved": p.moved,
                "limits_rad": list(p.limits),
            }
        return {
            "motion_process_enabled": self.motion_process_enabled,
            "session_open": self._session_open,
            "busy": self._busy,
            "active_joint": None if self._plan is None else self._plan.joint,
            "plan": plan,
            "last_error": self._last_error,
            "notice": (
                "process started without --enable-motion"
                if not self.motion_process_enabled
                else (
                    "control session open; one joint at a time"
                    if self._session_open
                    else "open control session with confirm=READY before moving"
                )
            ),
            "defaults": {
                "step_deg": DEFAULT_STEP_DEG,
                "max_step_deg": MAX_STEP_DEG,
                "iface": LEFT_IFACE,
            },
        }

    def _require_motion(self) -> None:
        if not self.motion_process_enabled:
            raise RuntimeError("motion APIs disabled; restart with --enable-motion")

    def open_session(self, confirm: str) -> dict[str, Any]:
        self._require_motion()
        if confirm != "READY":
            raise ValueError('confirm must be exactly "READY"')
        with self._lock:
            if self._session_open:
                return {"ok": True, "changed": False, **self._snapshot_unlocked()}
            if self._busy:
                raise RuntimeError("control busy")
        # Pause readonly CAN readers outside the lock (join can take >1s).
        if self._on_session_open:
            self._on_session_open()
        try:
            with self._lock:
                if self._session_open:
                    return {"ok": True, "changed": False, **self._snapshot_unlocked()}
                if not self.mock:
                    from linkerbot.comm import CANMessageDispatcher

                    self._bus = CANMessageDispatcher(LEFT_IFACE)
                    self._bus.__enter__()
                self._session_open = True
                self._last_error = None
                return {"ok": True, "changed": True, **self._snapshot_unlocked()}
        except Exception:
            with self._lock:
                self._session_open = False
                self._bus = None
            if self._on_session_close:
                self._on_session_close()
            raise

    def close_session(self) -> dict[str, Any]:
        with self._lock:
            if self._busy:
                raise RuntimeError("control busy; wait for MOVE/ENABLE to finish")
            self._force_release_locked()
            if self._bus is not None:
                try:
                    self._bus.__exit__(None, None, None)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = f"bus close: {exc}"
                self._bus = None
            was_open = self._session_open
            self._session_open = False
        if was_open and self._on_session_close:
            self._on_session_close()
        return {"ok": True, "changed": was_open, **self.snapshot()}

    def prepare(self, joint: int, step_deg: float | None = None, direction: int = 0) -> dict[str, Any]:
        self._require_motion()
        joint = int(joint)
        if joint not in LEFT_IDS:
            raise ValueError("joint must be 1..7")
        with self._lock:
            if self._busy:
                raise RuntimeError("control busy")
            if not self._session_open:
                raise RuntimeError("open control session first")
            if self._plan is not None and self._plan.enabled:
                raise RuntimeError("another joint is still enabled; RELEASE it first")
            step = DEFAULT_STEP_DEG[joint] if step_deg is None else float(step_deg)
            if not 0 < step <= MAX_STEP_DEG[joint]:
                raise ValueError(f"step_deg must be in (0, {MAX_STEP_DEG[joint]}]")
            start = self._read_angle_locked(joint)
            amount = math.radians(step)
            low, high = URDF_LIMITS[joint - 1]
            target = self._choose_target(start, amount, low, high, direction)
            self._plan = JointPlan(
                joint=joint,
                motor_id=LEFT_IDS[joint],
                kind="V1" if joint <= 5 else "V2",
                start_rad=start,
                target_rad=target,
                step_rad=target - start,
                limits=(low, high),
            )
            self._motor = None
            self._last_error = None
            return {"ok": True, **self._snapshot_unlocked()}

    def enable(self, joint: int, confirm: str) -> dict[str, Any]:
        self._require_motion()
        if confirm != "ENABLE":
            raise ValueError('confirm must be exactly "ENABLE"')
        with self._lock:
            if self._busy:
                raise RuntimeError("control busy")
            plan = self._require_plan(joint)
            if plan.enabled:
                return {"ok": True, "changed": False, **self._snapshot_unlocked()}
            self._busy = True
        try:
            with self._lock:
                plan = self._require_plan(joint)
                if self.mock:
                    plan.enabled = True
                elif plan.kind == "V1":
                    self._enable_v1_locked(plan)
                    plan.enabled = True
                else:
                    self._enable_v2_locked(plan)
                    plan.enabled = True
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._last_error = str(exc)
                self._busy = False
            raise
        with self._lock:
            self._busy = False
            return {"ok": True, "changed": True, **self._snapshot_unlocked()}

    def move(self, joint: int, confirm: str) -> dict[str, Any]:
        self._require_motion()
        if confirm != "MOVE":
            raise ValueError('confirm must be exactly "MOVE"')
        with self._lock:
            if self._busy:
                raise RuntimeError("control busy")
            plan = self._require_plan(joint)
            if not plan.enabled:
                raise RuntimeError("ENABLE the joint before MOVE")
            if plan.moved:
                return {"ok": True, "changed": False, **self._snapshot_unlocked()}
            self._busy = True
        actual = None
        try:
            with self._lock:
                plan = self._require_plan(joint)
                if self.mock:
                    self._mock_angles[joint - 1] = plan.target_rad
                    plan.moved = True
                    actual = plan.target_rad
                elif plan.kind == "V1":
                    actual = self._move_v1_locked(plan)
                    plan.moved = True
                else:
                    actual = self._move_v2_locked(plan)
                    plan.moved = True
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._last_error = str(exc)
                self._busy = False
            raise
        with self._lock:
            self._busy = False
            return {"ok": True, "changed": True, "actual_rad": actual, **self._snapshot_unlocked()}

    def release(self, joint: int, confirm: str) -> dict[str, Any]:
        self._require_motion()
        if confirm != "RELEASE":
            raise ValueError('confirm must be exactly "RELEASE"')
        with self._lock:
            if self._busy:
                raise RuntimeError("control busy")
            plan = self._require_plan(joint)
            self._disable_locked(plan)
            self._plan = None
            self._motor = None
            return {"ok": True, "changed": True, **self._snapshot_unlocked()}

    def read_joint(self, joint: int) -> float:
        with self._lock:
            return self._read_angle_locked(int(joint))

    def _require_plan(self, joint: int) -> JointPlan:
        if self._plan is None or self._plan.joint != int(joint):
            raise RuntimeError("prepare this joint first")
        return self._plan

    def _usable_window(self, low: float, high: float) -> tuple[float, float]:
        span = high - low
        if span <= 0:
            raise RuntimeError("invalid URDF limits")
        # Keep a soft margin, but never eat more than 15% of the joint span
        # (J2 upper limit is only ~4deg — a fixed 8deg margin would zero the window).
        margin = min(JOINT_MARGIN, 0.15 * span)
        return low + margin, high - margin

    def _choose_target(self, start: float, amount: float, low: float, high: float, direction: int) -> float:
        lo, hi = self._usable_window(low, high)
        if not low < start < high:
            raise RuntimeError("current angle outside URDF range")
        candidates = []
        if direction >= 0 and lo <= start + amount <= hi:
            candidates.append(start + amount)
        if direction <= 0 and lo <= start - amount <= hi:
            candidates.append(start - amount)
        if not candidates:
            # If start itself sits outside the soft window (near a hard stop),
            # only allow a step that moves back toward the usable center.
            mid = 0.5 * (lo + hi)
            toward = mid - start
            step = math.copysign(amount, toward) if toward != 0 else amount
            target = start + step
            if low < target < high and abs(target - mid) < abs(start - mid):
                return target
            raise RuntimeError("no safe direction with requested step")
        # Prefer positive when both available and direction==0.
        return candidates[0]

    def _read_angle_locked(self, joint: int) -> float:
        if self.mock:
            return self._mock_angles[joint - 1]
        if not self._session_open or self._bus is None:
            raise RuntimeError("control session not open")
        mid = LEFT_IDS[joint]
        if joint <= 5:
            from linkerbot.arm.a7.motor import A7Motor, SensorType

            motor = A7Motor(mid, self._bus)
            if not motor.check_alive(timeout_s=1.0):
                raise RuntimeError(f"J{joint} offline")
            return float(motor._read_register_float(SensorType.POSITION, timeout_s=1.0))
        from linkerbot.arm.p7.motor_v2 import MotorV2

        motor = MotorV2(mid, self._bus)
        if not motor.check_alive(timeout_s=1.0):
            raise RuntimeError(f"J{joint} offline")
        motor.read_initial_state(timeout_s=1.5)
        return float(motor.angle.angle)

    def _enable_v1_locked(self, plan: JointPlan) -> None:
        from linkerbot.arm.a7.motor import A7Motor, InternalSensorType, SensorType
        from linkerbot.arm.common import ControlMode

        motor = A7Motor(plan.motor_id, self._bus)
        if not motor.check_alive(timeout_s=1.0):
            raise RuntimeError("motor offline")
        motor.read_initial_state(timeout_s=1.0)
        if motor.enabled:
            raise RuntimeError("motor already enabled; refuse takeover")
        start = float(motor._read_register_float(SensorType.POSITION, timeout_s=1.0))
        motor.set_control_mode(ControlMode.PP)
        motor.set_velocity(V1_SPEED)
        motor.set_acceleration(V1_ACCEL)
        motor.set_deceleration(V1_ACCEL)
        motor.set_angle(start)
        motor.enable()
        time.sleep(0.25)
        if not bool(motor._read_register(InternalSensorType.ENABLED, timeout_s=0.8)[0]):
            raise RuntimeError("enable not confirmed")
        after = float(motor._read_register_float(SensorType.POSITION, timeout_s=1.0))
        if abs(after - start) > math.radians(2):
            motor.disable()
            raise RuntimeError("position jumped after enable")
        # Recompute target from post-enable pose with same signed step.
        signed = abs(plan.step_rad) if plan.target_rad >= plan.start_rad else -abs(plan.step_rad)
        low, high = plan.limits
        plan.start_rad = after
        plan.target_rad = self._choose_target(after, abs(signed), low, high, 1 if signed >= 0 else -1)
        plan.step_rad = plan.target_rad - plan.start_rad
        self._motor = motor

    def _move_v1_locked(self, plan: JointPlan) -> float:
        from linkerbot.arm.a7.motor import SensorType

        motor = self._motor
        motor.set_angle(plan.target_rad)
        t0 = time.monotonic()
        latest = plan.start_rad
        while time.monotonic() - t0 < V1_TIMEOUT_S:
            time.sleep(0.2)
            latest = float(motor._read_register_float(SensorType.POSITION, timeout_s=1.0))
            if abs(plan.target_rad - latest) < math.radians(1.0):
                break
            if not (plan.limits[0] < latest < plan.limits[1]):
                motor.set_angle(latest)
                raise RuntimeError("feedback left URDF range")
        motor.set_angle(latest)
        return latest

    def _enable_v2_locked(self, plan: JointPlan) -> None:
        from linkerbot.arm.p7.motor_v2 import MotorV2

        motor = MotorV2(plan.motor_id, self._bus)
        if not motor.check_alive(timeout_s=1.0):
            raise RuntimeError("V2 offline")
        param = motor._read_flash_param(0x0B, timeout_s=1.0)
        mode = int.from_bytes(param[:4], "little", signed=True)
        if mode != 2:
            raise RuntimeError(f"V2 mode={mode}, refuse (want P-T-M=2); not writing Flash")
        motor.read_initial_state(timeout_s=1.5)
        if motor.fault_code:
            raise RuntimeError(f"fault={motor.fault_code}")
        if motor.enabled:
            raise RuntimeError("V2 already enabled; refuse takeover")
        motor.set_position_kp(V2_KP)
        motor.enable()
        motor.start_polling()
        self._v2_polling = True
        motor.set_angle(motor.angle.angle)
        time.sleep(0.4)
        age = time.time() - motor.angle.timestamp
        if motor.fault_code or not motor.enabled or age > 0.3:
            if self._v2_polling:
                motor.stop_polling()
                self._v2_polling = False
            motor.disable()
            raise RuntimeError("V2 enable abnormal")
        start = float(motor.angle.angle)
        signed = abs(plan.step_rad) if plan.target_rad >= plan.start_rad else -abs(plan.step_rad)
        plan.start_rad = start
        plan.target_rad = self._choose_target(start, abs(signed), *plan.limits, 1 if signed >= 0 else -1)
        plan.step_rad = plan.target_rad - plan.start_rad
        self._motor = motor

    def _move_v2_locked(self, plan: JointPlan) -> float:
        motor = self._motor
        t0 = time.perf_counter()
        previous = plan.start_rad
        steps = int(V2_DURATION_S * V2_RATE_HZ) + 1
        for k in range(steps):
            delay = t0 + k / V2_RATE_HZ - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            actual = float(motor.angle.angle)
            age = time.time() - motor.angle.timestamp
            if age > 0.3 or not motor.enabled or motor.fault_code:
                raise RuntimeError("V2 feedback abnormal during move")
            if abs(actual - previous) > math.radians(2):
                raise RuntimeError("V2 sample jump >2deg")
            previous = actual
            s = k / max(1, steps - 1)
            easing = 3 * s * s - 2 * s * s * s
            target = plan.start_rad + (plan.target_rad - plan.start_rad) * easing
            motor.set_angle(target)
        time.sleep(0.3)
        end = float(motor.angle.angle)
        motor.set_angle(end)
        return end

    def _disable_locked(self, plan: JointPlan) -> None:
        motor = self._motor
        if motor is None:
            return
        try:
            if plan.kind == "V2" and self._v2_polling:
                motor.stop_polling()
                self._v2_polling = False
        except Exception:  # noqa: BLE001
            pass
        try:
            if plan.enabled:
                motor.disable()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"disable: {exc}"

    def _force_release_locked(self) -> None:
        if self._plan is not None:
            try:
                self._disable_locked(self._plan)
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
        self._plan = None
        self._motor = None
        self._v2_polling = False
