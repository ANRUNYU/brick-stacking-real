"""LAN web monitor: camera preview, joint telemetry, optional single-joint control.

Camera:
  POST /api/camera/release | /api/camera/acquire

Joint control (requires --enable-motion; follows left_robot_motor_menu / p7_test_v1_joints):
  POST /api/control/session/open   body {"confirm":"READY"}
  POST /api/control/session/close
  POST /api/control/joint/prepare  body {"joint":1,"step_deg":5}
  POST /api/control/joint/enable   body {"joint":1,"confirm":"ENABLE"}
  POST /api/control/joint/move     body {"joint":1,"confirm":"MOVE"}
  POST /api/control/joint/release  body {"joint":1,"confirm":"RELEASE"}
  GET  /api/control/status

Does not construct linkerbot.P7 (Flash side effects). Uses A7Motor/MotorV2 only.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from joint_control import JointController  # noqa: E402
from sources import (  # noqa: E402
    HEAD_SERIAL_DEFAULT,
    LEFT_ARM,
    RIGHT_ARM,
    ArmReaderWorker,
    FramePacket,
    MockArmWorker,
    MockCameraWorker,
    MonitorHub,
    OrbbecCameraWorker,
)


class CameraController:
    def __init__(self, hub: MonitorHub, args):
        self.hub = hub
        self.args = args
        self._lock = threading.Lock()
        self._worker = None

    @property
    def held(self) -> bool:
        with self.hub.lock:
            return bool(self.hub.meta.get("camera_held"))

    def _make_worker(self):
        if self.args.mock:
            return MockCameraWorker(self.hub, "head", fps=8)
        return OrbbecCameraWorker(
            self.hub,
            serial=self.args.serial,
            camera_id="head",
            width=self.args.width,
            height=self.args.height,
            fps=self.args.fps,
            jpeg_quality=self.args.jpeg_quality,
        )

    def acquire(self) -> dict:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return {"ok": True, "camera_held": True, "changed": False, "notice": "already holding camera"}
            self._worker = self._make_worker()
            with self.hub.lock:
                # Optimistic held flag; real Orbbec worker confirms after pipeline start.
                self.hub.meta["camera_held"] = True
                self.hub.meta.pop("camera_error", None)
                self.hub.meta["notice"] = (
                    "Orbbec held by monitor preview; use 释放摄像头 before exclusive vision capture"
                )
            self._worker.start()
            return {"ok": True, "camera_held": True, "changed": True, "notice": "camera acquired for preview"}

    def release(self) -> dict:
        with self._lock:
            worker = self._worker
            self._worker = None
            if worker is None:
                with self.hub.lock:
                    self.hub.meta["camera_held"] = False
                    self.hub.meta["notice"] = "camera already released; safe for exclusive vision capture"
                self.hub.set_frame(FramePacket(
                    b"", 0, 0, time.monotonic(), "head", "released", "camera released",
                ))
                return {"ok": True, "camera_held": False, "changed": False, "notice": "already released"}
            worker.stop()
            if hasattr(worker, "wait_released"):
                worker.wait_released(5.0)
            else:
                worker.join(timeout=5.0)
            time.sleep(0.4)
            with self.hub.lock:
                self.hub.meta["camera_held"] = False
                self.hub.meta.pop("camera_error", None)
                self.hub.meta["notice"] = "camera released; re-acquire when preview needed"
            self.hub.set_frame(FramePacket(
                b"", 0, 0, time.monotonic(), "head", "released", "camera released for other tools",
            ))
            return {"ok": True, "camera_held": False, "changed": True, "notice": "camera released"}


class ArmWorkerManager:
    """Pause readonly arm polling while a control session owns CAN."""

    def __init__(self, hub: MonitorHub, args):
        self.hub = hub
        self.args = args
        self._lock = threading.Lock()
        self._workers: list = []

    def start(self) -> None:
        with self._lock:
            if self._workers:
                return
            self._workers = build_arm_workers(self.args, self.hub)
            for worker in self._workers:
                worker.start()

    def stop(self) -> None:
        with self._lock:
            workers = self._workers
            self._workers = []
            for worker in workers:
                worker.stop()
            for worker in workers:
                worker.join(timeout=2.0)
            time.sleep(0.2)


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, hub, camera, arms: ArmWorkerManager, control: JointController):
        super().__init__(address, MonitorHandler)
        self.hub = hub
        self.camera = camera
        self.arms = arms
        self.control = control
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class MonitorHandler(BaseHTTPRequestHandler):
    server: MonitorServer

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _json(self, payload: dict, code: int = 200):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return self._send(code, body, "application/json; charset=utf-8")

    def _file(self, path: Path, content_type: str):
        if not path.is_file():
            return self._send(404, b"missing static asset", "text/plain; charset=utf-8")
        return self._send(200, path.read_bytes(), content_type)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            return self._file(target, ctype)
        if path == "/api/health":
            return self._json({
                "ok": True,
                "service": "brick-stacking-host-monitor",
                "started_at": self.server.started_at,
                "motion_enabled": self.server.control.motion_process_enabled,
                "camera_held": self.server.camera.held,
                "control_session": self.server.control.snapshot()["session_open"],
                "scope": "camera_joint_monitor_optional_single_joint_control",
            })
        if path == "/api/state":
            snap = self.server.hub.snapshot()
            snap["meta"]["camera_held"] = self.server.camera.held
            snap["meta"]["motion_enabled"] = self.server.control.motion_process_enabled
            snap["control"] = self.server.control.snapshot()
            return self._json(snap)
        if path == "/api/control/status":
            return self._json(self.server.control.snapshot())
        if path.startswith("/stream/"):
            return self._mjpeg(path.split("/", 2)[-1])
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except json.JSONDecodeError:
            return self._json({"ok": False, "error": "invalid JSON"}, 400)

        try:
            if path == "/api/camera/release":
                return self._json(self.server.camera.release())
            if path == "/api/camera/acquire":
                return self._json(self.server.camera.acquire())
            if path == "/api/control/session/open":
                return self._json(self.server.control.open_session(str(body.get("confirm", ""))))
            if path == "/api/control/session/close":
                return self._json(self.server.control.close_session())
            if path == "/api/control/joint/prepare":
                return self._json(self.server.control.prepare(
                    int(body["joint"]),
                    step_deg=body.get("step_deg"),
                    direction=int(body.get("direction", 0)),
                ))
            if path == "/api/control/joint/enable":
                return self._json(self.server.control.enable(int(body["joint"]), str(body.get("confirm", ""))))
            if path == "/api/control/joint/move":
                return self._json(self.server.control.move(int(body["joint"]), str(body.get("confirm", ""))))
            if path == "/api/control/joint/release":
                return self._json(self.server.control.release(int(body["joint"]), str(body.get("confirm", ""))))
        except KeyError as exc:
            return self._json({"ok": False, "error": f"missing field: {exc}"}, 400)
        except (ValueError, RuntimeError) as exc:
            return self._json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def _mjpeg(self, camera_id: str):
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            while True:
                packet = self.server.hub.get_jpeg(camera_id)
                if packet is None or not packet.jpeg:
                    time.sleep(0.2)
                    continue
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(packet.jpeg)}\r\n\r\n".encode())
                self.wfile.write(packet.jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            return


def build_arm_workers(args, hub: MonitorHub) -> list:
    workers = []
    if args.mock:
        if args.arms in {"left", "both"}:
            workers.append(MockArmWorker(hub, "left"))
        if args.arms in {"right", "both"}:
            workers.append(MockArmWorker(hub, "right"))
        return workers
    if args.arms in {"left", "both"}:
        workers.append(ArmReaderWorker(hub, *LEFT_ARM, period_s=args.arm_period))
    if args.arms in {"right", "both"}:
        workers.append(ArmReaderWorker(hub, *RIGHT_ARM, period_s=args.arm_period))
    return workers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--serial", default=HEAD_SERIAL_DEFAULT)
    parser.add_argument("--arms", choices=("none", "left", "right", "both"), default="left")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--jpeg-quality", type=int, default=75)
    parser.add_argument("--arm-period", type=float, default=0.15)
    parser.add_argument("--start-released", action="store_true")
    parser.add_argument(
        "--enable-motion",
        action="store_true",
        help="expose single-joint control APIs (still needs READY/ENABLE/MOVE/RELEASE confirms)",
    )
    parser.add_argument(
        "--linkerbot-src",
        default="/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src",
        help="path containing linkerbot package",
    )
    args = parser.parse_args(argv)

    if not 1 <= args.port <= 65535:
        parser.error("invalid port")

    repo = ROOT.parents[1]
    src = repo / "src"
    for path in (str(src), str(ROOT), args.linkerbot_src):
        if path and path not in sys.path:
            sys.path.insert(0, path)

    hub = MonitorHub()
    hub.meta.update(
        mode="mock" if args.mock else "real",
        serial=args.serial,
        arms=args.arms,
        motion_enabled=bool(args.enable_motion),
        camera_held=False,
        notice="use 释放摄像头 before exclusive vision capture",
    )

    arms = ArmWorkerManager(hub, args)
    arms.start()

    control = JointController(motion_process_enabled=bool(args.enable_motion), mock=bool(args.mock))
    control.set_hooks(on_open=arms.stop, on_close=arms.start)

    camera = CameraController(hub, args)
    if not args.start_released:
        camera.acquire()

    server = MonitorServer((args.bind, args.port), hub, camera, arms, control)
    print(json.dumps({
        "service": "brick-stacking-host-monitor",
        "url": f"http://{args.bind}:{args.port}/",
        "mode": "mock" if args.mock else "real",
        "motion_enabled": bool(args.enable_motion),
        "camera_held": camera.held,
        "cameras": ["head"],
        "arms": args.arms,
        "camera_api": ["/api/camera/release", "/api/camera/acquire"],
        "control_api": [
            "/api/control/session/open",
            "/api/control/joint/prepare",
            "/api/control/joint/enable",
            "/api/control/joint/move",
            "/api/control/joint/release",
            "/api/control/session/close",
        ],
    }, ensure_ascii=False))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("shutting down", file=sys.stderr)
    finally:
        try:
            control.close_session()
        except Exception:  # noqa: BLE001
            pass
        camera.release()
        arms.stop()
        server.server_close()
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
