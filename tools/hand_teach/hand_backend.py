"""Left O6 backend for Hand Teach web UI. No arm motion."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from brick_stacking.manual_teach.presets import (  # noqa: E402
    GRASP_PERCENT,
    RELEASE_PERCENT,
    as_percent_list,
)

CHANNEL_NAMES = (
    "thumb_flex",
    "thumb_abd",
    "index",
    "middle",
    "ring",
    "pinky",
)

# Previous grasp / draft poses are retired. Release is the non-grasp pose.
PRESETS = {
    "抓取": as_percent_list(GRASP_PERCENT),
    "松开": as_percent_list(RELEASE_PERCENT),
}


def _clamp_percent(values: list[float]) -> list[float]:
    if len(values) != 6:
        raise ValueError("exactly six percent channels required")
    out = [float(v) for v in values]
    if any(not (0.0 <= v <= 100.0) for v in out):
        raise ValueError("percent values must be in [0, 100]")
    return out


class HandTeachBackend:
    def __init__(
        self,
        *,
        side: str = "left",
        interface: str = "can1",
        enable_hand: bool = False,
        max_speed_percent: float = 15.0,
        poll_hz: float = 5.0,
    ):
        if side != "left" or interface != "can1":
            raise ValueError("this teach UI is locked to left O6 on can1")
        self.side = side
        self.interface = interface
        self.enable_hand = bool(enable_hand)
        self.max_speed_percent = float(max_speed_percent)
        self.poll_period = 1.0 / max(float(poll_hz), 0.5)
        self._lock = threading.RLock()
        self._hand = None
        self._session_open = False
        self._last_error: str | None = None
        self._angles: list[float] | None = None
        self._stamp_mono: float | None = None
        self._serial: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        from linkerbot import O6

        with self._lock:
            if self._hand is not None:
                return
            hand = O6(side=self.side, interface_name=self.interface)
            try:
                hand.stop_polling()
            except Exception:
                pass
            try:
                self._serial = hand.version.get_device_info().serial_number
            except Exception as exc:
                self._last_error = f"serial_read:{exc!r}"
                self._serial = None
            if self._serial and "-L-" not in self._serial:
                hand.close()
                raise RuntimeError(f"expected left hand SN, got {self._serial}")
            self._hand = hand
            self._stop.clear()
            self._thread = threading.Thread(target=self._poll_loop, name="hand-teach-poll", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            hand = self._hand
            self._hand = None
            self._session_open = False
        if hand is not None:
            try:
                hand.stop_polling()
            except Exception:
                pass
            try:
                hand.close()
            except Exception:
                pass

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    hand = self._hand
                if hand is None:
                    break
                data = hand.angle.get_blocking(timeout_ms=800)
                vals = [float(x) for x in data.angles.to_list()]
                with self._lock:
                    self._angles = vals
                    self._stamp_mono = time.monotonic()
                    self._last_error = None
            except Exception as exc:
                with self._lock:
                    self._last_error = repr(exc)
            self._stop.wait(self.poll_period)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "side": self.side,
                "interface": self.interface,
                "serial_number": self._serial,
                "enable_hand": self.enable_hand,
                "session_open": self._session_open,
                "max_speed_percent": self.max_speed_percent,
                "channel_names": list(CHANNEL_NAMES),
                "angles_percent": None if self._angles is None else list(self._angles),
                "stamp_mono": self._stamp_mono,
                "age_s": None if self._stamp_mono is None else (time.monotonic() - self._stamp_mono),
                "last_error": self._last_error,
                "presets": {k: list(v) for k, v in PRESETS.items()},
                "motion_commanded_arm": False,
            }

    def open_session(self, confirm: str) -> dict[str, Any]:
        if not self.enable_hand:
            raise RuntimeError("server started without --enable-hand")
        if confirm != "READY":
            raise ValueError('confirm must be "READY"')
        with self._lock:
            self._session_open = True
        return self.snapshot()

    def close_session(self) -> dict[str, Any]:
        with self._lock:
            self._session_open = False
        return self.snapshot()

    def apply(
        self,
        *,
        angles_percent: list[float],
        speed_percent: float,
        confirm: str,
    ) -> dict[str, Any]:
        if not self.enable_hand:
            raise RuntimeError("server started without --enable-hand")
        if confirm != "APPLY":
            raise ValueError('confirm must be "APPLY"')
        targets = _clamp_percent(angles_percent)
        speed = float(speed_percent)
        if not (0.0 < speed <= self.max_speed_percent):
            raise ValueError(f"speed_percent must be in (0, {self.max_speed_percent}]")
        speeds = [speed] * 6
        with self._lock:
            if not self._session_open:
                raise RuntimeError("open READY session before APPLY")
            hand = self._hand
            if hand is None:
                raise RuntimeError("hand not opened")
            before = None if self._angles is None else list(self._angles)
            hand.speed.set_speeds(speeds)
            hand.angle.set_angles(targets)
        time.sleep(0.05)
        # Fresh read outside long critical section.
        after = [float(x) for x in hand.angle.get_blocking(timeout_ms=800).angles.to_list()]
        with self._lock:
            self._angles = after
            self._stamp_mono = time.monotonic()
        return {
            "ok": True,
            "before_percent": before,
            "target_percent": targets,
            "speed_percent": speed,
            "after_percent": after,
            "snapshot": self.snapshot(),
        }
