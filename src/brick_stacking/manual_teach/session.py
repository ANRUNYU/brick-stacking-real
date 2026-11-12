"""Teach session: read left arm, command only grasp/release, log at 100 Hz.

The arm object is read with get_angles() only. This module never enables the
arm and never calls move_j, move_l, or rest.
"""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Any

from brick_stacking.manual_teach.presets import (
    ARM_JOINTS,
    DEFAULT_SPEED_PERCENT,
    GRASP_PERCENT,
    HAND_CHANNELS,
    HAND_LABELS_ZH,
    MAX_SPEED_PERCENT,
    RELEASE_PERCENT,
    SAMPLE_HZ,
    as_percent_list,
)
from brick_stacking.manual_teach.recorder import (
    StreamRecorder,
    boost_sleep_resolution,
    restore_sleep_resolution,
    sleep_until,
)
from brick_stacking.manual_teach.remote_link import JsonLink


class TeachSession:
    def __init__(
        self,
        directory: Path,
        *,
        mock: bool = True,
        enable_hand: bool = False,
        max_speed_percent: float = MAX_SPEED_PERCENT,
        repo_root: Path | None = None,
        hand_url: str = "",
        arm_url: str = "",
    ) -> None:
        self.recorder = StreamRecorder(directory)
        self.hand_url = hand_url.strip().rstrip("/")
        self.arm_url = arm_url.strip().rstrip("/")
        self.remote = bool(self.hand_url or self.arm_url)
        self.mock = False if self.remote else bool(mock)
        self.enable_hand = bool(self.hand_url) or (True if self.mock else bool(enable_hand))
        self.max_speed_percent = float(max_speed_percent)
        self.speed_percent = min(DEFAULT_SPEED_PERCENT, self.max_speed_percent)
        self.repo_root = repo_root
        self.session_open = bool(self.mock)
        self.serial: str | None = None
        self.arm_error: str | None = "臂读数未连接" if self.arm_url else None
        self.hand_error: str | None = "手接口未连接" if self.hand_url else None
        self._hand_link = JsonLink(self.hand_url) if self.hand_url else None
        self._arm_link = JsonLink(self.arm_url) if self.arm_url else None
        self._arm_read_hz: float | None = None
        self._q_src_age: float | None = None
        self._hand_src_age: float | None = None
        self._dev_lock = threading.RLock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._arm = None
        self._hand_dev = None
        self._q: list[float] | None = [0.0] * 7 if self.mock else None
        self._q_mono: float | None = time.monotonic() if self.mock else None
        self._hand: list[float] | None = as_percent_list(RELEASE_PERCENT) if self.mock else None
        self._hand_mono: float | None = time.monotonic() if self.mock else None
        self._hand_target: list[float] | None = None
        self._started = False

    def start_background(self) -> None:
        if self._started:
            return
        if not self.mock and not self.remote:
            self._open_devices()
        self._stop.clear()
        boost_sleep_resolution()
        targets = [self._record_loop]
        if self.remote:
            if self._arm_link is not None:
                targets.append(self._remote_arm_loop)
            if self._hand_link is not None:
                targets.append(self._remote_hand_loop)
        elif self.mock:
            targets.append(self._mock_loop)
        else:
            targets.append(self._arm_loop)
            targets.append(self._hand_loop)
        self._threads = [
            threading.Thread(target=fn, name=f"teach-{fn.__name__}", daemon=True) for fn in targets
        ]
        for thread in self._threads:
            thread.start()
        self._started = True

    def shutdown(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads = []
        try:
            if self.recorder.state != "idle":
                self.recorder.end()
        except Exception:
            pass
        self._close_devices()
        if self._hand_link is not None:
            self._hand_link.close()
        if self._arm_link is not None:
            self._arm_link.close()
        restore_sleep_resolution()
        self._started = False

    def open_session(self, confirm: str) -> dict[str, Any]:
        if confirm != "READY":
            raise ValueError('confirm must be "READY"')
        if not self.enable_hand:
            raise RuntimeError("服务未加 --enable-hand，不能准备手")
        if self._hand_link is not None:
            self._open_remote_hand()
        else:
            self.session_open = True
        return self.snapshot()

    def record_start(self) -> dict[str, Any]:
        self.recorder.start()
        return self.snapshot()

    def record_pause(self) -> dict[str, Any]:
        self.recorder.pause()
        return self.snapshot()

    def record_end(self) -> dict[str, Any]:
        self.recorder.end()
        return self.snapshot()

    def apply_preset(self, action: str, speed: float | None = None) -> dict[str, Any]:
        if action == "grasp":
            target = as_percent_list(GRASP_PERCENT)
        elif action == "release":
            target = as_percent_list(RELEASE_PERCENT)
        else:
            raise ValueError("action must be grasp or release")
        if not self.enable_hand:
            raise RuntimeError("服务未加 --enable-hand，不能下手")
        chosen = self.speed_percent if speed is None else float(speed)
        if chosen <= 0:
            raise ValueError("速度要大于 0")
        if self._hand_link is not None:
            chosen = self._apply_remote_hand(target, chosen)
        else:
            if not self.session_open:
                raise RuntimeError("先点「准备手」")
            if not (chosen <= self.max_speed_percent + 1e-9):
                raise ValueError(f"速度需在 1–{self.max_speed_percent:g} 之间")
            with self._dev_lock:
                self.speed_percent = chosen
                self._hand_target = list(target)
                if not self.mock:
                    hand = self._hand_dev
                    if hand is None:
                        raise RuntimeError("手未连接")
                    hand.speed.set_speeds([chosen] * 6)
                    hand.angle.set_angles(list(target))
        self.recorder.mark_hand(action, target, chosen)
        return self.snapshot()

    def _open_remote_hand(self) -> None:
        link = self._hand_link
        if link is None:
            raise RuntimeError("没有手接口")
        data = link.post("/api/session/open", {"confirm": "READY"})
        state = data.get("state") or {}
        with self._dev_lock:
            self.session_open = bool(state.get("session_open", True))
            self.hand_error = None

    def _apply_remote_hand(self, target: list[float], speed: float) -> float:
        link = self._hand_link
        if link is None:
            raise RuntimeError("没有手接口")
        state = (link.get("/api/state").get("state") or {})
        remote_max = float(state.get("max_speed_percent") or self.max_speed_percent)
        chosen = min(float(speed), remote_max)
        if chosen <= 0:
            raise ValueError("速度要大于 0")
        if not state.get("enable_hand"):
            raise RuntimeError("手上的控制接口没有打开")
        if not state.get("session_open"):
            opened = link.post("/api/session/open", {"confirm": "READY"})
            if not (opened.get("state") or {}).get("session_open", True):
                raise RuntimeError("手接口没有开会话")
        link.post(
            "/api/apply",
            {"confirm": "APPLY", "speed_percent": chosen, "angles_percent": list(target)},
        )
        with self._dev_lock:
            self.speed_percent = chosen
            self.max_speed_percent = remote_max
            self.session_open = True
            self._hand_target = list(target)
            self.hand_error = None
        return chosen

    def _remote_arm_loop(self) -> None:
        link = self._arm_link
        assert link is not None
        while not self._stop.is_set():
            try:
                data = link.get("/api/q")
                q = data.get("q_rad")
                if not data.get("ok") or not isinstance(q, list) or len(q) != 7:
                    raise RuntimeError(str(data.get("error") or "臂读数无效"))
                with self._dev_lock:
                    self._q = [float(v) for v in q]
                    self._q_mono = time.monotonic()
                    self._q_src_age = float(data.get("age_s") or 0.0)
                    self._arm_read_hz = data.get("read_hz")
                    self.arm_error = None
            except Exception as exc:
                with self._dev_lock:
                    self.arm_error = f"臂读数未连接: {exc}"
                if self._stop.wait(0.2):
                    break
                continue
            if self._stop.wait(0.01):
                break

    def _remote_hand_loop(self) -> None:
        link = self._hand_link
        assert link is not None
        while not self._stop.is_set():
            try:
                state = (link.get("/api/state").get("state") or {})
                angles = state.get("angles_percent")
                if not isinstance(angles, list) or len(angles) != 6:
                    raise RuntimeError(str(state.get("last_error") or "手读数无效"))
                with self._dev_lock:
                    self._hand = [float(v) for v in angles]
                    self._hand_mono = time.monotonic()
                    self._hand_src_age = float(state.get("age_s") or 0.0)
                    self.session_open = bool(state.get("session_open"))
                    self.serial = state.get("serial_number")
                    remote_max = state.get("max_speed_percent")
                    if remote_max:
                        self.max_speed_percent = float(remote_max)
                    err = state.get("last_error")
                    self.hand_error = None if not err else str(err)
            except Exception as exc:
                with self._dev_lock:
                    self.hand_error = f"手接口未连接: {exc}"
                if self._stop.wait(0.3):
                    break
                continue
            if self._stop.wait(0.08):
                break

    def advance_mock(self, dt: float) -> None:
        if not self.mock:
            return
        with self._dev_lock:
            self._mock_arm()
            self._approach_hand(dt)

    def snapshot(self) -> dict[str, Any]:
        with self._dev_lock:
            q = None if self._q is None else list(self._q)
            hand = None if self._hand is None else list(self._hand)
            target = None if self._hand_target is None else list(self._hand_target)
            q_age = _shown_age(self._q_mono, self._q_src_age)
            hand_age = _shown_age(self._hand_mono, self._hand_src_age)
            arm_error = self.arm_error
            hand_error = self.hand_error
            speed = self.speed_percent
            arm_ok = self._q is not None and arm_error is None
            hand_ok = self._hand is not None and hand_error is None
            arm_hz = self._arm_read_hz
        record = self.recorder.status()
        directory = self.recorder.directory
        return {
            "ok": True,
            "mock": self.mock,
            "enable_hand": self.enable_hand,
            "session_open": self.session_open,
            "serial_number": self.serial,
            "hz": SAMPLE_HZ,
            "directory": _display_path(directory, self.repo_root),
            "record": record,
            "recent_files": self.recorder.recent_names(),
            "arm": {
                "names": list(ARM_JOINTS),
                "unit": "rad",
                "q_rad": q,
                "age_s": None if q_age is None else round(q_age, 4),
                "error": arm_error,
            },
            "hand": {
                "names": list(HAND_CHANNELS),
                "labels": list(HAND_LABELS_ZH),
                "unit": "percent",
                "percent": hand,
                "target": target,
                "age_s": None if hand_age is None else round(hand_age, 4),
                "error": hand_error,
            },
            "presets": {
                "grasp": as_percent_list(GRASP_PERCENT),
                "release": as_percent_list(RELEASE_PERCENT),
            },
            "speed_percent": speed,
            "max_speed_percent": self.max_speed_percent,
            "link": {
                "hand_url": self.hand_url,
                "arm_url": self.arm_url,
                "hand_ok": hand_ok,
                "arm_ok": arm_ok,
                "arm_read_hz": arm_hz,
            },
            "arm_motion_commanded": False,
        }

    def _sample(self) -> dict[str, Any]:
        with self._dev_lock:
            now = time.monotonic()
            return {
                "q_rad": None if self._q is None else list(self._q),
                "hand_percent": None if self._hand is None else list(self._hand),
                "q_age_s": None if self._q_mono is None else max(0.0, now - self._q_mono),
                "hand_age_s": None if self._hand_mono is None else max(0.0, now - self._hand_mono),
            }

    def _record_loop(self) -> None:
        period = 1.0 / float(SAMPLE_HZ)
        next_t = time.perf_counter()
        while not self._stop.is_set():
            try:
                self.recorder.observe(self._sample())
            except Exception as exc:
                self.arm_error = f"record:{exc}"
            next_t += period
            if sleep_until(next_t, self._stop):
                break
            if time.perf_counter() - next_t > period:
                next_t = time.perf_counter()

    def _mock_loop(self) -> None:
        while not self._stop.is_set():
            self.advance_mock(0.02)
            if self._stop.wait(0.02):
                break

    def _arm_loop(self) -> None:
        while not self._stop.is_set():
            arm = self._arm
            if arm is None:
                break
            try:
                q = [float(v) for v in arm.get_angles()]
                with self._dev_lock:
                    self._q = q
                    self._q_mono = time.monotonic()
                    self.arm_error = None
            except Exception as exc:
                with self._dev_lock:
                    self.arm_error = f"arm_read:{exc}"
            if self._stop.wait(0.001):
                break

    def _hand_loop(self) -> None:
        while not self._stop.is_set():
            hand = self._hand_dev
            if hand is None:
                break
            try:
                data = hand.angle.get_blocking(timeout_ms=50)
                vals = [float(x) for x in data.angles.to_list()]
                with self._dev_lock:
                    self._hand = vals
                    self._hand_mono = time.monotonic()
                    self.hand_error = None
            except Exception as exc:
                with self._dev_lock:
                    self.hand_error = f"hand_read:{exc}"

    def _open_devices(self) -> None:
        from linkerbot import O6, P7  # type: ignore

        arm = P7(side="left", interface_name="can2")
        hand = O6(side="left", interface_name="can1")
        try:
            hand.stop_polling()
        except Exception:
            pass
        serial = None
        try:
            serial = hand.version.get_device_info().serial_number
        except Exception as exc:
            self.hand_error = f"serial_read:{exc}"
        if serial and "-L-" not in str(serial):
            try:
                hand.close()
            except Exception:
                pass
            try:
                arm.close()
            except Exception:
                pass
            raise RuntimeError(f"expected left hand SN, got {serial}")
        self._arm = arm
        self._hand_dev = hand
        self.serial = None if serial is None else str(serial)

    def _close_devices(self) -> None:
        hand = self._hand_dev
        arm = self._arm
        self._hand_dev = None
        self._arm = None
        if hand is not None:
            try:
                hand.stop_polling()
            except Exception:
                pass
            try:
                hand.close()
            except Exception:
                pass
        if arm is not None:
            try:
                arm.close()
            except Exception:
                pass

    def _mock_arm(self) -> None:
        t = time.monotonic()
        self._q = [0.15 * math.sin(t * 0.8 + i * 0.4) for i in range(7)]
        self._q_mono = t

    def _approach_hand(self, dt: float) -> None:
        if self._hand is None or self._hand_target is None:
            return
        rate = max(self.speed_percent, 1.0) * 4.0
        step = rate * max(0.0, float(dt))
        moved: list[float] = []
        if len(self._hand) != len(self._hand_target):
            return
        for current, target in zip(self._hand, self._hand_target):
            delta = target - current
            if abs(delta) <= step:
                moved.append(target)
            else:
                moved.append(current + step * (1.0 if delta > 0 else -1.0))
        self._hand = moved
        self._hand_mono = time.monotonic()


def _shown_age(received_mono: float | None, source_age: float | None) -> float | None:
    if received_mono is None:
        return None
    local = max(0.0, time.monotonic() - received_mono)
    extra = 0.0 if source_age is None else max(0.0, float(source_age))
    return round(local + extra, 4)


def _display_path(path: Path, repo_root: Path | None) -> str:
    resolved = path.resolve()
    if repo_root is not None:
        try:
            return resolved.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    return str(resolved)
