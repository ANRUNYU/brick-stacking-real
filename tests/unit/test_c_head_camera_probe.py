import importlib.util
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('head_probe',Path(__file__).parents[2]/'tools/c_head_camera_probe.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class ClockFrame:
    def __init__(self,device=2000000,system=1000010000,glob=1000000000):self.values=device,system,glob
    def get_timestamp_us(self):return self.values[0]
    def get_system_timestamp_us(self):return self.values[1]
    def get_global_timestamp_us(self):return self.values[2]


def test_global_timestamp_is_explicit_clock_bridge_not_device_relabel():
    anchor=dict(monotonic_before_s=10.,monotonic_after_s=10.002,realtime_s=1000.5,monotonic_raw_s=8.)
    r=m.frame_clocks(ClockFrame(),ClockFrame(), 'OBClockType.REALTIME',anchor)
    assert r['frames']['color']['global_host_monotonic_candidate_s']==pytest.approx(9.501)
    assert r['frames']['color']['device_timestamp_us']==2000000
    assert r['frames']['color']['sdk_receive_minus_global_s']==pytest.approx(.01)
    assert r['timing_acceptance']=='NOT_VALIDATED' and r['device_to_host_mapping_error_bound_s'] is None


def test_zero_global_does_not_fall_back_to_device_or_arrival():
    anchor=dict(monotonic_before_s=10.,monotonic_after_s=10.002,realtime_s=1000.5,monotonic_raw_s=8.)
    r=m.frame_clocks(ClockFrame(glob=0),ClockFrame(glob=0),'REALTIME',anchor)
    assert not r['frames']['color']['global_available']
    assert r['frames']['color']['global_host_monotonic_candidate_s'] is None


def test_sdk_monotonic_raw_is_not_python_monotonic():
    anchor=dict(monotonic_before_s=10.,monotonic_after_s=10.002,realtime_s=1000.5,monotonic_raw_s=8.)
    f=ClockFrame(glob=7500000,system=7510000)
    r=m.frame_clocks(f,f,'MONOTONIC',anchor)
    assert r['frames']['color']['global_host_monotonic_candidate_s']==pytest.approx(9.501)
    assert r['sdk_host_clock_domain']=='linux_clock_monotonic_raw'


@pytest.mark.parametrize('bad',['clock','anchor','missing_raw','negative'])
def test_invalid_clock_observation_rejected(bad):
    a=dict(monotonic_before_s=10.,monotonic_after_s=10.002,realtime_s=1000.5,monotonic_raw_s=8.)
    clock='REALTIME';f=ClockFrame()
    if bad=='clock':clock='UNKNOWN'
    elif bad=='anchor':a['monotonic_after_s']=9.
    elif bad=='missing_raw':clock='MONOTONIC';a['monotonic_raw_s']=None
    elif bad=='negative':f=ClockFrame(glob=-1)
    with pytest.raises(ValueError):m.frame_clocks(f,f,clock,a)

class Profile:
    def __init__(self,w,h,f,fmt): self.v=(w,h,f,fmt)
    def as_video_stream_profile(self): return self
    def get_width(self): return self.v[0]
    def get_height(self): return self.v[1]
    def get_fps(self): return self.v[2]
    def get_format(self): return 'OBFormat.'+self.v[3]
class Profiles:
    def __init__(self,values): self.values=values
    def get_count(self): return len(self.values)
    def get_stream_profile_by_index(self,i): return self.values[i]

def test_exact_mode_and_format_preference():
    p=Profiles([Profile(640,480,15,'RGB'),Profile(1280,800,30,'RGB'),Profile(1280,800,15,'MJPG'),Profile(1280,800,15,'RGB')])
    assert m.choose_profile(p,['RGB','MJPG']) is p.values[-1]

def test_missing_exact_profile_refuses_fallback():
    with pytest.raises(ValueError,match='no fallback'):
        m.choose_profile(Profiles([Profile(640,480,15,'RGB')]),['RGB'])

def test_cached_rectification_preserves_values_and_depth_holes():
    import numpy as np
    k=np.array([[100.,0,4.],[0,100.,4.],[0,0,1.]])
    rgb=np.full((8,8,3),128,np.uint8)
    d=np.ones((8,8),np.float32);d[4,4]=np.nan
    dist=dict(model='BROWN_CONRADY',k1=.01,k2=0.,k3=0.,k4=0.,k5=0.,k6=0.,p1=0.,p2=0.)
    cache={}
    a=m.rectify_pair(rgb,d,k,dist,map_cache=cache)
    b=m.rectify_pair(rgb,d,k,dist,map_cache=cache)
    c=m.rectify_pair(rgb,d,k,dist)
    assert len(cache)==1 and np.isnan(b[1][4,4])
    np.testing.assert_array_equal(a[0],c[0]);np.testing.assert_allclose(b[1],c[1],equal_nan=True)
    changed=k.copy();changed[0,0]=120
    m.rectify_pair(rgb,d,changed,dist,map_cache=cache)
    assert len(cache)==2

def test_zero_distortion_aligned_depth_is_not_remapped_with_color():
    import numpy as np
    k=np.array([[10.,0,10.],[0,10.,10.],[0,0,1.]])
    rgb=np.full((20,20,3),128,np.uint8)
    d=np.arange(400,dtype=np.float32).reshape(20,20);d[5,5]=np.nan
    color=dict(model='BROWN_CONRADY',k1=.4,k2=0.,k3=0.,k4=0.,k5=0.,k6=0.,p1=0.,p2=0.)
    depth=dict(color,k1=0.)
    _,correct=m.rectify_pair(rgb,d,k,color,depth_distortion=depth)
    _,old=m.rectify_pair(rgb,d,k,color)
    np.testing.assert_allclose(correct,d,equal_nan=True)
    assert not np.allclose(old,d,equal_nan=True)
