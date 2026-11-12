#!/usr/bin/env python3
"""Read-only left-arm angles for the teach panel.

Opens P7 on can2 and serves the latest get_angles(). Does not enable,
move, or rest the arm.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only P7 get_angles() HTTP")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8094)
    p.add_argument("--side", default="left")
    p.add_argument("--interface", default="can2")
    args = p.parse_args()

    from linkerbot import P7

    arm = P7(side=args.side, interface_name=args.interface)
    lock = threading.Lock()
    state = {"q_rad": None, "mono": None, "error": None, "reads": 0, "read_hz": None}
    stop = threading.Event()

    def loop() -> None:
        last_mark = time.perf_counter()
        mark_reads = 0
        while not stop.is_set():
            started = time.perf_counter()
            try:
                q = [float(v) for v in arm.get_angles()]
                now = time.monotonic()
                with lock:
                    state["q_rad"] = q
                    state["mono"] = now
                    state["error"] = None
                    state["reads"] += 1
                    mark_reads += 1
            except Exception as exc:
                with lock:
                    state["error"] = f"{type(exc).__name__}: {exc}"
                time.sleep(0.05)
                continue
            elapsed = time.perf_counter() - started
            if elapsed < 0.008:
                time.sleep(0.008 - elapsed)
            span = time.perf_counter() - last_mark
            if span >= 1.0:
                with lock:
                    state["read_hz"] = round(mark_reads / span, 1)
                mark_reads = 0
                last_mark = time.perf_counter()

    threading.Thread(target=loop, name="arm-read", daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path not in ("/api/q", "/api/health"):
                self.send_error(404)
                return
            with lock:
                age = None if state["mono"] is None else round(time.monotonic() - state["mono"], 4)
                body = {
                    "ok": state["q_rad"] is not None and not state["error"],
                    "q_rad": state["q_rad"],
                    "age_s": age,
                    "reads": state["reads"],
                    "read_hz": state["read_hz"],
                    "error": state["error"],
                    "arm_motion_commanded": False,
                }
            raw = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"arm-angle-readonly http://{args.bind}:{args.port}/api/q", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        try:
            arm.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
