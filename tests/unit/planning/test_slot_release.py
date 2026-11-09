import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.scene.stacking_slots import build_stacking_slots
from brick_stacking.planning.slot_release import slot_release_geometry


def test_ten_slots_release_height_and_table_axis():
    slots=build_stacking_slots(edge_m=.05,layers=[4,3,2,1],colors_by_layer=['red','yellow','blue','green'],center_xy_m=[0,0],yaw_rad=0,frame_id='table')
    assert len(slots)==10
    m=np.eye(4);m[:3,:3]=[[1,0,0],[0,0,-1],[0,1,0]];m[:3,3]=[.1,.2,.3]
    table=RigidTransform('world','table',m,'synthetic')
    o=np.eye(4);o[2,3]=-.1
    offset=RigidTransform('tcp','block',o,'synthetic')
    for slot in slots:
        result=slot_release_geometry(slot,table,offset,yaw_rad=0,clearance_m=.03,scene_version='mock')
        assert slot.center_m[2]==pytest.approx((slot.layer+.5)*.05)
        expected=table.apply(slot.center_m)
        np.testing.assert_allclose(result['release_tcp'].matrix[:3,3],expected+[0,-.1,0],atol=1e-12)
        np.testing.assert_allclose(result['approach_tcp'].matrix[:3,3]-result['release_tcp'].matrix[:3,3],[0,-.03,0],atol=1e-12)
        assert not result['motion_enabled'] and result['full_collision']=='UNKNOWN'
        assert len(result['supports'])==(0 if slot.layer==0 else 2)
