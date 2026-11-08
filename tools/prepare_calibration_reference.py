"""Read-only captured J1..5 -> pinned SDK L5_Link FK, never flange/TCP.

Allows fixed-camera calibration with a target attached BEFORE J6/J7. Does not
assume wrist quantization, wrist stiffness, zero TCP, or camera time alignment.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import uuid
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics


MODEL_SHA256='233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce'


def prepare(raw,urdf,*,sample_id,max_receive_span_s):
    if not sample_id or raw.get('arm_role')!='left' or raw.get('interface')!='can2' or raw.get('clock_domain')!='host_monotonic':
        raise ValueError('identified selected-left host-clock capture required')
    if raw.get('schema_version')!='c-left-readonly-probe-1' or raw.get('source') not in ('real','recorded','synthetic'):
        raise ValueError('explicit raw source/schema required')
    if not isinstance(raw.get('epoch'),str) or not raw['epoch'].startswith('linux_boot:'):
        raise ValueError('verified boot epoch required; do not relabel old capture UUIDs')
    uuid.UUID(raw['epoch'].split(':',1)[1])
    if not math.isfinite(max_receive_span_s) or max_receive_span_s<=0:raise ValueError('explicit positive receive-span threshold required')
    if hashlib.sha256(Path(urdf).read_bytes()).hexdigest()!=MODEL_SHA256:
        raise ValueError('SDK model hash mismatch')
    positions={};stamps=[]
    for row in raw['received']:
        mid=row['motor_id']
        if mid not in range(61,66):continue
        if mid in positions:raise ValueError('duplicate upstream runtime sample')
        data=bytes.fromhex(row['raw_hex'])
        if not 5<=len(data)<=8 or data[0]!=6:raise ValueError('A7 position READ response required')
        q=struct.unpack('<f',data[1:5])[0];stamp=row.get('host_receive_monotonic_s')
        if not math.isfinite(q) or row.get('position_sdk_rad')!=q or isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or stamp<0:
            raise ValueError('raw/decoded angle or host timestamp invalid')
        positions[mid]=q;stamps.append(stamp)
    if set(positions)!=set(range(61,66)):raise ValueError('all five upstream joints required; never fill missing joints')
    span=max(stamps)-min(stamps)
    if span>max_receive_span_s:raise ValueError('receive span too large')
    named={f'L{i}_Joint':positions[60+i] for i in range(1,6)}
    pose,_=urdf_forward_kinematics(urdf,named,base_frame='L_arm_root',tip_frame='L5_Link')
    return dict(schema_version='c-upstream-reference-pose-1',sample_id=sample_id,source=raw['source'],
                base_frame='L_arm_root',reference_frame='L5_Link',T_base_reference=pose.matrix.tolist(),
                model_version=MODEL_SHA256,joint_positions_sdk_rad=named,clock_domain=raw['clock_domain'],epoch=raw['epoch'],
                receive_interval_s=[min(stamps),max(stamps)],receive_span_s=span,
                camera_time_alignment='NOT_ESTABLISHED',approved=False,motion_enabled=False,
                notice='only valid with target rigidly attached to verified L5 link; not a flange pose, TCP, or permission to move')


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('capture','urdf','output'):p.add_argument(name,type=Path)
    p.add_argument('--sample-id',required=True);p.add_argument('--max-receive-span-s',type=float,required=True);a=p.parse_args()
    r=prepare(json.loads(a.capture.read_text(encoding='utf-8-sig')),a.urdf,sample_id=a.sample_id,max_receive_span_s=a.max_receive_span_s)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
