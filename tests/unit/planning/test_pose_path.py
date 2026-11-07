import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.joint_trajectory import JointLimits
from brick_stacking.planning.pose_path import plan_pose_path


def fk(q):
    c,s=np.cos(q[0]),np.sin(q[0]);m=np.eye(4)
    m[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]];m[:3,3]=[c,s,0]
    return RigidTransform('base','tcp',m,'synthetic')


def plan(targets,now=1):
    limits=JointLimits(('J1',),(-2.,),(2.,),(.2,),(.3,),'synthetic','synthetic')
    settings=dict(position_tolerance_m=1e-5,rotation_tolerance_rad=1e-5,orientation_weight_m_per_rad=.1,damping=.01,max_step_rad=.2,max_iterations=100,difference_step_rad=1e-6)
    context=dict(scene_version='mock',calibration_version='synthetic',clock_domain='mock',epoch='1',state_stamp_s=1,now_s=now,max_age_s=.1,start_tolerance_rad=.01,expected_start_rad=[0.])
    return plan_pose_path(fk,targets,[0.],limits,ik_settings=settings,trajectory_context=context)


def test_ordered_targets_include_current_to_first_target():
    r=plan([fk([.3]),fk([.6])])
    assert r['ik']=='PASS' and r['trajectory_limits']=='PASS'
    assert len(r['trajectory']['segments'])==2
    assert r['joint_waypoints_rad'][0]==[0.]
    for q,target in zip(r['joint_waypoints_rad'][1:],[fk([.3]),fk([.6])]):
        np.testing.assert_allclose(fk(q).matrix,target.matrix,atol=1e-5)
    assert not r['motion_enabled'] and r['full_collision']=='UNKNOWN'


def test_ik_failure_cannot_produce_partial_trajectory():
    m=fk([0.]).matrix.copy();m[2,3]=1
    r=plan([fk([.3]),RigidTransform('base','tcp',m,'synthetic')])
    assert r['ik']=='FAIL' and r['failed_target_index']==1 and r['trajectory'] is None


def test_ik_success_is_separate_from_stale_state_rejection():
    r=plan([fk([.3])],now=2)
    assert r['ik']=='PASS' and r['trajectory_limits']=='FAIL' and r['trajectory'] is None
