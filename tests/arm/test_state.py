import struct
import sys
import time
from types import SimpleNamespace

import pytest

from brick_stacking.arm import state


class FakeBus:
    def __init__(self):
        self.sent = []
        self.reply = None
        self.bad_id = None
        self.bad_kind = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def send(self, frame, timeout):
        can_id, data = frame.arbitration_id, frame.data
        assert not frame.is_extended_id and 0 < timeout <= 0.25
        self.sent.append((can_id, data))
        if data == b"\x06":
            position = -0.125 * (can_id % 10)
            if can_id == self.bad_id and self.bad_kind == "nonfinite":
                position = float("nan")
            payload = b"\x06" + struct.pack("<f", position)
        else:
            assert data == bytes.fromhex("670b000000000476")
            payload = bytes((can_id - 0x600,)) + bytes.fromhex("0b0200000000ff")
        self.reply = SimpleNamespace(
            arbitration_id=can_id, data=payload, timestamp=time.time(),
            is_extended_id=False, is_remote_frame=False, is_error_frame=False, is_fd=False,
        )
        if can_id == self.bad_id:
            if self.bad_kind == "wrong-id":
                self.reply.arbitration_id += 1
            elif self.bad_kind == "wrong-motor":
                self.reply.data = b"\x00" + payload[1:]
            elif self.bad_kind == "stale":
                self.reply.timestamp -= 1

    def recv(self, timeout):
        assert 0 < timeout <= 0.25
        reply, self.reply = self.reply, None
        return reply


@pytest.fixture
def transport(monkeypatch):
    bus = FakeBus()
    opens = []

    def open_bus(**options):
        opens.append(options)
        return bus

    monkeypatch.setattr(state, "_physical_path", lambda channel: {
        "can2": "pci-0000:00:14.0-usb-0:6.3.3:1.0",
        "can3": "pci-0000:00:14.0-usb-0:6.3.4:1.0",
    }[channel])
    monkeypatch.setitem(sys.modules, "can", SimpleNamespace(Bus=open_bus, Message=SimpleNamespace))
    return bus, opens


@pytest.mark.parametrize(("role", "channel", "first"), [("left", "can2", 61), ("right", "can3", 51)])
def test_bind_and_read_send_only_audited_requests(transport, role, channel, first):
    bus, opens = transport
    with state.ArmStateReader.open(role, channel) as reader:
        before = time.monotonic()
        sample = reader.read_state()
        assert before <= sample["host_receive_stamp"] <= time.monotonic()
        second = reader.read_state()
    positions = [(motor_id, b"\x06") for motor_id in range(first, first + 5)]
    modes = [(0x600 + motor_id, bytes.fromhex("670b000000000476")) for motor_id in (first + 5, first + 6)]
    assert bus.sent == positions + modes + positions + positions
    assert opens == [dict(interface="socketcan", channel=channel, ignore_config=True,
                          receive_own_messages=False, fd=False)]
    assert sample["joint_names"] == tuple(f"J{i}" for i in range(1, 8))
    assert list(sample["joint_bindings"].values()) == [
        {"sdk_index": i, "device_joint_id": str(first + i)} for i in range(7)
    ]
    assert sample["q_rad"] == (-0.125, -0.25, -0.375, -0.5, -0.625, None, None)
    assert sample["validity"] == "INVALID" and "J6/J7" in sample["reason"]
    assert sample["device_stamp"] is sample["enabled"] is sample["fault"] is sample["dq_rad_s"] is None
    assert sample["clock_domain"] == "host_monotonic"
    assert sample["epoch"] == second["epoch"] and sample["sample_id"] != second["sample_id"]
    assert bus.closed
    with pytest.raises(RuntimeError, match="closed"):
        reader.read_state()


def test_wrong_interface_or_usb_path_never_opens_bus(transport, monkeypatch):
    bus, opens = transport
    with pytest.raises(ValueError, match="audited CAN interface"):
        with state.ArmStateReader.open("left", "can3"):
            pytest.fail("unexpected binding")
    monkeypatch.setattr(state, "_physical_path", lambda _: "different-usb-path")
    with pytest.raises(ValueError, match="USB path"):
        with state.ArmStateReader.open("left", "can2"):
            pytest.fail("unexpected binding")
    assert not opens and not bus.sent


@pytest.mark.parametrize(("can_id", "kind"), [(61, "wrong-id"), (0x600 + 66, "wrong-motor"), (62, "stale")])
def test_wrong_or_stale_reply_prevents_binding(transport, can_id, kind):
    bus, _ = transport
    bus.bad_id, bus.bad_kind = can_id, kind
    with pytest.raises(ValueError, match="no matching fresh reply"):
        with state.ArmStateReader.open("left", "can2"):
            pytest.fail("unexpected binding")
    assert bus.closed


@pytest.mark.parametrize("kind", ["wrong-id", "stale", "nonfinite"])
def test_failed_read_never_reuses_previous_angle(transport, kind):
    bus, _ = transport
    with state.ArmStateReader.open("left", "can2") as reader:
        assert reader.read_state()["q_rad"][0] == -0.125
        bus.bad_id, bus.bad_kind = 61, kind
        sample = reader.read_state()
    assert sample["q_rad"] == (None, -0.25, -0.375, -0.5, -0.625, None, None)
    assert sample["validity"] == "INVALID" and "J1" in sample["reason"]
