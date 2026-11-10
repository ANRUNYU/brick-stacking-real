"""LAN web monitor for robot-host camera preview and read-only joint state.

Read-only. No motion enable, trajectory, Flash writes, or P7 SDK construction.
Bind on the robot host (0.0.0.0) so same-LAN collaborators can open the page.

Usage on robot host (vision/control venv with deps):
  cd /path/to/brick-stacking-real
  PYTHONPATH=src python tools/host_monitor/server.py --bind 0.0.0.0 --port 8088 \\
      --serial CP2L863000KL --arms left

Local UI smoke (no hardware):
  PYTHONPATH=src python tools/host_monitor/server.py --mock --bind 127.0.0.1 --port 8088
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

from sources import (  # noqa: E402
    HEAD_SERIAL_DEFAULT,
    LEFT_ARM,
    RIGHT_ARM,
    ArmReaderWorker,
    MockArmWorker,
    MockCameraWorker,
    MonitorHub,
    OrbbecCameraWorker,
)


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, hub: MonitorHub, workers: list):
        super().__init__(address, MonitorHandler)
        self.hub = hub
        self.workers = workers
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class MonitorHandler(BaseHTTPRequestHandler):
    server: MonitorServer

    def log_message(self, fmt, *args):  # quieter default access log
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

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
            payload = {
                "ok": True,
                "service": "brick-stacking-host-monitor",
                "started_at": self.server.started_at,
                "motion_enabled": False,
                "scope": "read_only_camera_and_joint_monitor",
            }
            return self._json(payload)
        if path == "/api/state":
            return self._json(self.server.hub.snapshot())
        if path.startswith("/stream/"):
            cam_id = path.split("/", 2)[-1]
            return self._mjpeg(cam_id)
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def _file(self, path: Path, content_type: str):
        if not path.is_file():
            return self._send(404, b"missing static asset", "text/plain; charset=utf-8")
        return self._send(200, path.read_bytes(), content_type)

    def _json(self, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return self._send(200, body, "application/json; charset=utf-8")

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
                    time.sleep(0.05)
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(packet.jpeg)}\r\n\r\n".encode())
                self.wfile.write(packet.jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            return


def build_workers(args, hub: MonitorHub) -> list:
    workers = []
    if args.mock:
        workers.append(MockCameraWorker(hub, "head", fps=8))
        if args.arms in {"left", "both"}:
            workers.append(MockArmWorker(hub, "left"))
        if args.arms in {"right", "both"}:
            workers.append(MockArmWorker(hub, "right"))
        hub.meta.update(mode="mock", notice="UI smoke only; not robot hardware")
        return workers

    workers.append(OrbbecCameraWorker(
        hub, serial=args.serial, camera_id="head",
        width=args.width, height=args.height, fps=args.fps, jpeg_quality=args.jpeg_quality,
    ))
    if args.arms in {"left", "both"}:
        workers.append(ArmReaderWorker(hub, *LEFT_ARM, period_s=args.arm_period))
    if args.arms in {"right", "both"}:
        workers.append(ArmReaderWorker(hub, *RIGHT_ARM, period_s=args.arm_period))
    hub.meta.update(
        mode="real",
        serial=args.serial,
        arms=args.arms,
        notice="Orbbec is exclusively held while this service runs; stop before vision capture jobs",
        motion_enabled=False,
    )
    return workers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0", help="LAN listen address")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--mock", action="store_true", help="no camera/CAN; local UI smoke")
    parser.add_argument("--serial", default=HEAD_SERIAL_DEFAULT, help="head camera SN")
    parser.add_argument("--arms", choices=("none", "left", "right", "both"), default="left")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--jpeg-quality", type=int, default=75)
    parser.add_argument("--arm-period", type=float, default=0.15)
    args = parser.parse_args(argv)

    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    if args.arms != "none" and not args.mock:
        # Ensure package import path for ArmStateReader.
        repo = ROOT.parents[1]
        src = repo / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))

    hub = MonitorHub()
    workers = build_workers(args, hub)
    for worker in workers:
        worker.start()

    server = MonitorServer((args.bind, args.port), hub, workers)
    print(json.dumps({
        "service": "brick-stacking-host-monitor",
        "url": f"http://{args.bind}:{args.port}/",
        "mode": "mock" if args.mock else "real",
        "motion_enabled": False,
        "cameras": ["head"],
        "arms": args.arms,
    }, ensure_ascii=False))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("shutting down", file=sys.stderr)
    finally:
        for worker in workers:
            worker.stop()
        server.server_close()
        # Give workers a moment to release Orbbec/CAN.
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
