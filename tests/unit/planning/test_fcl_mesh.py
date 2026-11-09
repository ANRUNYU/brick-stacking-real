import numpy as np
import pytest
pytest.importorskip('fcl')
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.fcl_mesh import FclMeshChecker

V=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
T=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]],int)

def pose(name,x):
    m=np.eye(4);m[0,3]=x
    return RigidTransform('world',name,m,'synthetic')


def test_disjoint_and_intersecting_meshes_and_nonzero_clearance():
    checker=FclMeshChecker({'a':(V,T),'b':(V,T)},model_version='synthetic')
    clear=checker.check_poses({'a':pose('a',0),'b':pose('b',2)},exclusions={},min_clearance_m=0.)
    assert clear['pairs'][0]['distance_m']==pytest.approx(1.)
    assert clear['sampled_status']=='PASS' and clear['status']=='UNKNOWN'
    assert not clear['motion_enabled']
    hit=checker.check_poses({'a':pose('a',0),'b':pose('b',.2)},exclusions={},min_clearance_m=0.)
    assert hit['status']=='FAIL' and hit['pairs'][0]['surface_intersection']
    margin=checker.check_poses({'a':pose('a',0),'b':pose('b',2)},exclusions={},min_clearance_m=1.1)
    assert margin['status']=='FAIL'


def test_frame_names_missing_poses_and_bad_exclusions_rejected():
    checker=FclMeshChecker({'a':(V,T),'b':(V,T)},model_version='test')
    with pytest.raises(ValueError): checker.check_poses({'a':pose('a',0)},exclusions={},min_clearance_m=0)
    with pytest.raises(ValueError): checker.check_poses({'a':pose('a',0),'b':pose('b',2)},exclusions={('a','b'):''},min_clearance_m=0)


def test_bad_triangle_index_rejected():
    with pytest.raises(ValueError): FclMeshChecker({'a':(V,np.array([[0,1,99]]))},model_version='test')

def test_joint_path_middle_surface_collision_not_just_endpoints():
    from brick_stacking.planning.joint_trajectory import JointLimits,build_offline_trajectory
    checker=FclMeshChecker({'a':(V,T),'b':(V,T)},model_version='triangles')
    trajectory=build_offline_trajectory([[2.],[-2.]],JointLimits(('J1',),(-3.,),(3.,),(1.,),(1.,),'synthetic','synthetic'),scene_version='scene',calibration_version='mock',clock_domain='mock',epoch='1',state_stamp_s=1,now_s=1,max_age_s=.1,start_tolerance_rad=.01,expected_start_rad=[2.])
    # Synthetic q -> translation for backend testing, not a real revolute FK.
    result=checker.check_trajectory(trajectory,lambda q:{'a':pose('a',0),'b':pose('b',q[0])},source_model_version='synthetic',scene_version='scene',exclusions={},min_clearance_m=0,sample_dt_s=.05,missing_coverage=['robot environment'])
    assert result['status']=='FAIL' and result['samples_checked']>1
    assert result['contacts'][0]['time_from_segment_start_s']>0
    assert not result['motion_enabled']
    with pytest.raises(ValueError): checker.check_trajectory(trajectory,lambda q:{},source_model_version='old',scene_version='scene',exclusions={},min_clearance_m=0,sample_dt_s=.05,missing_coverage=[])
