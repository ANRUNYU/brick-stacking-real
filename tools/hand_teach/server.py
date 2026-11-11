"""LAN Hand Teach UI for left O6. Default read-only; --enable-hand for APPLY.

No arm construction / enable / move.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hand_backend import HandTeachBackend  # noqa: E402


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def make_handler(backend: HandTeachBackend):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
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
                        "service": "hand-teach",
                        "enable_hand": backend.enable_hand,
                        "side": "left",
                    },
                )
                return
            if path == "/api/state":
                _json(self, 200, {"ok": True, "state": backend.snapshot()})
                return
            _json(self, 404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                body = _read_json(self)
                if path == "/api/session/open":
                    state = backend.open_session(str(body.get("confirm", "")))
                    _json(self, 200, {"ok": True, "state": state})
                    return
                if path == "/api/session/close":
                    state = backend.close_session()
                    _json(self, 200, {"ok": True, "state": state})
                    return
                if path == "/api/apply":
                    result = backend.apply(
                        angles_percent=list(body.get("angles_percent") or []),
                        speed_percent=float(body.get("speed_percent", 10)),
                        confirm=str(body.get("confirm", "")),
                    )
                    _json(self, 200, result)
                    return
                _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                _json(
                    self,
                    400,
                    {
                        "ok": False,
                        "error": str(exc),
                        "traceback": traceback.format_exc(limit=3),
                    },
                )

        def _static(self, rel: str) -> None:
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
                _json(self, 404, {"ok": False, "error": "static_not_found"})
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8091)
    p.add_argument("--enable-hand", action="store_true")
    p.add_argument("--max-speed-percent", type=float, default=15.0)
    p.add_argument("--poll-hz", type=float, default=5.0)
    p.add_argument(
        "--linkerbot-src",
        default="/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src",
    )
    args = p.parse_args()
    linker = Path(args.linkerbot_src)
    if linker.is_dir() and str(linker) not in sys.path:
        sys.path.insert(0, str(linker))

    backend = HandTeachBackend(
        enable_hand=args.enable_hand,
        max_speed_percent=args.max_speed_percent,
        poll_hz=args.poll_hz,
    )
    backend.start()
    handler = make_handler(backend)
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    mode = "ENABLE_HAND" if args.enable_hand else "READ_ONLY"
    print(f"hand-teach listening on http://{args.bind}:{args.port}/ mode={mode}", flush=True)
    try:
        server.serve_forever()
    finally:
        backend.stop()
        server.server_close()


if __name__ == "__main__":
    main()
