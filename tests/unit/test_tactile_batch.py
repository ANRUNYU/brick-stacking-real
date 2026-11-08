import importlib.util
from pathlib import Path
import sys
import pytest


def load(name):
    s=importlib.util.spec_from_file_location(name,Path(__file__).parents[2]/('tools/'+name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


sys.modules.setdefault('c_o6_index_probe',load('c_o6_index_probe'))
m=load('c_o6_tactile_probe')


def frame(index,prefix=0xB1,value=7):return bytes([prefix,index<<4,value,value,value,value])


def test_requires_start_and_all_ten_frames_not_mixed_old_tail():
    b=m.TactileBatch(0xB1)
    assert b.add(frame(5)) is None
    assert b.add(frame(0)) is None
    for i in range(1,9):assert b.add(frame(i)) is None
    assert b.add(frame(9))==[[7]*4 for _ in range(10)]
    assert b.add(frame(9)) is None


def test_wrong_finger_and_invalid_fragment_not_accepted():
    b=m.TactileBatch(0xB1)
    assert b.add(frame(0,prefix=0xB2)) is None
    assert b.add(b'\xb1') is None
    assert b.add(frame(10)) is None
    with pytest.raises(ValueError):m.TactileBatch(0x01)


def test_new_start_discards_partial_and_conflicting_duplicate_rejected():
    b=m.TactileBatch(0xB1);b.add(frame(0));b.add(frame(1))
    with pytest.raises(ValueError):b.add(frame(1,value=8))
    b.add(frame(0,value=8))
    for i in range(1,9):b.add(frame(i,value=8))
    assert b.add(frame(9,value=8))==[[8]*4 for _ in range(10)]


@pytest.mark.parametrize('profile',[{}, {'serial_number':'left','tactile':{'present':False}}, {'serial_number':'other','tactile':{'present':True}}])
def test_no_installed_tactile_or_wrong_device_refused_before_read(profile):
    class NoAccess:
        def read(self,*args):raise AssertionError('must reject before any hardware access')
    with pytest.raises(ValueError,match='absent/unverified'):
        m.capture(NoAccess(),'left',capabilities=profile)
