"""Explicitly opened, read-only adapter for the audited Linkerbot O6 SDK."""

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import version
import json
import math
from pathlib import Path
from threading import Lock
import time
from typing import cast
from uuid import uuid4

from brick_stacking.contracts import HandPercentChannels, HandRole, HandState


@dataclass(frozen=True)
class O6Binding:
    role: HandRole
    channel: str
    can_id: int
    serial_number: str
    config_hash: str

    @classmethod
    def load(cls, path: str | Path, role: HandRole) -> "O6Binding":
        if role not in ("left", "right"):
            raise ValueError("select left or right explicitly")
        content = Path(path).read_bytes()
        row = json.loads(content)[role]
        return cls(role=role, config_hash=sha256(content).hexdigest(), **row)

    def __post_init__(self):
        endpoints = {"right": ("can0", 0x27, "R"), "left": ("can1", 0x28, "L")}
        if self.role not in endpoints:
            raise ValueError("select left or right explicitly")
        channel, can_id, side = endpoints[self.role]
        serial_parts = self.serial_number.split("-")
        if ((self.channel, self.can_id) != (channel, can_id)
                or serial_parts[0] != "LHO6" or serial_parts[3:4] != [side]):
            raise ValueError("O6 side, serial and audited CAN endpoint must agree")


class O6HandAdapter:
    """Read six percent channels from a session whose serial has been checked."""

    def __init__(self, binding: O6Binding, hand, mapping_version: str):
        self.binding = binding
        self._hand = hand
        self._mapping_version = mapping_version
        self._epoch = uuid4().hex
        self._last_sdk_stamp = -math.inf
        self._lock = Lock()

    @classmethod
    @contextmanager
    def open(cls, binding: O6Binding):
        """Open only on explicit request, using the SDK version reviewed in the audit."""
        if version("linkerbot") != "0.5.4":
            raise RuntimeError("D1-02 requires the audited Linkerbot SDK 0.5.4")
        from linkerbot import O6

        hand = O6(side=binding.role, interface_name=binding.channel)
        try:
            # This stops SDK sensor polling. It is not a physical stop.
            hand.stop_polling()
            serial = hand.version.get_device_info().serial_number
            if serial != binding.serial_number:
                raise ValueError(f"O6 serial mismatch on {binding.channel}: {serial!r}")
            mapping = json.dumps(hand.angle.get_angle_mapping(), separators=(",", ":"))
            adapter = cls(binding, hand, sha256(mapping.encode()).hexdigest())
            try:
                yield adapter
            finally:
                with adapter._lock:
                    adapter._hand = None
        finally:
            hand.close()

    def read_hand_state(self) -> HandState:
        with self._lock:
            if self._hand is None:
                raise RuntimeError("O6 read session is closed")
            started = time.time()
            data = self._hand.angle.get_blocking(timeout_ms=500)
            received = time.monotonic()
            stamp = data.timestamp
            # The SDK timestamp is Unix host time. It is not a device timestamp.
            if not (started <= stamp <= time.time() and stamp > self._last_sdk_stamp):
                raise ValueError("O6 angle feedback is stale or has an invalid timestamp")
            values = tuple(data.angles.to_list())
            if len(values) != 6 or any(
                type(value) not in (int, float) or not 0 <= value <= 100 for value in values
            ):
                raise ValueError("O6 requires six finite percent channels in [0, 100]")
            self._last_sdk_stamp = stamp
            return {
                "sample_id": uuid4().hex,
                "source": "real",
                "device_id": self.binding.serial_number,
                "frame_id": f"{self.binding.role}_hand",
                "device_stamp": None,
                "host_receive_stamp": received,
                "clock_domain": "host_monotonic",
                "epoch": self._epoch,
                "validity": "VALID",
                "reason": None,
                "role": self.binding.role,
                "hand_sn": self.binding.serial_number,
                "raw_u8": None,
                "percent": cast(HandPercentChannels, values),
                "mapping_version": self._mapping_version,
                "fault_valid": False,
                "temperature_valid": False,
                "tactile_valid": False,
            }
