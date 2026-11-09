"""Convert one contact-confirmed raw capture to existing pivot row schema.

Offline only. Requires explicit verified V2 range profile and pinned SDK URDF.
No default range, hidden axis conversion, TCP matrix, or physical approval.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from brick_stacking.localization.urdf_chain import urdf_forward_kinematics


SDK_URDF_SHA256 = '233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce'


def prepare(raw, profile, urdf, *, sample_id, contact_confirmed, contact_evidence, max_receive_span_s):
    if contact_confirmed is not True or not sample_id or not contact_evidence:
        raise ValueError('sample identity and explicit fixed-point contact evidence required')
    if raw.get('schema_version') != 'c-left-supported-rest-1' or raw.get('source') != 'real' or raw.get('arm_role') != 'left' or raw.get('interface') != 'can2':
        raise ValueError('expected selected-left real raw capture')
    if raw.get('status') != 'RAW_SEVEN_AXIS_CAPTURED' or raw.get('clock_domain') != 'host_monotonic' or not raw.get('epoch'):
        raise ValueError('complete capture and explicit clock required')
    if hashlib.sha256(Path(urdf).read_bytes()).hexdigest() != SDK_URDF_SHA256:
        raise ValueError('SDK model hash mismatch; vendor opposite-axis model is not interchangeable')
    if not math.isfinite(max_receive_span_s) or max_receive_span_s <= 0:
        raise ValueError('explicit positive receive-span threshold required')
    positions, stamps = {}, []
    for row in raw['received']:
        if 'control_mode' in row:
            continue
        mid = row['motor_id']
        if mid not in range(61, 68) or mid in positions:
            raise ValueError('exactly one runtime row per left joint required')
        if mid >= 66:
            config = profile.get(str(mid), {})
            if config.get('verified') is not True or not config.get('evidence') or config.get('units') != 'rad':
                raise ValueError('verified per-wrist Theta range evidence required')
            lo, hi = config.get('theta_min_rad'), config.get('theta_max_rad')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lo, hi)) or lo >= hi:
                raise ValueError('finite ordered measured/readback Theta range required')
            data = bytes.fromhex(row['raw_hex'])
            if len(data) != 8 or data[0] != 0 or data[6] != 0:
                raise ValueError('fault-free Rest runtime feedback required')
            q = lo + int.from_bytes(data[1:3], 'big') / 65535 * (hi-lo)
        else:
            data = bytes.fromhex(row['raw_hex'])
            if not 5 <= len(data) <= 8 or data[0] != 6:
                raise ValueError('A7 position read response required')
            q = struct.unpack('<f', data[1:5])[0]
            if row.get('position_sdk_rad') != q:
                raise ValueError('decoded angle disagrees with raw response')
        stamp = row.get('host_receive_monotonic_s')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (q, stamp)):
            raise ValueError('finite positions and receive stamps required')
        positions[mid] = q
        stamps.append(stamp)
    if set(positions) != set(range(61, 68)):
        raise ValueError('missing axis; never fill with zero')
    if max(stamps)-min(stamps) > max_receive_span_s:
        raise ValueError('receive span exceeds explicit threshold')
    joints = {f'L{i}_Joint': positions[60+i] for i in range(1, 8)}
    transform, _ = urdf_forward_kinematics(urdf, joints, base_frame='L_arm_root', tip_frame='L8_Link')
    return dict(sample_id=sample_id, clock_domain=raw['clock_domain'], epoch=raw['epoch'],
                host_stamp_s=max(stamps), T_base_flange=transform.matrix.tolist(),
                model_version=SDK_URDF_SHA256, joint_positions_sdk_rad=joints,
                receive_span_s=max(stamps)-min(stamps), contact_evidence=contact_evidence,
                range_evidence={mid: profile[mid]['evidence'] for mid in ('66', '67')},
                approved=False, notice='one candidate row; motion/stillness, shared epoch and independent multi-pose validation remain required')


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ('capture', 'range_profile', 'urdf', 'output'):
        p.add_argument(name, type=Path)
    p.add_argument('--sample-id', required=True)
    p.add_argument('--contact-confirmed', action='store_true')
    p.add_argument('--contact-evidence', required=True)
    p.add_argument('--max-receive-span-s', type=float, required=True)
    a = p.parse_args()
    row = prepare(json.loads(a.capture.read_text(encoding='utf-8-sig')),
                  json.loads(a.range_profile.read_text(encoding='utf-8-sig')), a.urdf,
                  sample_id=a.sample_id, contact_confirmed=a.contact_confirmed,
                  contact_evidence=a.contact_evidence, max_receive_span_s=a.max_receive_span_s)
    with a.output.open('x', encoding='utf-8') as f:
        json.dump(row, f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
