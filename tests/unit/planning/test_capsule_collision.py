import numpy as np
import pytest
from brick_stacking.planning.capsule_collision import Capsule,segment_distance,sampled_capsule_check
from brick_stacking.planning.joint_trajectory import JointLimits,build_offline_trajectory


def trajectory():
    return build_offline_trajectory([[-.5],[.5]],JointLimits(('J1',),(-1,),(1,),(1,),(1,),'model','synthetic'),scene_version='scene',calibration_version='synthetic',clock_domain='mock',epoch='1',state_stamp_s=1,now_s=1,max_age_s=.1,start_tolerance_rad=.01,expected_start_rad=[-.5])


def check(geometry,obstacles,**kw):
    args=dict(frame_id='base',model_version='model',scene_version='scene',collision_model_version='synthetic-capsules',sample_dt_s=.01,self_exclusions={},missing_coverage=['camera','fingers'])
    args.update(kw)
    return sampled_capsule_check(trajectory(),geometry,obstacles,**args)


def test_middle_pose_contact_detected_even_when_endpoints_clear():
    # Synthetic geometry intentionally maps test q to x, not a real arm model.
    geometry=lambda q:[Capsule('tool',(q[0],0,.2),(q[0],0,.3),.02,'base')]
    obstacle=dict(name='sphere',type='sphere',center_m=[0,0,.25],radius_m=.02,frame_id='base')
    r=check(geometry,[obstacle])
    assert r['status']=='FAIL' and r['contacts'][0]['time_from_segment_start_s']>0


def test_clear_samples_remain_unknown_continuously():
    r=check(lambda q:[Capsule('arm',(0,0,.2),(0,0,.3),.01,'base')],[dict(name='table',type='plane',normal=[0,0,1],offset_m=0,frame_id='base')])
    assert r['sampled_status']=='PASS' and r['status']=='UNKNOWN' and not r['motion_enabled']


def test_self_contact_requires_explicit_exclusion_reason():
    geometry=lambda q:[Capsule('a',(0,0,0),(0,0,.2),.01,'base'),Capsule('b',(0,0,.2),(0,0,.4),.01,'base')]
    assert check(geometry,[])['status']=='FAIL'
    assert check(geometry,[],self_exclusions={('a','b'):'synthetic installation seam'})['status']=='UNKNOWN'
    with pytest.raises(ValueError): check(geometry,[],self_exclusions={('a','b'):''})


def test_degenerate_parallel_and_crossing_segments():
    assert segment_distance([0,0,0],[0,0,0],[1,0,0],[1,0,0])==pytest.approx(1)
    assert segment_distance([0,0,0],[1,0,0],[0,1,0],[1,1,0])==pytest.approx(1)
    assert segment_distance([-1,0,0],[1,0,0],[0,-1,0],[0,1,0])==pytest.approx(0)


def test_unknown_radius_stale_model_and_empty_geometry_rejected():
    with pytest.raises(ValueError): Capsule('a',(0,0,0),(1,0,0),0,'base')
    with pytest.raises(ValueError): check(lambda q:[],[])
    with pytest.raises(ValueError): check(lambda q:[],[],model_version='old')
