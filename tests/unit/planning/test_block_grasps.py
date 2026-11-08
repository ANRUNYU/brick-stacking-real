import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.block_grasps import cube_face_grasps


def generate(m, approach):
    return cube_face_grasps(RigidTransform('world','block',m,'synthetic'),edge_m=.05,finger_side_clearance_m=.005,approach_world=approach,pregrasp_distance_m=.08,geometry_version='synthetic-1')


def test_opposed_50mm_contacts_and_geometric_frame_not_tcp():
    r=generate(np.eye(4),[0,0,1]);assert len(r['candidates'])==2
    for c in r['candidates']:
        p,q=[x['point_world_m'] for x in c['contacts']]
        assert np.linalg.norm(np.array(p)-q)==pytest.approx(.05)
        assert c['required_opening_m']==pytest.approx(.06)
        np.testing.assert_allclose(c['pregrasp'].matrix[:3,3]-c['target'].matrix[:3,3],[0,0,.08])
        assert c['flange_goal'] is None and c['hand_preset'] is None and c['full_collision']=='UNKNOWN'


def test_rotated_world_does_not_assume_world_up():
    r=np.array([[0,0,1],[1,0,0],[0,1,0]])
    m=np.eye(4);m[:3,:3]=r;m[:3,3]=[.1,.2,.3]
    out=generate(m,r[:,2]);assert [c['face_axis_block'] for c in out['candidates']]==[0,1]
    for c in out['candidates']:
        np.testing.assert_allclose(c['target'].matrix[:3,2],r[:,2])
        np.testing.assert_allclose(np.mean([p['point_world_m'] for p in c['contacts']],axis=0),m[:3,3])
        assert np.linalg.det(c['target'].matrix[:3,:3])==pytest.approx(1)


def test_no_orthogonal_faces_reports_rejection_not_silent_direction_change():
    r=generate(np.eye(4),np.ones(3)/np.sqrt(3));assert not r['candidates'] and len(r['rejected'])==3


def test_bad_dimension_and_nonunit_approach_rejected():
    with pytest.raises(ValueError):generate(np.eye(4),[0,0,2])
    with pytest.raises(ValueError):
        cube_face_grasps(RigidTransform('w','b',np.eye(4),'synthetic'),edge_m=.05,finger_side_clearance_m=-.001,approach_world=[0,0,1],pregrasp_distance_m=.08,geometry_version='x')
