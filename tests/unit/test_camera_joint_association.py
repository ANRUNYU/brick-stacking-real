import importlib.util
from pathlib import Path
import struct
import pytest


def load(name,filename):
    s=importlib.util.spec_from_file_location(name,Path(__file__).parents[2]/'tools'/filename)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


m=load('association','associate_camera_joint_samples.py')
camera_tool=load('clock_read','c_head_camera_probe.py')


@pytest.fixture
def recording():
    cycles=[]
    for t in (1.,1.05,1.1,1.15):
        q=struct.unpack('<f',struct.pack('<f',t*.02))[0]
        rows=[dict(motor_id=i,raw_hex=(b'\x06'+struct.pack('<f',q)).hex(),position_sdk_rad=q,host_receive_monotonic_s=t) for i in range(61,66)]
        cycles.append(dict(schema_version='c-left-readonly-probe-1',source='synthetic',arm_role='left',interface='can2',clock_domain='host_monotonic',epoch='linux_boot:synthetic',received=rows))
    class Frame:
        def get_timestamp_us(self):return 5000000
        def get_system_timestamp_us(self):return 1000105000
        def get_global_timestamp_us(self):return 1000075000
    clocks=camera_tool.frame_clocks(Frame(),Frame(),'REALTIME',dict(monotonic_before_s=1.2,monotonic_after_s=1.2,realtime_s=1000.2,monotonic_raw_s=1.))
    report=dict(result='CAPTURED',frames=[dict(file='frame_000.npz',clock_observation=clocks)])
    return cycles,report


def associate(recording):return m.associate(*recording,max_bracket_gap_s=.1,max_bracket_step_rad=.01,max_rgb_depth_skew_s=.02)


def test_exposure_interpolation_preserves_raw_time_and_provisional_status(recording):
    r=associate(recording);row=r['samples'][0]
    assert row['association_host_monotonic_s']==pytest.approx(1.075)
    assert row['joint_positions_sdk_rad']['L1_Joint']==pytest.approx(.0215)
    assert row['clock_observation']['frames']['depth']['device_timestamp_us']==5000000
    assert row['quality']=='PROVISIONAL' and not r['calibration_sample_valid']
    assert r['timing_acceptance']=='NOT_VALIDATED' and not r['approved']


@pytest.mark.parametrize('bad',['epoch','raw','zero_global','bridge','extrapolate','gap','step','skew'])
def test_incompatible_or_unobservable_association_rejected(recording,bad):
    c,r=recording;obs=r['frames'][0]['clock_observation']
    if bad=='epoch':c[-1]['epoch']='linux_boot:other'
    elif bad=='raw':c[0]['received'][0]['position_sdk_rad']=9.
    elif bad=='zero_global':obs['frames']['depth']['global_timestamp_us']=0
    elif bad=='bridge':obs['frames']['depth']['global_host_monotonic_candidate_s']+=.01
    elif bad=='extrapolate':c[:]=c[2:]
    elif bad=='gap':c[:]=[c[0],c[-1]]
    elif bad=='step':
        for row in c[2]['received']:
            row['position_sdk_rad']=2.;row['raw_hex']=(b'\x06'+struct.pack('<f',2.)).hex()
    elif bad=='skew':
        obs['frames']['color']['global_timestamp_us']+=30000
        obs['frames']['color']['global_host_monotonic_candidate_s']+=.03
    with pytest.raises(ValueError):associate(recording)
