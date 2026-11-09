import importlib.util
from pathlib import Path
import sys
import struct

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[2] / ('tools/'+name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.modules.setdefault('c_left_arm_readonly_probe', load('c_left_arm_readonly_probe'))
rest = load('c_left_wrist_rest_capture')


def test_only_exact_rest_for_selected_wrist():
    for mid in (66, 67):
        assert rest.CAN_FRAME.unpack(rest.rest_request(mid)) == (mid, 8, b'\xff'*7+b'\xfd')
    for mid in (51, 57, 61, 65, 68):
        with pytest.raises(ValueError):
            rest.rest_request(mid)


@pytest.mark.parametrize('supported,allowed,ref', [(False, True, 'x'), (True, False, 'x'), (True, True, ''), (1, True, 'x')])
def test_interlock_rejects_before_hardware(supported, allowed, ref):
    with pytest.raises(ValueError):
        rest.capture(supported_wrist=supported, allow_rest=allowed, authorization_ref=ref)


class FakeBus:
    def __init__(self, *, mode=2, fault=0):
        self.mode, self.fault = mode, fault
        self.sent, self.pending = [], []

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def setsockopt(self, *args): pass
    def bind(self, addr): assert addr == ('can2',)
    def setblocking(self, flag): pass
    def settimeout(self, value): pass

    def send(self, frame):
        self.sent.append(frame)
        cid, n, data = rest.CAN_FRAME.unpack(frame)
        if cid in (0x642, 0x643):
            answer = bytes([cid-0x600, 11, self.mode, 0, 0, 0, 0, 255])
        elif cid in (66, 67):
            assert data == b'\xff'*7+b'\xfd'
            answer = bytes([0, 128, 0, 127, 240, 0, self.fault, 25])
        else:
            assert 61 <= cid <= 65 and n == 1 and data[0] == 6
            answer = b'\x06' + struct.pack('<f', .2)
        self.pending.append(rest.CAN_FRAME.pack(cid, len(answer), answer))
        return len(frame)

    def recvmsg(self, size):
        if not self.pending:
            raise BlockingIOError()
        return self.pending.pop(0), [], 0, ('can2',)


def run_fake(monkeypatch, **settings):
    bus = FakeBus(**settings)
    for name, value in [('AF_CAN', 29), ('CAN_RAW', 1), ('SOL_CAN_RAW', 101), ('CAN_RAW_FILTER', 1)]:
        monkeypatch.setattr(rest.socket, name, value, raising=False)
    monkeypatch.setattr(rest.socket, 'socket', lambda *args: bus)
    monkeypatch.setattr(rest, 'host_clock_epoch', lambda: 'linux_boot:synthetic-test')
    result = rest.capture(supported_wrist=True, allow_rest=True, authorization_ref='test-only')
    return bus, result


def test_exact_two_rest_no_restore_and_raw_not_calibration(monkeypatch):
    bus, result = run_fake(monkeypatch)
    assert [x['kind'] for x in result['transmitted']] == ['mode_read']*2+['rest']*2+['angle_read']*5
    assert len(bus.sent) == 9
    assert result['status'] == 'RAW_SEVEN_AXIS_CAPTURED'
    assert result['calibration_sample_valid'] is False
    wrists = [r for r in result['received'] if 'position_raw_u16' in r]
    assert len(wrists) == 2 and all(r['position_sdk_rad'] is None for r in wrists)


def test_bad_mode_sends_no_rest(monkeypatch):
    bus, result = run_fake(monkeypatch, mode=1)
    assert len(bus.sent) == 1
    assert result['status'] == 'INCOMPLETE'


def test_first_wrist_fault_cancels_remaining_rest_and_reads(monkeypatch):
    bus, result = run_fake(monkeypatch, fault=3)
    assert len(bus.sent) == 3
    assert [r['motor_id'] for r in result['transmitted'] if r['kind'] == 'rest'] == [66]
    assert result['status'] == 'INCOMPLETE'
