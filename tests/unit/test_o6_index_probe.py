import copy
import importlib.util
from pathlib import Path

import pytest


s=importlib.util.spec_from_file_location('index_probe',Path(__file__).parents[2]/'tools/c_o6_index_probe.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
SN='LHO6-04-322-L-Z-1-D'
START=[253,175,253,253,254,254]


class Fake:
    def __init__(self):
        self.data=dict(interface='can1',serial_number=SN,angles_raw=START.copy(),speeds_raw=[128]*6,faults_raw=[0]*6)
        self.writes=[];self.fault=False;self.error=None
    def snapshot(self):return copy.deepcopy(self.data)
    def write(self,cmd,values):self.writes.append((cmd,values.copy()))
    def observe(self):
        if self.error:raise self.error
        x=START.copy();x[2]-=8
        return x,[1 if self.fault else 0]*6


def run(io, **extra):
    params=dict(expected_serial=SN,expected_start_raw=START,delta_raw=-8,speed_percent=10)
    params.update(extra)
    return m.run_trial(io,**params)


def execute(io, **extra):
    params=dict(execute=True,empty_hand=True,arm_supported=True,clearance_confirmed=True,physical_stop_confirmed=True,authorization_ref='unit-test-only')
    params.update(extra);return run(io,**params)


def test_default_preview_never_writes():
    io=Fake();r=run(io)
    assert not io.writes and r['status']=='READ_ONLY_PREVIEW'
    assert r['plan']['target_raw']==[253,175,245,253,254,254]


@pytest.mark.parametrize('bad',['empty_hand','arm_supported','clearance_confirmed','physical_stop_confirmed'])
def test_field_condition_missing_refuses_all_writes(bad):
    io=Fake()
    with pytest.raises(ValueError):execute(io,**{bad:False})
    assert not io.writes


@pytest.mark.parametrize('bad',['serial','fault','changed_start','range','speed'])
def test_bad_identity_state_or_trial_refused_before_writes(bad):
    io=Fake();args={}
    if bad=='serial':io.data['serial_number']='right'
    elif bad=='fault':io.data['faults_raw'][0]=3
    elif bad=='changed_start':io.data['angles_raw'][0]-=10
    elif bad=='range':args['delta_raw']=9
    elif bad=='speed':args['speed_percent']=float('nan')
    with pytest.raises(ValueError):execute(io,**args)
    assert not io.writes


def test_one_index_target_only_no_auto_return_or_speed_restore(monkeypatch):
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    io=Fake();r=execute(io)
    assert r['status']=='TARGET_FEEDBACK_OBSERVED' and r['angle_command_attempts']==1
    assert io.writes==[(5,[128,128,26,128,128,128]),(1,[253,175,245,253,254,254])]
    assert r['plan']['physical_motion_verified'] is False and r['stop_confirmed'] is False


@pytest.mark.parametrize('failure',['fault','timeout','interrupt'])
def test_failure_does_not_blindly_reverse_or_claim_stop(failure):
    io=Fake()
    if failure=='fault':io.fault=True
    elif failure=='timeout':io.error=RuntimeError('timeout')
    else:io.error=KeyboardInterrupt()
    r=execute(io)
    assert r['status']=='INCOMPLETE' and not r['stop_confirmed']
    assert len(io.writes)==2 and 'error' in r
