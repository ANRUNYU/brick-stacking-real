import numpy as np
import pytest
from brick_stacking.planning.joint_trajectory import JointLimits, build_offline_trajectory, sample_segment


def limits():
    return JointLimits(('J1','J2'),(-1,-2),(1,2),(.2,.3),(.4,.5),'synthetic-model-1','synthetic')


def build(**overrides):
    kw=dict(scene_version='mock-scene',calibration_version='synthetic-cal',clock_domain='host_monotonic',epoch='test-1',state_stamp_s=10.,now_s=10.01,max_age_s=.1,start_tolerance_rad=.01,expected_start_rad=[0,0])
    kw.update(overrides)
    return build_offline_trajectory([[0,0],[.5,-1],[0,.2]],limits(),**kw)


def test_interpolation_bounds_endpoints_and_derivatives():
    result=build()
    assert not result['motion_enabled'] and result['full_collision']=='UNKNOWN'
    assert result['ik']=='NOT_CHECKED'
    for segment in result['segments']:
        duration=segment['duration_s']
        for t in np.linspace(0,duration,1001):
            q,v,a=sample_segment(segment,t)
            assert np.all(np.abs(v)<=limits().velocity_rad_s)
            assert np.all(np.abs(a)<=limits().acceleration_rad_s2)
            assert np.all(q>=limits().lower_rad) and np.all(q<=limits().upper_rad)
        for t,key in [(0,'start_rad'),(duration,'end_rad')]:
            q,v,a=sample_segment(segment,t)
            np.testing.assert_allclose(q,segment[key],atol=1e-12)
            np.testing.assert_allclose(v,0,atol=1e-12)
            np.testing.assert_allclose(a,0,atol=1e-12)


@pytest.mark.parametrize('change',[{'state_stamp_s':9.},{'clock_domain':''},{'epoch':''},{'calibration_version':''},{'state_stamp_s':11.},{'now_s':float('nan')},{'expected_start_rad':[.5,0]},{'max_age_s':None}])
def test_invalid_context(change):
    with pytest.raises(ValueError): build(**change)


@pytest.mark.parametrize('names,lower,velocity',[(('J1','J1'),(-1,-2),(.2,.3)),(('J1','J2'),(None,-2),(.2,.3)),(('J1','J2'),(-1,-2),(0,.3))])
def test_unknown_or_invalid_limits(names,lower,velocity):
    with pytest.raises(ValueError): JointLimits(names,lower,(1,2),velocity,(.4,.5),'mock','synthetic')


def test_position_limit_and_stationary_rejection():
    for q in ([[0,0],[2,0]],[[0,0],[0,0]]):
        with pytest.raises(ValueError):
            build_offline_trajectory(q,limits(),scene_version='s',calibration_version='c',clock_domain='host',epoch='e',state_stamp_s=1,now_s=1,max_age_s=.1,start_tolerance_rad=.01,expected_start_rad=[0,0])
