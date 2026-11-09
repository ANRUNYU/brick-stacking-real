import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.joint_trajectory import JointLimits
from brick_stacking.planning.numerical_ik import solve_pose_ik,rotation_log


def fk(q):
    c,s=np.cos(q[0]),np.sin(q[0]);m=np.eye(4)
    m[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]];m[:3,3]=[c,s,0]
    return RigidTransform('base','tip',m,'synthetic')


def solve(t,seed=[0.]):
    return solve_pose_ik(fk,t,seed,JointLimits(('J1',),(-2.,),(2.,),(1.,),(1.,),'mock','synthetic'),position_tolerance_m=1e-5,rotation_tolerance_rad=1e-5,orientation_weight_m_per_rad=.1,damping=.01,max_step_rad=.2,max_iterations=100,difference_step_rad=1e-6)


def test_known_target_independent_fk_residual():
    r=solve(fk([.7]))
    assert r['ik']=='PASS' and not r['motion_enabled']
    np.testing.assert_allclose(fk(r['positions_rad']).matrix,fk([.7]).matrix,atol=1e-5)
    assert r['full_collision']=='UNKNOWN' and r['trajectory']=='NOT_GENERATED'


def test_impossible_translation_returns_local_failure():
    m=fk([0.]).matrix.copy();m[2,3]=10
    r=solve(RigidTransform('base','tip',m,'synthetic'))
    assert r['ik']=='FAIL' and r['positions_rad'] is None


def test_bad_seed_or_frame_rejected():
    with pytest.raises(ValueError): solve(fk([0.]),[3.])
    with pytest.raises(ValueError): solve(RigidTransform('world','tip',np.eye(4),'synthetic'))


def test_pi_rotation_log():
    assert np.linalg.norm(rotation_log(np.diag([1,-1,-1])))==pytest.approx(np.pi)
