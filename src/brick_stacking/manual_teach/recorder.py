"""100 Hz jsonl teach log. One file per start, until end.

Pause keeps the same file. The next start after end creates a new file.
Arm motion is never commanded here; this module only writes samples.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from brick_stacking.manual_teach.presets import (
    ARM_JOINTS,
    GRASP_PERCENT,
    HAND_CHANNELS,
    HAND_LABELS_ZH,
    RELEASE_PERCENT,
    SAMPLE_HZ,
    as_percent_list,
)


def boost_sleep_resolution() -> None:
    """Ask Windows for a 1 ms sleep quantum so a 10 ms period can hold 100 Hz."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        return


def restore_sleep_resolution() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        return


def sleep_until(deadline: float, stop: threading.Event, *, now=time.perf_counter) -> bool:
    """Wait until `deadline`. Return True if `stop` was set.

    Uses time.sleep, not Event.wait. On Windows, Event.wait stays on the
    coarse scheduler quantum and a 10 ms period falls to about 70 Hz.
    """
    while not stop.is_set():
        remain = deadline - now()
        if remain <= 0:
            return False
        time.sleep(remain if remain < 0.05 else 0.05)
    return True


def _wall(moment: datetime | None = None) -> str:
    current = moment or datetime.now().astimezone()
    return current.isoformat(timespec="milliseconds")


def _round_vec(values: Any, n: int, places: int) -> list[float] | None:
    if values is None:
        return None
    try:
        seq = list(values)
    except TypeError:
        return None
    if len(seq) != n:
        return None
    try:
        return [round(float(v), places) for v in seq]
    except (TypeError, ValueError):
        return None


