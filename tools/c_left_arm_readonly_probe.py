"""Bounded Linux SocketCAN LEFT J1..5 angle and J6/7 Flash mode READS.

Standalone standard-library tool. Never imports or constructs the motion SDK.
J6/J7 packets are retained raw: quantization and state source need validation.
This diagnostic intentionally cannot produce a complete calibration sample.
"""
import argparse
import json
import math
from pathlib import Path
import socket
import struct
import time
import uuid


CAN_FRAME = struct.Struct('=IB3x8s')
LEFT_IDS = tuple(range(61, 68))


def receive_filters():
    # SocketCAN's CAN_ERR_FLAG in can_mask selects the error receive list;
    # it must NOT be added here as a supposed ordinary-frame exclusion.
    # Standard data IDs: CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_SFF_MASK.
    ids = LEFT_IDS + (0x600 + 66, 0x600 + 67)
    return b''.join(struct.pack('=II', mid, 0xC00007FF) for mid in ids)


def v2_mode_request(motor_id):
    if motor_id not in (66, 67):
        raise ValueError('only LEFT J6/7 Flash control-mode READ is allowed')
    return CAN_FRAME.pack(0x600 + motor_id, 8, bytes.fromhex('670b000000000476'))


def position_request(motor_id):
    if motor_id not in range(61, 66):
        raise ValueError('only LEFT A7 J1..5 position reads are allowed')
    return CAN_FRAME.pack(motor_id, 1, b'\x06')


def decode_received(frame, flags):
    # Drop local TX, extended/RTR/error frames, short and unrelated packets.
    if flags & socket.MSG_DONTROUTE or len(frame) != CAN_FRAME.size:
        return None
    motor_id, size, payload = CAN_FRAME.unpack(frame)
    if motor_id in (0x600 + 66, 0x600 + 67):
        mid = motor_id - 0x600
        if size != 8 or payload[:2] != bytes([mid, 0x0B]) or payload[6:] != b'\x00\xff':
            return None
        return dict(motor_id=mid, raw_hex=payload.hex(),
                    control_mode=int.from_bytes(payload[2:6], 'little', signed=True),
                    position_sdk_rad=None, notice='Flash mode READ; not runtime angle/state')
    if motor_id not in LEFT_IDS or size > 8:
        return None
    payload = payload[:size]
    row = dict(motor_id=motor_id, raw_hex=payload.hex())
    if motor_id <= 65:
        if size < 5 or payload[0] != 0x06:
            return None
        angle = struct.unpack('<f', payload[1:5])[0]
        if not math.isfinite(angle):
            return None
        row['position_sdk_rad'] = angle
    else:
        if size != 8 or payload[0] not in range(6):
            return None
        row.update(status=payload[0], fault=payload[6], position_sdk_rad=None,
                   notice='raw V2 feedback; quantization not verified')
    return row


def capture(timeout_s=0.35, passive_s=0.5, read_wrist_mode=True):
    if not math.isfinite(timeout_s) or not 0 < timeout_s <= 1:
        raise ValueError('query timeout must be in (0, 1] seconds')
    if not math.isfinite(passive_s) or not 0 <= passive_s <= 3:
        raise ValueError('passive window must be in [0, 3] seconds')
    if type(read_wrist_mode) is not bool:raise ValueError('explicit wrist-mode selection required')
    report = dict(schema_version='c-left-readonly-probe-1', source='real',
                  arm_role='left', interface='can2', units='rad',
                  clock_domain='host_monotonic', epoch='linux_boot:'+str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip())),capture_id=str(uuid.uuid4()),
                  stamp_semantics='host receive/dequeue time, not device time',
                  transmitted=[], received=[], missing_motor_ids=list(LEFT_IDS),
                  calibration_sample_valid=False, motion_commands_sent=0,
                  complete_seven_axis_state=False)
    start = time.monotonic()
    with socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW) as bus:
        bus.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, receive_filters())
        bus.bind(('can2',))

        def receive_until(deadline, expected=None):
            while time.monotonic() < deadline:
                bus.settimeout(max(0.0001, deadline - time.monotonic()))
                try:
                    frame, _, flags, _ = bus.recvmsg(CAN_FRAME.size)
                except socket.timeout:
                    break
                row = decode_received(frame, flags)
                if row is None:
                    continue
                row['host_receive_monotonic_s'] = time.monotonic()
                report['received'].append(row)
                if row['motor_id'] == expected:
                    break

        # Drain old queued traffic before the first request; retain only new data.
        bus.setblocking(False)
        for _ in range(4096):
            try:
                bus.recvmsg(CAN_FRAME.size)
            except BlockingIOError:
                break
        else:
            raise RuntimeError('receive queue did not drain; no requests sent')
        for mid in (LEFT_IDS if read_wrist_mode else LEFT_IDS[:5]):
            sent_at = time.monotonic()
            packet = position_request(mid) if mid <= 65 else v2_mode_request(mid)
            count = bus.send(packet)
            if count != CAN_FRAME.size:
                raise RuntimeError('incomplete CAN position request')
            wire_id, size, payload = CAN_FRAME.unpack(packet)
            report['transmitted'].append(dict(motor_id=mid, arbitration_id=wire_id,
                                              data_hex=payload[:size].hex(),
                                              host_send_monotonic_s=sent_at))
            receive_until(sent_at + timeout_s, mid)
        receive_until(time.monotonic() + passive_s)
    observed = {row['motor_id'] for row in report['received']}
    report['missing_motor_ids'] = [mid for mid in LEFT_IDS if mid not in observed]
    positioned = {r['motor_id'] for r in report['received'] if r.get('position_sdk_rad') is not None}
    report['missing_position_ids'] = [mid for mid in LEFT_IDS if mid not in positioned]
    report['elapsed_s'] = time.monotonic() - start
    report['status'] = 'DIAGNOSTIC_ONLY'
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--five-axis-only',action='store_true',help='only J1..5 position READs; no wrist requests')
    args = parser.parse_args()
    # Reserve output before touching the bus; never overwrite an earlier capture.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(capture(read_wrist_mode=not args.five_axis_only), stream, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
