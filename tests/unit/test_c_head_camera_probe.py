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
