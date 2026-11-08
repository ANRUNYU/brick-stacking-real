"""Static calibration recording: head camera + J1..5 READ only, no arm motion.

Records device/host clocks separately. Joint stationarity supports a static-pose
association; it is not a measured device-to-host latency mapping or motion permit.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
import time
import subprocess
import sys


CAMERA_TOOL_SHA='60e3b1b0210d41a84529f404ec2ae4500beb42766f8b6aca55f8760d021d2ce9'


def stationary_summary(cycles,camera_report,*,max_joint_span_rad,max_state_gap_s):
    import math
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in (max_joint_span_rad,max_state_gap_s)):
        raise ValueError('explicit positive measurement quality thresholds required')
    values=[];times=[];epochs=set();incomplete=0
    for cycle in cycles:
        rows=[r for r in cycle.get('received',[]) if r.get('motor_id') in range(61,66) and r.get('position_sdk_rad') is not None]
        if len(rows)!=5 or len({r['motor_id'] for r in rows})!=5:
            incomplete+=1;continue
        rows.sort(key=lambda x:x['motor_id'])
        q=[r['position_sdk_rad'] for r in rows];stamps=[r['host_receive_monotonic_s'] for r in rows]
        if not all(math.isfinite(x) for x in q+stamps):raise ValueError('nonfinite recorded state')
        values.append(q);times.append(max(stamps));epochs.add(cycle.get('epoch'))
        if cycle.get('clock_domain')!='host_monotonic':raise ValueError('host clock required')
        if not isinstance(cycle.get('epoch'),str) or not cycle['epoch'].startswith('linux_boot:'):raise ValueError('host boot epoch required')
    frames=camera_report.get('frames',[])
    if any(f.get('host_clock_domain')!='host_monotonic' for f in frames):raise ValueError('camera host-arrival clock must be explicit')
    ct=[f['host_receive_stamp_s'] for f in frames]
    spans=[max(q[i] for q in values)-min(q[i] for q in values) for i in range(5)] if values else None
    gap=max((b-a for a,b in zip(times,times[1:])),default=float('inf'))
    covered=bool(times and ct and min(times)<=min(ct) and max(times)>=max(ct))
    valid=len(values)>=3 and incomplete==0 and len(epochs)==1 and covered and gap<=max_state_gap_s and max(spans)<=max_joint_span_rad and camera_report.get('result')=='CAPTURED'
    return dict(schema_version='c-static-acquisition-quality-1',stationary_capture_quality='PASS' if valid else 'FAIL',
                complete_joint_cycles=len(values),incomplete_joint_cycles=incomplete,joint_span_rad=spans,
                max_state_gap_s=gap if math.isfinite(gap) else None,camera_host_window_covered=covered,
                clock_epoch=next(iter(epochs)) if len(epochs)==1 else None,
                max_joint_span_rad_threshold=max_joint_span_rad,max_state_gap_s_threshold=max_state_gap_s,
                time_association='static-pose assumption using host arrival times; device timestamps retained separately',
                device_host_latency_mapping='UNKNOWN',calibration_sample_valid=False,approved=False,motion_enabled=False)


def collect(camera_main,joint_capture,output,*,camera_serial,attachment_id,
            max_joint_span_rad,max_state_gap_s,pose_id,joint_process_factory=None):
    output=Path(output)
    if not attachment_id or not camera_serial or not pose_id:raise ValueError('pose, attachment and camera identities required')
    # Validate before opening either camera or CAN.
    stationary_summary([],{},max_joint_span_rad=max_joint_span_rad,max_state_gap_s=max_state_gap_s)
    output.mkdir(parents=True,exist_ok=False)
    cycles=[];errors=[];stop=threading.Event();started=time.monotonic()
    def sample():
        while not stop.is_set() and time.monotonic()-started<25:
            at=time.monotonic()
            try:cycles.append(joint_capture(timeout_s=.03,passive_s=0.,read_wrist_mode=False))
            except Exception as exc:
                errors.append(type(exc).__name__+': '+str(exc));break
            stop.wait(max(0.,.05-(time.monotonic()-at)))
    process=joint_process_factory(output) if joint_process_factory else None
    thread=None
    if process is None:
        # Injection path for pure tests. Hardware CLI always uses an isolated process.
        thread=threading.Thread(target=sample,daemon=True);thread.start()
    camera_exit=None
    try:
        time.sleep(.3)
        camera_exit=camera_main(['--capture','--serial',camera_serial,'--frames','3','--seconds','10','--output',str(output/'camera')])
        time.sleep(.3)
    finally:
        if process is not None:
            (output/'joint_worker.stop').write_text('stop',encoding='utf-8')
            try:_,stderr=process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate();_,stderr=process.communicate(timeout=2)
                errors.append('READ-only worker required process termination')
            worker_path=output/'joint_worker.json'
            if worker_path.exists():
                worker=json.loads(worker_path.read_text());cycles=worker['cycles'];errors.extend(worker['errors'])
            else:errors.append('READ-only worker produced no record')
            if process.returncode or stderr:errors.append('READ-only worker error: '+stderr.decode('utf-8',errors='replace')[:2000])
        else:
            stop.set();thread.join(timeout=2)
            if thread.is_alive():errors.append('joint READ thread still running; no motor commands exist in this recorder')
        (output/'joint_cycles.json').write_text(json.dumps(cycles,indent=2,allow_nan=False),encoding='utf-8')
    report_path=output/'camera/camera_report.json'
    camera=json.loads(report_path.read_text()) if report_path.exists() else {}
    quality=stationary_summary(cycles,camera,max_joint_span_rad=max_joint_span_rad,max_state_gap_s=max_state_gap_s)
    if errors or camera_exit!=0 or camera.get('errors') or camera.get('cleanup_errors'):quality['stationary_capture_quality']='FAIL'
    result=dict(schema_version='c-static-calibration-record-1',attachment_id=attachment_id,pose_id=pose_id,
                reference_frame='L5_Link',camera_serial=camera_serial,camera_exit=camera_exit,
                joint_read_only_ids=[61,62,63,64,65],joint_requests_per_cycle=5,target_writes=0,
                enable_rest_zero_flash_commands=0,quality=quality,errors=errors,
                sampler='isolated_readonly_process' if process is not None else 'injected_test_thread',
                notice='only raw static recording; attachment identity/center visibility/FK and independent physical calibration still require checks')
    (output/'record_manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result


def load(path,expected_sha,name):
    path=Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha:raise ValueError('reviewed tool source hash mismatch')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def worker_main():
    p=argparse.ArgumentParser();p.add_argument('--joint-worker',action='store_true');p.add_argument('--joint-tool',type=Path,required=True);p.add_argument('--joint-tool-sha',required=True);p.add_argument('--worker-output',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True);a=p.parse_args()
    joint=load(a.joint_tool,a.joint_tool_sha,'five_axis_read_worker');cycles=[];errors=[];started=time.monotonic()
    try:
        while not a.stop_file.exists() and time.monotonic()-started<25:
            at=time.monotonic()
            cycles.append(joint.capture(timeout_s=.03,passive_s=0.,read_wrist_mode=False))
            time.sleep(max(0.,.05-(time.monotonic()-at)))
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:a.worker_output.write_text(json.dumps(dict(cycles=cycles,errors=errors),indent=2,allow_nan=False),encoding='utf-8')


def start_worker(joint_tool,joint_sha,output):
    return subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--joint-worker',
            '--joint-tool',str(Path(joint_tool).resolve()),'--joint-tool-sha',joint_sha,
            '--worker-output',str(output/'joint_worker.json'),'--stop-file',str(output/'joint_worker.stop')],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('output',type=Path)
    p.add_argument('--camera-tool',type=Path,required=True);p.add_argument('--joint-tool',type=Path,required=True);p.add_argument('--joint-tool-sha',required=True)
    p.add_argument('--camera-serial',required=True);p.add_argument('--attachment-id',required=True)
    p.add_argument('--pose-id',required=True)
    p.add_argument('--max-joint-span-rad',type=float,required=True);p.add_argument('--max-state-gap-s',type=float,required=True);a=p.parse_args()
    camera=load(a.camera_tool,CAMERA_TOOL_SHA,'camera_read');joint=load(a.joint_tool,a.joint_tool_sha,'joint_read')
    r=collect(camera.main,joint.capture,a.output,camera_serial=a.camera_serial,attachment_id=a.attachment_id,
              max_joint_span_rad=a.max_joint_span_rad,max_state_gap_s=a.max_state_gap_s,pose_id=a.pose_id,
              joint_process_factory=lambda output:start_worker(a.joint_tool,a.joint_tool_sha,output))
    r['source_locks']=dict(camera_sha256=CAMERA_TOOL_SHA,joint_sha256=a.joint_tool_sha,
                           recorder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'record_manifest.json').write_text(json.dumps(r,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(r,allow_nan=False))


if __name__=='__main__':
    if '--joint-worker' in sys.argv:worker_main()
    else:main()
