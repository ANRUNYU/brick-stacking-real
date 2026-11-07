import importlib.util
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('head_probe',Path(__file__).parents[2]/'tools/c_head_camera_probe.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

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
