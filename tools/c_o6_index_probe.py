"""Left O6 index-only field trial. Default is READ-ONLY preview.

Execution requires separate explicit onsite authorization. Exiting Python is
NOT a motor stop: the last hand target/speed remain active. No automatic return.
No arm SDK, enable, Rest, zero, Flash, right-hand, or other CAN-ID commands.
"""
import argparse
import json
import math
from pathlib import Path
import socket
import struct
import time


FRAME = struct.Struct('=IB3x8s')
LEFT_ID = 0x28


def six_raw(values):
    if not isinstance(values, (list, tuple)) or len(values) != 6 or any(type(x) is not int or not 0 <= x <= 255 for x in values):
        raise ValueError('exactly six hardware raw uint8 values required')
    return list(values)


def make_plan(snapshot, *, expected_serial, delta_raw, speed_percent):
    if '-L-' not in expected_serial or snapshot['serial_number'] != expected_serial:
        raise ValueError('expected LEFT serial mismatch')
    if type(delta_raw) is not int or not 1 <= abs(delta_raw) <= 8:
        raise ValueError('this field-trial proposal only allows 1..8 raw counts')
    if not isinstance(speed_percent, (float, int)) or isinstance(speed_percent, bool) or not math.isfinite(speed_percent) or not 0 < speed_percent <= 10:
        raise ValueError('explicit trial speed in (0,10] normalized percent required')
    start, speeds = six_raw(snapshot['angles_raw']), six_raw(snapshot['speeds_raw'])
    if any(six_raw(snapshot['faults_raw'])):
        raise ValueError('nonzero hand fault; no trial')
    target = start.copy(); target[2] += delta_raw
    six_raw(target)
    trial_speeds = speeds.copy();trial_speeds[2] = round(speed_percent*255/100)
    return dict(schema_version='c-o6-index-trial-1', serial_number=expected_serial,
                interface=snapshot['interface'], start_raw=start, target_raw=target,
                initial_speeds_raw=speeds, trial_speeds_raw=trial_speeds,
                index_delta_raw=delta_raw, speed_percent=speed_percent,
                units='hardware_raw_u8; speed normalized percent, not rad/s',
                motion_enabled=False, physical_motion_verified=False,
                automatic_return=False, automatic_speed_restore=False,
                warning='all six targets are transmitted; five keep measured start values; process exit does not stop the hand',
                scope='empty-hand direction/response trial only; not a grasp preset or safety/force acceptance')


def run_trial(io, *, expected_serial, expected_start_raw, delta_raw, speed_percent,
              execute=False, empty_hand=False, arm_supported=False,
              clearance_confirmed=False, physical_stop_confirmed=False, authorization_ref=''):
    snapshot = io.snapshot()
    plan = make_plan(snapshot, expected_serial=expected_serial, delta_raw=delta_raw, speed_percent=speed_percent)
    report = dict(plan=plan, snapshot=snapshot, writes=[], observations=[],
                  status='READ_ONLY_PREVIEW', stop_confirmed=None,
                  execution_requested=execute, angle_command_attempts=0)
    if not execute:
        return report
    if not all(x is True for x in (empty_hand, arm_supported, clearance_confirmed, physical_stop_confirmed)) or not isinstance(authorization_ref, str) or not authorization_ref.strip():
        raise ValueError('separate field authorization, empty/clear supported hand and physical-stop confirmation required')
    expected = six_raw(expected_start_raw)
    if any(abs(a-b) > 2 for a,b in zip(expected, snapshot['angles_raw'])):
        raise ValueError('start changed from reviewed proposal; no write')
    report.update(authorization_ref=authorization_ref, status='INCOMPLETE', stop_confirmed=False)
    try:
        # Keep the five non-index target and speed values from this fresh read.
        # Mark a write before calling send: exceptions cannot prove no TX occurred.
        for cmd, values in ((5, plan['trial_speeds_raw']), (1, plan['target_raw'])):
            report['writes'].append(dict(command=cmd, values=values, transmission='attempted'))
            if cmd == 1:report['angle_command_attempts'] += 1
            io.write(cmd, values)
            report['writes'][-1]['transmission'] = 'socket_send_completed_not_execution_ack'
        deadline = time.monotonic()+3
        settled = 0
        while time.monotonic() < deadline:
            angles, faults = io.observe()
            angles, faults = six_raw(angles), six_raw(faults)
            report['observations'].append(dict(angles_raw=angles, faults_raw=faults, host_receive_monotonic_s=time.monotonic()))
            if any(faults):
                raise RuntimeError('hand fault; operator must use confirmed physical stop')
            if any(abs(angles[i]-plan['start_raw'][i]) > 3 for i in (0,1,3,4,5)):
                raise RuntimeError('non-index feedback changed; operator must stop')
            settled = settled+1 if abs(angles[2]-plan['target_raw'][2]) <= 2 else 0
            if settled >= 3:
                report['status'] = 'TARGET_FEEDBACK_OBSERVED'
                break
            time.sleep(.1)
        else:
            raise RuntimeError('response window expired; software timeout is not a hand stop')
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt, EOFError) as exc:
        report['error'] = type(exc).__name__+': '+str(exc)
    report['final_state_notice'] = 'no automatic return/stop/speed restore; operator observes actual finger and secures hand'
    return report


