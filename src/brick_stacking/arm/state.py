"""Read the audited P7 endpoints without constructing a motor or arm SDK object."""

from contextlib import contextmanager
import math
import struct
import subprocess
from threading import Lock
import time
from uuid import uuid4

from brick_stacking.contracts import ArmState, JointName

JOINTS: tuple[JointName, ...] = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")
ENDPOINTS = {
    "left": ("can2", "pci-0000:00:14.0-usb-0:6.3.3:1.0", (61, 62, 63, 64, 65, 66, 67)),
    "right": ("can3", "pci-0000:00:14.0-usb-0:6.3.4:1.0", (51, 52, 53, 54, 55, 56, 57)),
}
POSITION_READ = b"\x06"
MODE_READ = bytes.fromhex("670b000000000476")
TIMEOUT_S = 0.25


def _physical_path(channel: str) -> str | None:
    result = subprocess.run(
        ["udevadm", "info", "--query=property", f"--path=/sys/class/net/{channel}"],
        check=True, capture_output=True, text=True, timeout=2,
    )
    return next((line[8:] for line in result.stdout.splitlines() if line.startswith("ID_PATH=")), None)


class ArmStateReader:
    def __init__(self, role: str, channel: str, ids: tuple[int, ...], bus, message):
        self._role = role
        self._channel = channel
        self._ids = ids
        self._bus = bus
        self._message = message
        self._epoch = uuid4().hex
        self._lock = Lock()

    @classmethod
    @contextmanager
    def open(cls, role: str, channel: str):
        """Bind by explicit role, audited interface/USB path and all seven replies."""
        if role not in ENDPOINTS:
            raise ValueError("select left or right explicitly")
        expected_channel, path, ids = ENDPOINTS[role]
        if channel != expected_channel or _physical_path(channel) != path:
            raise ValueError(f"{role} arm does not match the audited CAN interface and USB path")

        import can

        with can.Bus(interface="socketcan", channel=channel, ignore_config=True,
                     receive_own_messages=False, fd=False) as bus:
            reader = cls(role, channel, ids, bus, can.Message)
            try:
                for index, motor_id in enumerate(ids):
                    try:
                        if index < 5:
                            reader._position(motor_id)
                        else:
                            reader._query(0x600 + motor_id, MODE_READ, bytes((motor_id, 0x0B)), 8)
                    except (TimeoutError, ValueError) as exc:
                        raise ValueError(f"cannot bind {role} arm: J{index + 1} ID {motor_id}: {exc}") from exc
                yield reader
            finally:
                with reader._lock:
                    reader._bus = None

    def _query(self, can_id: int, request: bytes, prefix: bytes, size: int) -> bytes:
        started = time.time()
        deadline = time.monotonic() + TIMEOUT_S
        self._bus.send(self._message(arbitration_id=can_id, data=request, is_extended_id=False),
                       timeout=TIMEOUT_S)
        while (remaining := deadline - time.monotonic()) > 0:
            frame = self._bus.recv(remaining)
            if frame is None:
                break
            if (frame.arbitration_id == can_id and not frame.is_extended_id
                    and not frame.is_remote_frame and not frame.is_error_frame and not frame.is_fd
                    and started <= frame.timestamp <= time.time()
                    and len(frame.data) == size and frame.data.startswith(prefix)):
                return bytes(frame.data)
        raise TimeoutError("no matching fresh reply")

    def _position(self, motor_id: int) -> float:
        reply = self._query(motor_id, POSITION_READ, POSITION_READ, 5)
        position, = struct.unpack("<f", reply[1:])
        if not math.isfinite(position):
            raise ValueError("non-finite position")
        return position

    def read_state(self) -> ArmState:
        with self._lock:
            if self._bus is None:
                raise RuntimeError("arm read session is closed")
            positions: list[float | None] = []
            failures = []
            for joint, motor_id in zip(JOINTS[:5], self._ids[:5], strict=True):
                try:
                    positions.append(self._position(motor_id))
                except (TimeoutError, ValueError) as exc:
                    positions.append(None)
                    failures.append(f"{joint}: {exc}")
            positions.extend((None, None))
            failures.append("J6/J7: no audited read-only position query")
            # Shared VALID rule: seven finite q_rad required. Until an audited
            # J6/J7 read-only position query exists, samples stay INVALID.
            from brick_stacking.arm.arm_state_validity import assign_validity_from_joints

            validity, reason = assign_validity_from_joints(
                positions=positions, failures=failures
            )
            return {
                "sample_id": uuid4().hex,
                "source": "real",
                "device_id": f"{self._channel}:{','.join(map(str, self._ids))}",
                "frame_id": f"{self._role}_arm_base",
                "device_stamp": None,
                "host_receive_stamp": time.monotonic(),
                "clock_domain": "host_monotonic",
                "epoch": self._epoch,
                "validity": validity,
                "reason": reason,
                "joint_names": JOINTS,
                "joint_bindings": {
                    joint: {"sdk_index": index, "device_joint_id": str(motor_id)}
                    for index, (joint, motor_id) in enumerate(zip(JOINTS, self._ids, strict=True))
                },
                "q_rad": tuple(positions),
                "dq_rad_s": None,
                "enabled": None,
                "fault": None,
            }
