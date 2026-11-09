import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.approach_candidates import generate_approaches


def pose(target,source,xyz):
    m=np.eye(4);m[:3,3]=xyz;return RigidTransform(target,source,m,'synthetic')


def test_approaches_use_explicit_world_directions_and_tcp_offset():
    r=generate_approaches(pose('world','block',[0,0,.2]),pose('world','block',[.3,0,.2]),pose('tcp','block',[0,0,-.1]),directions_world=[[0,0,1],[1,0,0]],clearance_m=.03,scene_version='mock')
    assert len(r)==2 and r[0]['candidate_id']!=r[1]['candidate_id']
    np.testing.assert_allclose(r[0]['targets'][0].matrix[:3,3],[0,0,.33])
    np.testing.assert_allclose(r[1]['targets'][0].matrix[:3,3],[.03,0,.3])
    assert all(not c['motion_enabled'] and c['full_collision']=='UNKNOWN' for c in r)


def test_direction_normalization_and_frame_guesses_refused():
    a=pose('world','block',[0,0,0]);o=pose('tcp','block',[0,0,0])
    for directions in ([[0,0,0]],[[0,0,2]],[[0,0,1],[0,0,1]]):
        with pytest.raises(ValueError):generate_approaches(a,a,o,directions_world=directions,clearance_m=.03,scene_version='mock')
