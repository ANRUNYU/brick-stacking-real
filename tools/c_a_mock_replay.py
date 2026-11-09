"""Replay C's synthetic point sample with A's pinned MockArm checkout only.

Run in a fresh interpreter. Never imports an installed hardware adapter, issues
a real permit, or claims sampled point replay preserves continuous interpolation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--a-checkout',type=Path,required=True);p.add_argument('--expected-commit',required=True)
    p.add_argument('--sample',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    commit=subprocess.check_output(['git','-C',str(a.a_checkout),'rev-parse','HEAD'],text=True).strip()
    if commit!=a.expected_commit:raise ValueError('reviewed A checkout commit mismatch')
    data=json.loads(a.sample.read_text(encoding='utf-8-sig'))
    if data.get('source')!='synthetic' or data.get('execution_backend_restriction')!='mock' or data.get('motion_enabled') is not False:
        raise ValueError('only explicit synthetic, mock-only C sample supported')
    if 'brick_stacking' in sys.modules:raise ValueError('launch in a fresh interpreter; do not replace loaded C modules')
    sys.path.insert(0,str((a.a_checkout/'src').resolve()))
    from brick_stacking.arm.adapter import MockArm,trajectory_hash
    if MockArm.backend!='mock' or MockArm.hardware_enabled is not False:raise ValueError('only reviewed MockArm allowed')
    trajectory=MockArm.validate_trajectory(data['trajectory'])
    class Clock:
        now=10.
        def __call__(self):return self.now
    reports=[]
    for mode in ('fresh_feedback','missing_feedback','cancel'):
        clock=Clock();external=dict(feedback=None)
        arm=MockArm(trajectory['points'][0]['q_rad'],clock=clock,feedback_reader=lambda:external['feedback'])
        baseline=arm.read_state()
        deadline=clock.now+trajectory['points'][-1]['time_from_start_s']+1.
        permit=dict(device_id='mock-arm',trajectory_hash=trajectory_hash(trajectory),config_hash='mock-config',calibration_hash='mock-calibration',scene_version='mock-scene',valid_until_host_monotonic_s=deadline)
        command=arm.execute_trajectory(trajectory,permit,valid_until_host_monotonic_s=deadline)
        start=clock.now
        for index,point in enumerate(trajectory['points']):
            clock.now=start+point['time_from_start_s']
            if mode=='fresh_feedback':external['feedback']=dict(baseline,sample_id=f'synthetic-feedback-{index}',host_receive_stamp=clock.now,q_rad=point['q_rad'])
            arm.step(command)
            if mode=='cancel':arm.cancel(command);break
        before=arm.get_execution_status(command)
        if mode=='fresh_feedback':
            clock.now+=.001
            external['feedback']=dict(baseline,sample_id='synthetic-post-dispatch-feedback',host_receive_stamp=clock.now,q_rad=trajectory['points'][-1]['q_rad'])
            arm.step(command)
        elif mode=='missing_feedback':clock.now=deadline;arm.step(command)
        result=arm.get_execution_result(command)
        expected={'fresh_feedback':'SUCCEEDED','missing_feedback':'FAILED','cancel':'CANCELLED'}[mode]
        if result['status']!=expected or (mode!='cancel' and before!='RUNNING'):raise AssertionError('feedback/expiry/cancel semantics mismatch')
        reports.append(dict(case=mode,status_before_final_check=before,result=result))
    output=dict(schema_version='c-a-mock-integration-1',source='synthetic',a_commit=commit,
                input_sha256=hashlib.sha256(a.sample.read_bytes()).hexdigest(),contract_version='0.1',
                joint_names=trajectory['joint_names'],point_count=len(trajectory['points']),reports=reports,
                continuous_interpolation_preserved=False,real_execution='NOT_TESTED',motion_enabled=False,
                notice='Mock dispatch/feedback contract only; A point contract cannot encode C quintic basis. No real trajectory approval.')
    with a.output.open('x',encoding='utf-8') as f:json.dump(output,f,indent=2,allow_nan=False)
    print(json.dumps(dict(cases=[(r['case'],r['result']['status']) for r in reports],a_commit=commit,points=len(trajectory['points']))))


if __name__=='__main__':main()
