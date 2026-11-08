import importlib.util
from pathlib import Path
import socket
import struct

import pytest


spec = importlib.util.spec_from_file_location('probe', Path(__file__).parents[2] / 'tools/c_left_arm_readonly_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_only_five_left_read_requests():
    for mid in range(61, 66):
        assert probe.CAN_FRAME.unpack(probe.position_request(mid)) == (mid, 1, b'\x06'+b'\0'*7)
    for mid in (51, 60, 66, 67, 68, 0x642):
        with pytest.raises(ValueError):
            probe.position_request(mid)


def test_standard_ids_do_not_subscribe_to_kernel_error_receive_list():
    filters = list(struct.iter_unpack('=II', probe.receive_filters()))
    assert [mid for mid, _ in filters] == list(range(61, 68)) + [0x642, 0x643]
    for mid, mask in filters:
        # CAN_ERR_FLAG changes kernel subscription semantics, rather than
        # simply rejecting frames. This caused the real can2 receive failure.
        assert not mask & 0x20000000
        assert (mid & mask) == (mid & 0x7FF)
        assert ((mid | 0x80000000) & mask) != (mid & mask)
        assert ((mid | 0x40000000) & mask) != (mid & mask)


def test_v2_only_exact_mode_read_and_strict_response():
    for mid in (66, 67):
        frame = probe.v2_mode_request(mid)
        assert probe.CAN_FRAME.unpack(frame) == (0x600+mid, 8, bytes.fromhex('670b000000000476'))
        reply = probe.CAN_FRAME.pack(0x600+mid, 8, bytes([mid, 11, 2, 0, 0, 0, 0, 255]))
        row = probe.decode_received(reply, 0)
        assert row['control_mode'] == 2 and row['position_sdk_rad'] is None
        assert probe.decode_received(reply, socket.MSG_DONTROUTE) is None
        assert probe.decode_received(frame, 0) is None
    with pytest.raises(ValueError):
        probe.v2_mode_request(61)


def test_echo_and_nonstandard_packets_rejected():
    good = probe.CAN_FRAME.pack(61, 5, b'\x06'+struct.pack('<f', .25))
    assert probe.decode_received(good, 0)['position_sdk_rad'] == .25
    assert probe.decode_received(good, socket.MSG_DONTROUTE) is None
    assert probe.decode_received(probe.position_request(61), 0) is None
    for flag in (0x80000000, 0x40000000, 0x20000000):
        assert probe.decode_received(probe.CAN_FRAME.pack(61 | flag, 5, b'\x06'+struct.pack('<f', .25)), 0) is None
    assert probe.decode_received(probe.CAN_FRAME.pack(61, 5, b'\x06'+struct.pack('<f', float('nan'))), 0) is None


def test_v2_is_raw_never_assumed_quantized():
    row = probe.decode_received(probe.CAN_FRAME.pack(66, 8, bytes.fromhex('0180000000000019')), 0)
    assert row['position_sdk_rad'] is None
    assert probe.decode_received(probe.CAN_FRAME.pack(66, 8, b'\xff'*7+b'\xfd'), 0) is None


@pytest.mark.parametrize('timeout,passive', [(0, .5), (2, .5), (.35, -1), (.35, float('nan'))])
def test_invalid_windows_before_socket(timeout, passive):
    with pytest.raises(ValueError):
        probe.capture(timeout, passive)
