"""HTTP client for the live hand teach API and the read-only arm angles."""

from __future__ import annotations

import http.client
import json
import threading
from typing import Any
from urllib.parse import urlparse


class JsonLink:
    """Direct connection. Does not use HTTP_PROXY (that proxy turns the robot into 502)."""

    def __init__(self, base: str, timeout: float = 1.5) -> None:
        parsed = urlparse(base)
        if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
            raise ValueError(f"need http://host:port, got {base}")
        self.base = base.rstrip("/")
        self.host = parsed.hostname
        self.port = int(parsed.port)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._conn: http.client.HTTPConnection | None = None

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path, None)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, body)

    def request(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Connection": "keep-alive", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        last_error: Exception | None = None
        with self._lock:
            for attempt in (1, 2):
                try:
                    conn = self._connection()
                    conn.request(method, path, body=payload, headers=headers)
                    resp = conn.getresponse()
                    raw = resp.read()
                    if resp.status >= 400:
                        detail = raw.decode("utf-8", "replace")[:300]
                        try:
                            parsed = json.loads(detail)
                            detail = str(parsed.get("error") or detail)
                        except json.JSONDecodeError:
                            pass
                        raise RuntimeError(detail or f"HTTP {resp.status}")
                    data = json.loads(raw.decode("utf-8"))
                    if not isinstance(data, dict):
                        raise RuntimeError("JSON object required")
                    return data
                except Exception as exc:
                    last_error = exc
                    self._drop()
                    if attempt == 2:
                        break
            assert last_error is not None
            raise last_error

    def close(self) -> None:
        with self._lock:
            self._drop()

    def _connection(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        return self._conn

    def _drop(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
