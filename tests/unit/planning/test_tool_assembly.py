import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.tool_assembly import attach_tool_poses


def test_noncommuting_mount_and_local_pose():
    a=np.eye(4);a[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]];a[:3,3]=[1,2,3]
    b=np.eye(4);b[:3,:3]=np.diag([1,-1,-1]);b[:3,3]=[0,0,.002]
    c=np.eye(4);c[:3,3]=[.1,0,.02]
    tip=RigidTransform('base','tip',a,'synthetic');mount=RigidTransform('tip','palm',b,'synthetic');local=RigidTransform('palm','finger',c,'synthetic')
    r=attach_tool_poses(tip,mount,{'finger':local})['finger']
    np.testing.assert_allclose(r.matrix,a@b@c)
    assert not r.approved
    with pytest.raises(ValueError):attach_tool_poses(tip,mount,{'wrong':local})