class StreamRecorder:
    """Append-only teach stream. States: idle, recording, paused."""

    def __init__(self, directory: Path, *, hz: int = SAMPLE_HZ) -> None:
        self.directory = Path(directory)
        self.hz = int(hz)
        self.state = "idle"
        self.path: Path | None = None
        self.last_path: Path | None = None
        self.count = 0
        self._fh = None
        self._lock = threading.Lock()
        self._run_started: float | None = None
        self._pause_started: float | None = None
        self._paused_total = 0.0
        self._first_mono: float | None = None
        self._last_mono: float | None = None
        self._finished_samples = 0
        self._finished_elapsed = 0.0
        self._finished_hz: float | None = None

    def start(self, *, wall: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            if self.state == "recording":
                return self._status_unlocked(created=False)
            if self.state == "paused":
                now = time.monotonic()
                if self._pause_started is not None:
                    self._paused_total += now - self._pause_started
                self._pause_started = None
                self.state = "recording"
                self._write_unlocked({"type": "resume", "t_mono": round(now, 6), "t_wall": _wall(wall)})
                return self._status_unlocked(created=False)
            self.directory.mkdir(parents=True, exist_ok=True)
            moment = wall or datetime.now().astimezone()
            index = self._next_index()
            name = f"teach_{index:02d}_{moment:%Y%m%d_%H%M%S}.jsonl"
            path = self.directory / name
            if path.exists():
                name = f"teach_{index:02d}_{moment:%Y%m%d_%H%M%S}_{time.time_ns()}.jsonl"
                path = self.directory / name
            self.path = path
            self._fh = path.open("a", encoding="utf-8", newline="\n")
            self.count = 0
            self._paused_total = 0.0
            self._pause_started = None
            self._run_started = time.monotonic()
            self._first_mono = None
            self._last_mono = None
            self.state = "recording"
            self._write_unlocked(self._header(moment, index))
            return self._status_unlocked(created=True)

    def pause(self, *, wall: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            if self.state != "recording":
                raise RuntimeError("只有正在记录时可以暂停")
            now = time.monotonic()
            self.state = "paused"
            self._pause_started = now
            self._write_unlocked(
                {
                    "type": "pause",
                    "t_mono": round(now, 6),
                    "t_wall": _wall(wall),
                    "samples": self.count,
                }
            )
            return self._status_unlocked(created=False)

    def end(self, *, wall: datetime | None = None) -> Path:
        with self._lock:
            if self.state == "idle" or self._fh is None or self.path is None:
                raise RuntimeError("没有打开的记录")
            now = time.monotonic()
            if self.state == "paused" and self._pause_started is not None:
                self._paused_total += now - self._pause_started
                self._pause_started = None
            elapsed = self._elapsed_unlocked(now)
            self._finished_samples = self.count
            self._finished_elapsed = elapsed
            self._finished_hz = self._hz_unlocked()
            self._write_unlocked(
                {
                    "type": "end",
                    "t_mono": round(now, 6),
                    "t_wall": _wall(wall),
                    "samples": self.count,
                    "elapsed_s": round(elapsed, 3),
                }
            )
            self._fh.close()
            self._fh = None
            path = self.path
            self.last_path = path
            self.path = None
            self.state = "idle"
            self._pause_started = None
            self._run_started = None
            return path

    def observe(self, sample: Mapping[str, Any]) -> bool:
        """Write one 100 Hz tick. No-op unless state is recording."""
        with self._lock:
            if self.state != "recording" or self._fh is None:
                return False
            now = time.monotonic()
            self.count += 1
            if self._first_mono is None:
                self._first_mono = now
            self._last_mono = now
            q = _round_vec(sample.get("q_rad"), 7, 6)
            hand = _round_vec(sample.get("hand_percent"), 6, 4)
            self._write_unlocked(
                {
                    "type": "sample",
                    "i": self.count,
                    "t_mono": round(now, 6),
                    "t_wall": _wall(),
                    "q_rad": q,
                    "hand_percent": hand,
                    "q_age_s": _age(sample.get("q_age_s")),
                    "hand_age_s": _age(sample.get("hand_age_s")),
                }
            )
            return True

    def mark_hand(
        self,
        action: str,
        target_percent: list[float],
        speed_percent: float,
        *,
        wall: datetime | None = None,
    ) -> bool:
        """Log a grasp/release command if a file is open (recording or paused)."""
        if action not in ("grasp", "release"):
            raise ValueError("action must be grasp or release")
        target = as_percent_list(target_percent)
        with self._lock:
            if self._fh is None:
                return False
            now = time.monotonic()
            self._write_unlocked(
                {
                    "type": "hand",
                    "action": action,
                    "t_mono": round(now, 6),
                    "t_wall": _wall(wall),
                    "target_percent": [round(v, 4) for v in target],
                    "speed_percent": round(float(speed_percent), 3),
                }
            )
            return True

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_unlocked(created=False)

    def recent_names(self, limit: int = 12) -> list[str]:
        if not self.directory.is_dir():
            return []
        files = list(self.directory.glob("teach_[0-9][0-9]_*.jsonl"))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.name for p in files[:limit]]

    def _header(self, moment: datetime, index: int) -> dict[str, Any]:
        return {
            "type": "header",
            "schema": "manual-teach-stream-1",
            "hz": self.hz,
            "index": index,
            "side": "left",
            "arm_interface": "can2",
            "hand_interface": "can1",
            "arm_joints": list(ARM_JOINTS),
            "arm_unit": "rad",
            "hand_channels": list(HAND_CHANNELS),
            "hand_labels_zh": list(HAND_LABELS_ZH),
            "hand_unit": "percent",
            "grasp_percent": as_percent_list(GRASP_PERCENT),
            "release_percent": as_percent_list(RELEASE_PERCENT),
            "arm_motion_commanded": False,
            "started_wall": _wall(moment),
            "note": (
                "Each sample is one tick of the latest arm get_angles() and hand percent. "
                "q_age_s and hand_age_s are how old that read was. "
                "The arm is never commanded. hand lines are operator grasp/release."
            ),
        }

    def _next_index(self) -> int:
        best = 0
        if self.directory.is_dir():
            for path in self.directory.glob("teach_[0-9][0-9]_*.jsonl"):
                parts = path.name.split("_")
                if len(parts) < 2:
                    continue
                try:
                    best = max(best, int(parts[1]))
                except ValueError:
                    continue
        return best + 1

    def _elapsed_unlocked(self, now: float | None = None) -> float:
        if self._run_started is None:
            return 0.0
        current = time.monotonic() if now is None else now
        paused = self._paused_total
        if self.state == "paused" and self._pause_started is not None:
            paused += current - self._pause_started
        return max(0.0, current - self._run_started - paused)

    def _hz_unlocked(self) -> float | None:
        if self.count < 2 or self._first_mono is None or self._last_mono is None:
            return None
        span = self._last_mono - self._first_mono
        if span <= 0:
            return None
        return (self.count - 1) / span

    def _status_unlocked(self, *, created: bool) -> dict[str, Any]:
        path = self.path
        if self.state == "idle":
            samples = self._finished_samples
            elapsed = self._finished_elapsed
            hz = self._finished_hz
        else:
            samples = self.count
            elapsed = self._elapsed_unlocked()
            hz = self._hz_unlocked()
        return {
            "state": self.state,
            "created": created,
            "path": None if path is None else str(path),
            "name": None if path is None else path.name,
            "last_name": None if self.last_path is None else self.last_path.name,
            "samples": samples,
            "elapsed_s": round(elapsed, 3),
            "measured_hz": None if hz is None else round(hz, 1),
        }

    def _write_unlocked(self, payload: Mapping[str, Any]) -> None:
        if self._fh is None:
            raise RuntimeError("record file is not open")
        self._fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()


def _age(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(max(0.0, float(value)), 4)
    except (TypeError, ValueError):
        return None
