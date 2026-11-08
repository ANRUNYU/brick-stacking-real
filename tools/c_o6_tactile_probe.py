"""Read-only O6 tactile batches; never opens/closes the hand or uses pytest fixtures.

Raw uint8 counts are not calibrated force/pressure units or a contact threshold.
"""
import argparse
import json
from pathlib import Path
import socket
import time
from c_o6_index_probe import FRAME, LEFT_ID, SocketHand


FINGERS = dict(thumb=0xB1,index=0xB2,middle=0xB3,ring=0xB4,pinky=0xB5)


class TactileBatch:
    def __init__(self, prefix):
        if prefix not in FINGERS.values():raise ValueError('known finger read prefix required')
        self.prefix=prefix;self.parts=None

    def add(self, data):
        if len(data)<6 or data[0]!=self.prefix:return None
        index=data[1]>>4
        if index>=10:return None
        if index==0:self.parts={}
        if self.parts is None:return None
        payload=bytes(data[2:6])
        if index in self.parts and self.parts[index]!=payload:
            raise ValueError('conflicting duplicate tactile frame')
        self.parts[index]=payload
        if set(self.parts)==set(range(10)):
            matrix=[list(self.parts[i]) for i in range(10)];self.parts=None
            return matrix
        return None


def read_matrix(io, prefix):
    batch=TactileBatch(prefix)
    io.bus.setblocking(False)
    for _ in range(4096):
        try:io.bus.recvmsg(FRAME.size)
        except BlockingIOError:break
    else:raise RuntimeError('busy receive queue; request not sent')
    if io.bus.send(FRAME.pack(LEFT_ID,2,bytes([prefix,0xA4])))!=FRAME.size:
        raise RuntimeError('incomplete tactile READ send')
    deadline=time.monotonic()+.6
    while time.monotonic()<deadline:
        io.bus.settimeout(max(.0001,deadline-time.monotonic()))
        try:frame,_,flags,_=io.bus.recvmsg(FRAME.size)
        except socket.timeout:break
        cid,n,p=FRAME.unpack(frame)
        if flags & socket.MSG_DONTROUTE or cid!=LEFT_ID or not 0<n<=8:continue
        matrix=batch.add(p[:n])
        if matrix is not None:return dict(raw_u8_10x4=matrix,host_receive_monotonic_s=time.monotonic())
    return dict(raw_u8_10x4=None,error='incomplete batch or no response; no retry')


def capture(io, expected_serial):
    serial=io.read(0xC0)
    if '-L-' not in expected_serial or serial!=expected_serial:raise ValueError('expected LEFT SN required before sensor requests')
    rows=[]
    for repeat in range(2):
        for finger,prefix in FINGERS.items():
            try:sample=read_matrix(io,prefix)
            except (ValueError,RuntimeError) as exc:sample=dict(raw_u8_10x4=None,error=str(exc))
            rows.append(dict(repeat=repeat,finger=finger,**sample))
        if repeat==0:time.sleep(.2)
    return dict(schema_version='c-o6-tactile-read-1',source='real',serial_number=serial,interface=io.interface,
                clock_domain='host_monotonic',epoch='linux_boot:'+Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                units='uncalibrated_raw_u8',contact_condition='not independently established',rows=rows,
                commands='SN C0 READ then each B1..B5 A4 READ twice',control_writes=0,
                notice='complete matrices establish response only, not force calibration/contact discrimination')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('output',type=Path);p.add_argument('--interface',required=True,choices=('can0','can1'));p.add_argument('--expected-serial',required=True);a=p.parse_args()
    with a.output.open('x',encoding='utf-8') as f:
        io=SocketHand(a.interface)
        try:json.dump(capture(io,a.expected_serial),f,indent=2,allow_nan=False)
        finally:io.close()


if __name__=='__main__':main()
