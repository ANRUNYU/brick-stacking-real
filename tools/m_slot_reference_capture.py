"""Bounded camera-only black-cross reference collection. Preview by default."""
import argparse
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess,sys
from pathlib import Path


def main(argv=None,*,runner=subprocess.run):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True,help='new directory, never overwrite')
    p.add_argument('--serial',default='CP2L863000KL')
    p.add_argument('--frames',type=int,default=10)
    p.add_argument('--execute',action='store_true',help='camera only; no motion')
    p.add_argument('--marker-clear-confirmed',action='store_true',help='operator confirms cross visible and camera not in use')
    args=p.parse_args(argv)
    if not 2<=args.frames<=30:p.error('frames must be 2..30')
    if not args.serial.strip():p.error('camera serial required')
    root=Path(__file__).resolve().parents[1]
    script=root/'tools/orbbec_camera_probe.py'
    out=args.output.resolve()
    if out.exists() or Path(str(out)+'.zip').exists():p.error('output or zip exists; choose a fresh path')
    report=dict(schema_version='m-slot-reference-capture-1',created_utc=datetime.now(timezone.utc).isoformat(),
                serial=args.serial,execute=args.execute,commands_sent_to_robot=0,
                control_ready=False,motion_enabled=False,permit=None,
                expected_reference_frame='table_black_cross_20mm',
                target_definition_only=dict(table_center_m=[0,0,0],nominal_edge_m=.05,
                                            model_center_m=[0,0,.025],top_center_m=[0,0,.05]),
                camera_expectations=None,calibration_binding=None,target_association_confirmed=False,
                marker_center_pixel=None,table_plane=None,reference_error_bound_m=None,
                result='PREVIEW',errors=[])
    inventory=[sys.executable,str(script),'--output',str(out/'inventory')]
    capture=[sys.executable,str(script),'--capture','--serial',args.serial,
             '--frames',str(args.frames),'--seconds','40','--width','640','--height','480',
             '--fps','15','--output',str(out/'rgbd')]
    if not args.execute:
        print(json.dumps(dict(report,planned_commands=[inventory,capture]),ensure_ascii=False));return 0
    if not args.marker_clear_confirmed:p.error('execute requires --marker-clear-confirmed')
    out.mkdir(parents=True)
    try:
        for name,command in (('inventory',inventory),('rgbd',capture)):
            completed=runner(command,cwd=root,capture_output=True,text=True,encoding='utf-8',
                             errors='replace',timeout=90)
            (out/(name+'.stdout.log')).write_text(completed.stdout,encoding='utf-8')
            (out/(name+'.stderr.log')).write_text(completed.stderr,encoding='utf-8')
            record=json.loads((out/name/'camera_report.json').read_text(encoding='utf-8'))
            if completed.returncode!=0 or record.get('errors') or record.get('cleanup_errors'):
                raise ValueError(name+' failed; inspect camera_report.json and logs')
            if name=='inventory':
                found=[d for d in record.get('devices',[]) if d.get('serial')==args.serial]
                if record.get('result')!='INVENTORY' or len(found)!=1:
                    raise ValueError('expected camera not uniquely enumerated; no capture attempted')
            elif record.get('result')!='CAPTURED' or len(record.get('frames',[]))!=args.frames:
                raise ValueError('incomplete frame capture')
        files=list((out/'rgbd').glob('*.npz'))
        if len(files)!=args.frames:raise ValueError('raw NPZ count mismatch')
        report['result']='CAPTURED_REFERENCE_INPUTS_PENDING_ANNOTATION'
        report['next_required']=['cross-center pixel annotation with coordinate convention and uncertainty',
                                 'table plane / upward normal and uncertainty',
                                 'actual cube edge and measurement uncertainty',
                                 'current camera/calibration/scene binding',
                                 'construct independent camera-frame goal before contrast capture']
    except Exception as exc:
        report['result']='FAILED';report['errors'].append(type(exc).__name__+': '+str(exc))
        if isinstance(exc,subprocess.TimeoutExpired):
            for name,value in (('timeout.stdout.log',exc.stdout),('timeout.stderr.log',exc.stderr)):
                if value is not None:(out/name).write_bytes(value if isinstance(value,bytes) else value.encode('utf-8'))
    report['input_hashes']={f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in sorted(out.rglob('*')) if f.is_file()}
    (out/'slot_reference_capture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.make_archive(str(out),'zip',root_dir=out)
    print(json.dumps(dict(result=report['result'],errors=report['errors'],output=str(out),
                         archive=str(out)+'.zip',control_ready=False),ensure_ascii=False))
    return 2 if report['errors'] else 0


if __name__=='__main__':raise SystemExit(main())
