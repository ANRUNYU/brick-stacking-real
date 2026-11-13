"""Manual teach log: 100 Hz ticks, one file per ended take, locked hand poses."""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from brick_stacking.manual_teach.presets import (
    GRASP_PERCENT,
    RELEASE_PERCENT,
    VICTORY_PERCENT,
    VICTORY_RAW_U8,
    VICTORY_SOURCE_URL,
)
from brick_stacking.manual_teach.recorder import StreamRecorder, sleep_until
from brick_stacking.manual_teach.session import TeachSession

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "hand_teach"))

import hand_backend  # noqa: E402


WALL = datetime(2026, 11, 13, 3, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_percent_raw_mapping_matches_live_feedback() -> None:
    from brick_stacking.manual_teach.presets import percent_to_raw_u8, raw_u8_to_percent

    assert raw_u8_to_percent(213) == 213 * 100.0 / 255.0
    assert percent_to_raw_u8(raw_u8_to_percent(213)) == 213
    assert [percent_to_raw_u8(v) for v in GRASP_PERCENT] == [104, 61, 195, 186, 0, 0]
    assert [percent_to_raw_u8(v) for v in RELEASE_PERCENT] == [213, 61, 215, 215, 0, 0]
    assert [percent_to_raw_u8(v) for v in VICTORY_PERCENT] == list(VICTORY_RAW_U8)


def test_presets_match_operator_readings() -> None:
    assert GRASP_PERCENT == (40.8, 23.9, 76.5, 72.9, 0.0, 0.0)
    assert RELEASE_PERCENT == (83.5, 23.9, 84.3, 84.3, 0.0, 0.0)
    assert hand_backend.PRESETS["抓取"] == [40.8, 23.9, 76.5, 72.9, 0.0, 0.0]
    assert hand_backend.PRESETS["松开"] == [83.5, 23.9, 84.3, 84.3, 0.0, 0.0]
    assert hand_backend.PRESETS["胜利手势"] == list(VICTORY_PERCENT)
    assert "github.com/linker-bot/primitive/blob/5d0599e" in VICTORY_SOURCE_URL
    assert "three_finger_soft_draft" not in hand_backend.PRESETS


def test_hundred_hertz_loop_writes_one_sample_per_tick(tmp_path: Path) -> None:
    recorder = StreamRecorder(tmp_path)
    recorder.start(wall=WALL)

    class Clock:
        def __init__(self) -> None:
            self.t = 0.0

        def now(self) -> float:
            return self.t

        def sleep(self, delay: float) -> None:
            self.t += delay

    clock = Clock()
    stop = threading.Event()

    def tick() -> None:
        recorder.observe(
            {
                "q_rad": [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7],
                "hand_percent": list(RELEASE_PERCENT),
                "q_age_s": 0.001,
                "hand_age_s": 0.004,
            }
        )
        if recorder.count >= 20:
            stop.set()

    period = 0.01
    next_t = clock.now()
    while not stop.is_set():
        tick()
        next_t += period
        delay = next_t - clock.now()
        if delay > 0:
            clock.sleep(delay)
    path = recorder.end(wall=WALL)
    rows = _lines(path)
    samples = [row for row in rows if row["type"] == "sample"]
    assert len(samples) == 20
    assert abs(clock.t - 0.20) < 1e-9
    assert rows[0]["schema"] == "manual-teach-stream-1"
    assert rows[0]["hz"] == 100
    assert rows[0]["arm_joints"] == ["J1", "J2", "J3", "J4", "J5", "J6", "J7"]
    assert rows[0]["grasp_percent"] == [40.8, 23.9, 76.5, 72.9, 0.0, 0.0]
    assert rows[0]["release_percent"] == [83.5, 23.9, 84.3, 84.3, 0.0, 0.0]
    assert rows[0]["arm_motion_commanded"] is False
    assert samples[0]["q_rad"] == [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7]
    assert samples[0]["hand_percent"] == [83.5, 23.9, 84.3, 84.3, 0.0, 0.0]
    assert samples[-1]["i"] == 20
    assert rows[-1]["type"] == "end"
    assert rows[-1]["samples"] == 20


def test_end_then_start_opens_a_new_file_pause_keeps_the_same_one(tmp_path: Path) -> None:
    recorder = StreamRecorder(tmp_path)
    first = recorder.start(wall=WALL)
    assert first["created"] is True
    assert recorder.observe({"q_rad": [0] * 7, "hand_percent": [0] * 6, "q_age_s": 0, "hand_age_s": 0})
    recorder.pause(wall=WALL)
    assert recorder.observe({"q_rad": [1] * 7, "hand_percent": [1] * 6, "q_age_s": 0, "hand_age_s": 0}) is False
    assert recorder.mark_hand("grasp", list(GRASP_PERCENT), 12) is True
    resumed = recorder.start(wall=WALL)
    assert resumed["created"] is False
    assert resumed["name"] == first["name"]
    recorder.observe({"q_rad": [0.2] * 7, "hand_percent": list(GRASP_PERCENT), "q_age_s": 0, "hand_age_s": 0})
    path1 = recorder.end(wall=WALL)
    second = recorder.start(wall=WALL)
    path2 = recorder.end(wall=WALL)

    assert path1 != path2
    assert path1.name.startswith("teach_01_20261113_031200")
    assert path2.name.startswith("teach_02_20261113_031200")
    rows = _lines(path1)
    assert [row["type"] for row in rows] == ["header", "sample", "pause", "hand", "resume", "sample", "end"]
    assert rows[3]["action"] == "grasp"
    assert rows[3]["target_percent"][0] == 40.8
    assert _lines(path2)[0]["index"] == 2
    assert recorder.observe({"q_rad": [0] * 7, "hand_percent": [0] * 6, "q_age_s": 0, "hand_age_s": 0}) is False


def test_mock_grasp_reaches_new_pose_and_release_is_the_idle_pose(tmp_path: Path) -> None:
    session = TeachSession(tmp_path, mock=True)
    assert session.snapshot()["hand"]["percent"] == [83.5, 23.9, 84.3, 84.3, 0.0, 0.0]
    session.record_start()
    session.apply_preset("grasp", 15)
    session.advance_mock(1.0)
    snap = session.snapshot()
    assert snap["hand"]["percent"] == [40.8, 23.9, 76.5, 72.9, 0.0, 0.0]
    assert snap["arm_motion_commanded"] is False
    path = session.recorder.end()
    actions = [row for row in _lines(path) if row["type"] == "hand"]
    assert actions[0]["action"] == "grasp"
    session.apply_preset("release", 12)
    session.advance_mock(1.0)
    assert session.snapshot()["hand"]["percent"] == [83.5, 23.9, 84.3, 84.3, 0.0, 0.0]


def test_remote_grasp_posts_the_live_hand_api_and_arm_q_is_not_invented(tmp_path: Path) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    seen: dict = {"apply": None, "opened": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, payload: dict) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/q":
                self._send({"ok": True, "q_rad": [0.2, -0.1, 0.3, -0.4, 1.2, -0.2, 0.1], "age_s": 0.01, "read_hz": 80})
                return
            if path == "/api/state":
                self._send({
                    "ok": True,
                    "state": {
                        "enable_hand": True,
                        "session_open": seen["opened"],
                        "max_speed_percent": 50,
                        "angles_percent": [83.5, 23.9, 84.3, 84.3, 0.0, 0.0],
                        "serial_number": "LHO6-TEST",
                        "age_s": 0.05,
                        "last_error": None,
                    },
                })
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or "0")
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if self.path == "/api/session/open":
                seen["opened"] = body.get("confirm") == "READY"
                self._send({"ok": True, "state": {"session_open": seen["opened"], "enable_hand": True}})
                return
            if self.path == "/api/apply":
                seen["apply"] = body
                self._send({"ok": True, "after_percent": body.get("angles_percent")})
                return
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        session = TeachSession(
            tmp_path,
            mock=False,
            hand_url=f"http://127.0.0.1:{port}",
            arm_url=f"http://127.0.0.1:{port}",
        )
        session.start_background()
        deadline = time.time() + 3
        snap = session.snapshot()
        while time.time() < deadline and not (snap["link"]["arm_ok"] and snap["link"]["hand_ok"]):
            time.sleep(0.05)
            snap = session.snapshot()
        assert snap["mock"] is False
        assert snap["arm"]["q_rad"][0] == 0.2
        assert snap["hand"]["percent"][0] == 83.5
        session.apply_preset("grasp", 12)
        assert seen["opened"] is True
        assert seen["apply"]["confirm"] == "APPLY"
        assert seen["apply"]["angles_percent"] == [40.8, 23.9, 76.5, 72.9, 0.0, 0.0]
        assert seen["apply"]["speed_percent"] == 12
    finally:
        session.shutdown()
        server.shutdown()


def test_sleep_until_returns_when_deadline_already_passed() -> None:
    stop = threading.Event()
    assert sleep_until(0.0, stop, now=lambda: 1.0) is False
    stop.set()
    assert sleep_until(10.0, stop, now=lambda: 0.0) is True
