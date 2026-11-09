"""Read-only robot interface audit; no enable, motion, reset or Flash writes.
Run with the existing p7 SDK python for --kind can, vision python for camera.
Parameter-only replay variant: no preview imagery is saved.
Color/depth registration is NOT asserted.
"""
import argparse,base64,datetime,hashlib,json,pathlib,subprocess,time
p=argparse.ArgumentParser(); p.add_argument('--kind',choices=['can','camera'],required=True); p.add_argument('--output',required=True); a=p.parse_args()
out={'at':datetime.datetime.now().astimezone().isoformat(),'kind':a.kind,'motion_commands_sent':False}
if a.kind=='can':
 import can,struct
 out['links']=json.loads(subprocess.check_output(['ip','-j','-details','-statistics','link','show','type','can']))
 out['usb']=subprocess.check_output(['lsusb','-t'],text=True)
 out['can_sysfs']={x.name:str((x/'device').resolve()) for x in pathlib.Path('/sys/class/net').glob('can*')}
 def query(b,mid,data,seconds=.25):
  b.send(can.Message(arbitration_id=mid,is_extended_id=False,data=bytes(data)))
  rows=[]; end=time.monotonic()+seconds
  while time.monotonic()<end:
   m=b.recv(.03)
   if m is not None: rows.append({'id':m.arbitration_id,'hex':m.data.hex(),'stamp':m.timestamp})
  return rows
 out['motors']=[]
 for iface,base in [('can2',60),('can3',50)]:
  with can.Bus(channel=iface,interface='socketcan') as b:
   for j in range(1,8):
    mid=base+j; row={'interface':iface,'joint':j,'id':mid}
    if j<=5:
     row['queries']={hex(cmd):query(b,mid,[cmd]) for cmd in [6,0x2b,0x5f]}
     rr=row['queries']['0x6']; rr=[r for r in rr if r['id']==mid and r['hex'].startswith('06') and len(bytes.fromhex(r['hex']))>=5]
     row['position_rad']=struct.unpack('<f',bytes.fromhex(rr[0]['hex'])[1:5])[0] if rr else None
    else:
     row['mode_query']=query(b,0x600+mid,[0x67,0x0b,0,0,0,0,4,0x76])
    out['motors'].append(row)
 out['hands']=[]
 for iface,mid in [('can0',0x27),('can1',0x28)]:
  with can.Bus(channel=iface,interface='socketcan') as b:
   row={'interface':iface,'id':mid,'queries':{hex(c):query(b,mid,[c]) for c in [0xc0,0xc1,0xc2,0xc4,1,0x33,0x35]}}
   rr=row['queries']['0xc0']; sn=sorted([bytes.fromhex(r['hex']) for r in rr if r['id']==mid and r['hex'].startswith('c0')],key=lambda d:d[1])
   row['serial']=b''.join(d[2:] for d in sn).rstrip(b'\0').decode('ascii',errors='replace')
   out['hands'].append(row)
 root=next(pathlib.Path('/home/qwer/linkerbot-p7-unpack').glob('*/src/linkerbot'))
 out['source_sha256']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'arm/p7/motor_v2.py',root/'arm/p7/p7.py',root/'comm/can/can.py',root/'hand/o6/o6.py']}
elif a.kind=='camera':
 import pyorbbecsdk as s,numpy as np
 ctx=s.Context(); ds=ctx.query_devices(); out['sdk_version']=s.get_version(); out['devices']=[]
 for i in range(ds.get_count()):
  row={}; pipe=None; started=False
  try:
   d=ds.get_device_by_index(i); info=d.get_device_info(); row.update(serial=info.get_serial_number(),name=info.get_name(),firmware=info.get_firmware_version(),connection=info.get_connection_type())
   pipe=s.Pipeline(d); cfg=s.Config()
   for typ,key in [(s.OBSensorType.COLOR_SENSOR,'color'),(s.OBSensorType.DEPTH_SENSOR,'depth')]:
    ps=pipe.get_stream_profile_list(typ); vs=[ps.get_stream_profile_by_index(k).as_video_stream_profile() for k in range(ps.get_count())]
    allowed=[s.OBFormat.RGB,s.OBFormat.MJPG,s.OBFormat.YUYV] if key=='color' else [s.OBFormat.Y16]
    vs=[v for v in vs if v.get_format() in allowed]; v=min(vs,key=lambda x:abs(x.get_width()-640)+abs(x.get_height()-480)+abs(x.get_fps()-15))
    cfg.enable_stream(v); intr=v.get_intrinsic(); row[key]={'width':v.get_width(),'height':v.get_height(),'fps':v.get_fps(),'format':str(v.get_format()),'fx':intr.fx,'fy':intr.fy,'cx':intr.cx,'cy':intr.cy}
   pipe.start(cfg); started=True; frames=[]; end=time.monotonic()+10; warm=0
   while len(frames)<15 and time.monotonic()<end:
    fs=pipe.wait_for_frames(500)
    if not fs: continue
    c,z=fs.get_color_frame(),fs.get_depth_frame()
    if not c or not z: continue
    warm+=1
    if warm<=15: continue
    arr=np.frombuffer(z.get_data(),np.uint16)
    frames.append({'color_us':c.get_timestamp_us(),'depth_us':z.get_timestamp_us(),'depth_scale_mm':z.get_depth_scale(),'nonzero_depth_ratio':float((arr>0).mean())})
   row['frames']=frames; row['stream_ok']=len(frames)==15
  except Exception as e: row['error']=repr(e)
  finally:
   if started: pipe.stop()
  out['devices'].append(row)
pathlib.Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('AUDIT_SAVED',a.output)

