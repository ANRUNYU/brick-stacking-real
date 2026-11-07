import pytest
from brick_stacking.planning.cartesian_diagnostics import swept_aabb_hit


def test_swept_check_catches_obstacle_between_endpoints():
    assert swept_aabb_hit([0,0,0],[1,0,0],[.01]*3,[.49,-.1,-.1],[.51,.1,.1])
    assert not swept_aabb_hit([0,0,.5],[1,0,.5],[.01]*3,[.49,-.1,-.1],[.51,.1,.1])
    assert swept_aabb_hit([0,0,0],[0,0,0],[.01]*3,[-.1]*3,[.1]*3)
    with pytest.raises(ValueError): swept_aabb_hit([0]*3,[1]*3,[0]*3,[0]*3,[1]*3)

def test_waypoints_keep_ik_and_full_collision_unknown():
    import numpy as np
    from brick_stacking.localization.rigid_transforms import RigidTransform
    from brick_stacking.planning.cartesian_diagnostics import offline_pick_place
    def pose(frame, xyz):
        m=np.eye(4);m[:3,3]=xyz
        return RigidTransform('world',frame,m,'synthetic')
    offset=RigidTransform('tcp','block',np.eye(4),'synthetic')
    result=offline_pick_place(pose('block',[0,0,.2]),pose('block',[.5,0,.2]),offset,clearance_m=.1,half_extent_m=[.01]*3,obstacles=[],scene_version='mock-1')
    assert result['collision_aabb']=='PASS'
    assert result['ik']=='UNKNOWN' and result['full_collision']=='UNKNOWN'
    assert not result['motion_enabled']
    assert [p['phase'] for p in result['waypoints']]==['approach','grasp','lift','transfer','release','retreat']
