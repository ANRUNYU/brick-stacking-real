"""Manual teach panel. Default mock. Live reads the left arm and can command the hand.

Arm path is get_angles() only: no enable, no move_j, no move_l, no rest.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from brick_stacking.manual_teach.session import TeachSession  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_OUT = ROOT / "docs" / "team" / "B" / "evidence" / "line_h"


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def make_handler(session: TeachSession):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def handle(self) -> None:
            # Keep the browser poll on one socket. A new connection every
            # 100 ms piles up TIME_WAIT on Windows and eventually stalls.
            self.close_connection = True
            try:
                self.handle_one_request()
                while not self.close_connection:
                    self.handle_one_request()
            except Exception:
                return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path in ("/", "/index.html"):
                    self._static("index.html")
                    return
                if path.startswith("/static/"):
                    self._static(path[len("/static/") :])
                    return
                if path == "/api/health":
                    _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "service": "manual-teach",
                            "mock": session.mock,
                            "enable_hand": session.enable_hand,
                        },
                    )
                    return
                if path == "/api/state":
                    _json(self, 200, session.snapshot())
                    return
                _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                _json(self, 500, {"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=3)})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                body = _read_json(self)
                confirm = str(body.get("confirm", ""))
                if path == "/api/session/open":
                    _json(self, 200, session.open_session(confirm))
                    return
                if path == "/api/record/start":
                    if confirm != "START":
                        raise ValueError('confirm must be "START"')
                    _json(self, 200, session.record_start())
                    return
                if path == "/api/record/pause":
                    if confirm != "PAUSE":
                        raise ValueError('confirm must be "PAUSE"')
                    _json(self, 200, session.record_pause())
                    return
                if path == "/api/record/end":
                    if confirm != "END":
                        raise ValueError('confirm must be "END"')
                    _json(self, 200, session.record_end())
                    return
                if path == "/api/hand/grasp":
                    if confirm != "GRASP":
                        raise ValueError('confirm must be "GRASP"')
                    speed = body.get("speed_percent")
                    _json(self, 200, session.apply_preset("grasp", None if speed is None else float(speed)))
                    return
                if path == "/api/hand/release":
                    if confirm != "RELEASE":
                        raise ValueError('confirm must be "RELEASE"')
                    speed = body.get("speed_percent")
                    _json(
                        self,
                        200,
                        session.apply_preset("release", None if speed is None else float(speed)),
                    )
                    return
                _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                _json(self, 400, {"ok": False, "error": str(exc)})

        def _static(self, rel: str) -> None:
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
                _json(self, 404, {"ok": False, "error": "static_not_found"})
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                ctype = "text/javascript; charset=utf-8"
            elif target.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif target.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Manual teach panel for left arm read + hand grasp/release")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8092)
    p.add_argument("--live", action="store_true", help="read P7 on can2 and O6 on can1 on this machine")
    p.add_argument("--enable-hand", action="store_true", help="allow grasp/release on a local hand")
    p.add_argument("--hand-url", default="", help="live hand teach base, e.g. http://10.157.173.135:8091")
    p.add_argument("--arm-url", default="", help="read-only arm angles base, e.g. http://10.157.173.135:8094")
    p.add_argument("--max-speed-percent", type=float, default=15.0)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory for teach_NN_*.jsonl")
    p.add_argument(
        "--linkerbot-src",
        default="/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src",
    )
    args = p.parse_args(argv)
    linker = Path(args.linkerbot_src)
    if args.live and linker.is_dir() and str(linker) not in sys.path:
        sys.path.insert(0, str(linker))
    remote = bool(args.hand_url or args.arm_url)
    session = TeachSession(
        args.out,
        mock=not args.live and not remote,
        enable_hand=args.enable_hand,
        max_speed_percent=args.max_speed_percent,
        repo_root=ROOT,
        hand_url=args.hand_url,
        arm_url=args.arm_url,
    )
    try:
        session.start_background()
    except Exception as exc:
        print(f"manual-teach failed to open devices: {exc}", file=sys.stderr)
        session.shutdown()
        return 1
    handler = make_handler(session)
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    if args.hand_url or args.arm_url:
        mode = f"REMOTE hand={args.hand_url or '-'} arm={args.arm_url or '-'}"
    elif args.live:
        mode = "LIVE"
    else:
        mode = "MOCK"
    hand = "HAND" if session.enable_hand else "HAND_OFF"
    print(
        f"manual-teach listening on http://{args.bind}:{args.port}/ mode={mode} {hand} out={args.out}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
