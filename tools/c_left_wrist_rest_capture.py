"""Explicit supported-wrist Rest capture. This command CHANGES wrist state.

Only left can2; at most one Rest per wrist; no enable/target/zero/Flash write.
Must have fresh现场 authorization and physical wrist support before invocation.
Raw feedback is retained; factory quantization is never silently certified.
"""
import argparse
import json
from pathlib import Path
import socket
import time
import uuid

from c_left_arm_readonly_probe import (
    CAN_FRAME, decode_received, position_request, receive_filters, v2_mode_request,
)


def rest_request(mid):
    if mid not in (66, 67):
        raise ValueError('only left wrist 66/67 may receive Rest')
    return CAN_FRAME.pack(mid, 8, b'\xff'*7 + b'\xfd')


def host_clock_epoch():
    # Monotonic clock is shared within a Linux boot, not within a capture UUID.
    boot_id = str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    return 'linux_boot:' + boot_id


def capture(*, supported_wrist, allow_rest, authorization_ref):
    if supported_wrist is not True or allow_rest is not True or not isinstance(authorization_ref, str) or not authorization_ref.strip():
        raise ValueError('physical support and explicit Rest authorization required')
    r = dict(schema_version='c-left-supported-rest-1', source='real',
             arm_role='left', interface='can2', clock_domain='host_monotonic',
             epoch=host_clock_epoch(), capture_id=str(uuid.uuid4()), authorization_ref=authorization_ref,
             physically_supported_confirmed=True, transmitted=[], received=[],
             calibration_sample_valid=False, status='INCOMPLETE',
             warning='Rest removes holding; no automatic re-enable or restore',
             stamp_semantics='host receive/dequeue time, not device sample time')
    with socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW) as bus:
        bus.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, receive_filters())
        bus.bind(('can2',))
        bus.setblocking(False)
        for _ in range(4096):
            try:
                bus.recvmsg(CAN_FRAME.size)
            except BlockingIOError:
                break
        else:
            raise RuntimeError('busy receive queue; no commands sent')

        def exchange(mid, packet, kind):
            sent_at = time.monotonic()
            if bus.send(packet) != CAN_FRAME.size:
                raise RuntimeError('incomplete CAN send')
            cid, n, data = CAN_FRAME.unpack(packet)
            r['transmitted'].append(dict(motor_id=mid, arbitration_id=cid,
                                          data_hex=data[:n].hex(), kind=kind,
                                          host_send_monotonic_s=sent_at))
            deadline = sent_at + .5
            while time.monotonic() < deadline:
                bus.settimeout(max(.0001, deadline-time.monotonic()))
                try:
                    frame, _, flags, _ = bus.recvmsg(CAN_FRAME.size)
                except socket.timeout:
                    break
                row = decode_received(frame, flags)
                if row is None:
                    continue
                row['host_receive_monotonic_s'] = time.monotonic()
                r['received'].append(row)
                if row['motor_id'] != mid:
                    continue
                if kind == 'mode_read' and 'control_mode' in row:
                    return row
                if kind == 'rest' and 'status' in row:
                    return row
                if kind == 'angle_read' and row.get('position_sdk_rad') is not None:
                    return row
            raise RuntimeError(f'{kind}: no matching fresh reply for {mid}; no retry')

        try:
            for mid in (66, 67):
                row = exchange(mid, v2_mode_request(mid), 'mode_read')
                if row['control_mode'] != 2:
                    raise RuntimeError('unexpected mode; no Rest issued')
            for mid in (66, 67):
                row = exchange(mid, rest_request(mid), 'rest')
                if row['status'] != 0 or row['fault'] != 0:
                    raise RuntimeError('Rest/fault check failed; remaining commands cancelled')
                raw = bytes.fromhex(row['raw_hex'])
                row['position_raw_u16'] = int.from_bytes(raw[1:3], 'big')
                row['velocity_raw_u12'] = (raw[3] << 4) | (raw[4] >> 4)
            for mid in range(61, 66):
                exchange(mid, position_request(mid), 'angle_read')
            r['status'] = 'RAW_SEVEN_AXIS_CAPTURED'
        except (RuntimeError, OSError) as exc:
            r['error'] = str(exc)
        # No finally disable/enable: no unsolicited state transitions on exit.
    return r


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--supported-wrist', action='store_true')
    p.add_argument('--allow-rest', action='store_true')
    p.add_argument('--authorization-ref', required=True)
    a = p.parse_args()
    with a.output.open('x', encoding='utf-8') as out:
        r = capture(supported_wrist=a.supported_wrist, allow_rest=a.allow_rest,
                    authorization_ref=a.authorization_ref)
        json.dump(r, out, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
