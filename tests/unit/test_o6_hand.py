from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from brick_stacking.hardware import o6_hand
from brick_stacking.hardware.mock_devices import MockHand
from brick_stacking.hardware.o6_hand import O6Binding, O6HandAdapter


CONFIG = Path(__file__).resolve().parents[2] / "config/hand/o6_observed.json"


@pytest.fixture
def sdk(monkeypatch):
    calls = []
    payload = SimpleNamespace(
        serial="LHO6-04-276-R-Z-1-D", stamp=101.0, values=[0, 20, 40, 60, 80, 100]
    )

    def call(name, result=None):
        calls.append(name)
        return result

    def open_sdk(**kwargs):
        call(("open", kwargs))
        return SimpleNamespace(
            stop_polling=lambda: call("stop_polling"),
            close=lambda: call("close"),
            version=SimpleNamespace(
                get_device_info=lambda: call("identity", SimpleNamespace(serial_number=payload.serial))
            ),
            angle=SimpleNamespace(
                get_angle_mapping=lambda: call("mapping", [[0, 255]] * 6),
                get_blocking=lambda *, timeout_ms: call(
                    ("read", timeout_ms),
                    SimpleNamespace(
                        timestamp=payload.stamp,
                        angles=SimpleNamespace(to_list=lambda: payload.values),
                    ),
                ),
            ),
        )

    monkeypatch.setitem(sys.modules, "linkerbot", SimpleNamespace(O6=open_sdk))
    monkeypatch.setattr(o6_hand, "version", lambda _: "0.5.4")
    monkeypatch.setattr(
        o6_hand, "time",
        SimpleNamespace(time=iter((100.0, 102.0, 103.0, 104.0)).__next__, monotonic=lambda: 25.0),
    )
    return calls, payload


@pytest.mark.parametrize(
    ("role", "channel", "can_id", "serial"),
    [
        ("right", "can0", 0x27, "LHO6-04-276-R-Z-1-D"),
        ("left", "can1", 0x28, "LHO6-04-322-L-Z-1-D"),
    ],
)
def test_o6_read_only_session(sdk, role, channel, can_id, serial):
    calls, payload = sdk
    payload.serial = serial
    binding = O6Binding.load(CONFIG, role)
    assert binding.can_id == can_id
    with O6HandAdapter.open(binding) as hand:
        state = hand.read_hand_state()
        assert state["source"] == "real"
        assert state["role"] == role and state["hand_sn"] == serial
        assert state["raw_u8"] is None and state["percent"] == tuple(payload.values)
        assert state["device_stamp"] is None and state["host_receive_stamp"] == 25.0
        assert not any(state[key] for key in ("fault_valid", "temperature_valid", "tactile_valid"))
        with pytest.raises(ValueError, match="stale"):
            hand.read_hand_state()
    with pytest.raises(RuntimeError, match="closed"):
        hand.read_hand_state()
    assert calls == [
        ("open", {"side": role, "interface_name": channel}), "stop_polling",
        "identity", "mapping", ("read", 500), ("read", 500), "close",
    ]


def test_wrong_serial_closes_before_angle_read(sdk):
    calls, payload = sdk
    payload.serial = "LHO6-04-322-L-Z-1-D"
    with pytest.raises(ValueError, match="serial mismatch"):
        with O6HandAdapter.open(O6Binding.load(CONFIG, "right")):
            pytest.fail("wrong hand was accepted")
    assert calls[1:] == ["stop_polling", "identity", "close"]


def test_swapped_can_binding_rejected():
    with pytest.raises(ValueError, match="audited CAN"):
        O6Binding("right", "can1", 0x27, "LHO6-04-276-R-Z-1-D", "test")


def test_invalid_percent_feedback_closes_session(sdk):
    calls, payload = sdk
    payload.values[0] = float("nan")
    with pytest.raises(ValueError, match="percent channels"):
        with O6HandAdapter.open(O6Binding.load(CONFIG, "right")) as hand:
            hand.read_hand_state()
    assert calls[-1] == "close"


def test_mock_reports_raw_and_preserves_preset_interface():
    hand = MockHand(role="right", raw_u8=(0, 1, 2, 3, 4, 255))
    hand.simulate_preset("MOCK_OPEN")
    assert hand.get_state()["preset"] == "MOCK_OPEN"
    state = hand.read_hand_state()
    assert state["role"] == "right" and state["source"] == "mock"
    assert state["raw_u8"] == (0, 1, 2, 3, 4, 255) and "percent" not in state
    with pytest.raises(ValueError, match="raw_u8"):
        MockHand(raw_u8=(0, 1, 2, 3, 4, 256))
