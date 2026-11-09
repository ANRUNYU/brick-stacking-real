import importlib.util
from pathlib import Path
import pytest

s=importlib.util.spec_from_file_location('static_capture',Path(__file__).parents[2]/'tools/c_static_calibration_capture.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def data():
    cycles=[]
    for t in (1.,1.05,1.1,1.15):
        rows=[dict(motor_id=mid,position_sdk_rad=.1,host_receive_monotonic_s=t) for mid in range(61,66)]
        cycles.append(dict(received=rows,epoch='linux_boot:synthetic',clock_domain='host_monotonic'))
    return cycles,dict(result='CAPTURED',frames=[dict(host_receive_stamp_s=1.06,host_clock_domain='host_monotonic'),dict(host_receive_stamp_s=1.13,host_clock_domain='host_monotonic')])


def summarize(c,r):return m.stationary_summary(c,r,max_joint_span_rad=.001,max_state_gap_s=.1)


def test_static_quality_is_not_clock_mapping_or_calibration_approval():
    r=summarize(*data());assert r['stationary_capture_quality']=='PASS'
    assert not r['calibration_sample_valid'] and r['device_host_latency_mapping']=='UNKNOWN'


@pytest.mark.parametrize('bad',['motion','gap','coverage','missing','epoch'])
def test_unqualified_static_capture_retained_as_failure(bad):
    c,r=data()
    if bad=='motion':c[-1]['received'][0]['position_sdk_rad']+=.01
    elif bad=='gap':c[1]['received'][0]['host_receive_monotonic_s']+=.5
    elif bad=='coverage':r['frames'][-1]['host_receive_stamp_s']=3
    elif bad=='missing':c[0]['received'].pop()
    elif bad=='epoch':c[-1]['epoch']='linux_boot:changed'
    assert summarize(c,r)['stationary_capture_quality']=='FAIL'


def test_recorder_requests_only_five_read_axes_and_cleans_up(tmp_path):
    import json,time
    calls=[]
    def joint_capture(**kwargs):
        calls.append(kwargs)
        at=time.monotonic()
        return dict(received=[dict(motor_id=mid,position_sdk_rad=.1,host_receive_monotonic_s=at) for mid in range(61,66)],epoch='linux_boot:synthetic',clock_domain='host_monotonic')
    def camera_main(args):
        out=Path(args[-1]);out.mkdir()
        report=dict(result='CAPTURED',frames=[dict(host_receive_stamp_s=time.monotonic(),host_clock_domain='host_monotonic')])
        (out/'camera_report.json').write_text(json.dumps(report));return 0
    r=m.collect(camera_main,joint_capture,tmp_path/'capture',camera_serial='synthetic',attachment_id='synthetic',pose_id='synthetic',max_joint_span_rad=.001,max_state_gap_s=.2)
    assert r['quality']['stationary_capture_quality']=='PASS'
    assert len(calls)>=3 and all(c['read_wrist_mode'] is False for c in calls)
    assert r['target_writes']==0 and r['enable_rest_zero_flash_commands']==0


def test_isolated_read_worker_keeps_sampling_during_parent_block(tmp_path):
    import json,time,hashlib
    joint=tmp_path/'fake_read.py'
    joint.write_text('''import time
def capture(**kwargs):
 assert kwargs['read_wrist_mode'] is False
 at=time.monotonic()
 return dict(received=[dict(motor_id=i,position_sdk_rad=.1,host_receive_monotonic_s=at) for i in range(61,66)],epoch='linux_boot:synthetic',clock_domain='host_monotonic')
''')
    sha=hashlib.sha256(joint.read_bytes()).hexdigest()
    def camera_main(args):
        out=Path(args[-1]);out.mkdir()
        # A native SDK can block the parent's GIL; a separate interpreter is independent.
        begin=time.monotonic();time.sleep(.3)
        report=dict(result='CAPTURED',frames=[dict(host_receive_stamp_s=begin,host_clock_domain='host_monotonic')])
        (out/'camera_report.json').write_text(json.dumps(report));return 0
    r=m.collect(camera_main,None,tmp_path/'isolated',camera_serial='synthetic',attachment_id='synthetic',pose_id='synthetic',max_joint_span_rad=.001,max_state_gap_s=.2,joint_process_factory=lambda out:m.start_worker(joint,sha,out))
    assert r['sampler']=='isolated_readonly_process' and r['quality']['stationary_capture_quality']=='PASS'