class SocketHand:
    def __init__(self, interface):
        if interface not in ('can0','can1'):
            raise ValueError('only candidate hand buses can0/can1; never arm buses')
        self.interface = interface
        self.bus = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.bus.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, struct.pack('=II',LEFT_ID,0xC00007FF))
        self.bus.bind((interface,))

    def close(self):
        self.bus.close()  # Resource cleanup only, not a motor stop.

    def read(self, cmd):
        if cmd not in (0xC0,1,5,0x35):raise ValueError('read command not allowed')
        self.bus.setblocking(False)
        for _ in range(4096):
            try:self.bus.recvmsg(FRAME.size)
            except BlockingIOError:break
        else:raise RuntimeError('receive queue busy')
        self.bus.send(FRAME.pack(LEFT_ID,1,bytes([cmd])))
        deadline=time.monotonic()+.4;parts={}
        while time.monotonic()<deadline:
            self.bus.settimeout(max(.0001,deadline-time.monotonic()))
            try:frame,_,flags,_=self.bus.recvmsg(FRAME.size)
            except socket.timeout:break
            cid,n,p=FRAME.unpack(frame)
            if flags & socket.MSG_DONTROUTE or cid!=LEFT_ID or not 1<=n<=8 or p[0]!=cmd:continue
            if cmd==0xC0:
                if n>=2 and p[1] in range(4):parts[p[1]]=p[2:n]
                if len(parts)==4:return b''.join(parts[i] for i in range(4)).rstrip(b'\0').decode('ascii')
            elif n==7:return list(p[1:7])
        raise RuntimeError('read response timeout; no retry')

    def snapshot(self):
        serial=self.read(0xC0)
        if '-L-' not in serial:raise ValueError('left serial required before further hand access')
        return dict(interface=self.interface,serial_number=serial,angles_raw=self.read(1),speeds_raw=self.read(5),faults_raw=self.read(0x35),
                    host_receive_monotonic_s=time.monotonic(),clock_domain='host_monotonic',epoch='linux_boot:'+Path('/proc/sys/kernel/random/boot_id').read_text().strip())

    def observe(self):
        return self.read(1), self.read(0x35)

    def write(self, cmd, values):
        if cmd not in (1,5):raise ValueError('only hand angle/speed writes supported')
        if self.bus.send(FRAME.pack(LEFT_ID,7,bytes([cmd]+six_raw(values)))) != FRAME.size:
            raise RuntimeError('incomplete CAN send')


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('output',type=Path);p.add_argument('--interface',required=True,choices=('can0','can1'))
    p.add_argument('--expected-serial',required=True);p.add_argument('--delta-raw',type=int,required=True);p.add_argument('--speed-percent',type=float,required=True)
    p.add_argument('--expected-start-raw',type=int,nargs=6)
    for name in ('execute','empty-hand','arm-supported','clearance-confirmed','physical-stop-confirmed'):p.add_argument('--'+name,action='store_true')
    p.add_argument('--authorization-ref',default='');a=p.parse_args()
    with a.output.open('x',encoding='utf-8') as out:
        io=SocketHand(a.interface)
        try:
            r=run_trial(io,expected_serial=a.expected_serial,expected_start_raw=a.expected_start_raw,delta_raw=a.delta_raw,speed_percent=a.speed_percent,
                        execute=a.execute,empty_hand=a.empty_hand,arm_supported=a.arm_supported,clearance_confirmed=a.clearance_confirmed,
                        physical_stop_confirmed=a.physical_stop_confirmed,authorization_ref=a.authorization_ref)
            json.dump(r,out,indent=2,allow_nan=False)
            if a.execute:
                print('Last target and trial speed remain active; process exit is NOT a motor stop.',flush=True)
                if r['status']=='INCOMPLETE':
                    print('FIELD TRIAL INCOMPLETE: use the confirmed physical stop if needed; no automatic reverse/stop was sent.',flush=True)
                    raise SystemExit(2)
            print(r['status'],flush=True)
        finally:io.close()


if __name__=='__main__':main()
