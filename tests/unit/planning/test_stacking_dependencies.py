import math
import pytest
from brick_stacking.scene.stacking_slots import build_stacking_slots
from brick_stacking.scene.scene_manager import SceneManager


def make_slots(edge=.05, yaw=0):
    return build_stacking_slots(edge_m=edge, layers=[4, 3, 2, 1], colors_by_layer=["red", "yellow", "blue", "green"],
        center_xy_m=[0, 0], yaw_rad=yaw, frame_id="fixture_table")


def test_slots_scale_rotate_and_depend_on_two_lower():
    slots = make_slots(.08, math.pi / 2)
    assert len(slots) == 10
    assert slots[0].center_m[1] == pytest.approx(-.12)
    assert slots[0].center_m[2] == .04
    assert slots[-1].center_m[2] == pytest.approx(.28)
    assert slots[4].supports == ("L0_0", "L0_1")


def test_no_upper_target_before_support_and_commit_after_verification_only():
    manager = SceneManager(make_slots())
    assert len(manager.ready_slots()) == 4
    with pytest.raises(ValueError): manager.reserve("L1_0", "upper")
    manager.reserve("L0_0", "red0")
    with pytest.raises(ValueError): manager.commit_verified("L0_0", "red0")
    manager.mark_unverified("L0_0")
    with pytest.raises(ValueError): manager.cancel_before_pick("L0_0")
    manager.commit_verified("L0_0", "red0")
    manager.reserve("L0_1", "red1")
    manager.mark_unverified("L0_1")
    manager.commit_verified("L0_1", "red1")
    assert "L1_0" in {s.slot_id for s in manager.ready_slots()}
    with pytest.raises(ValueError): manager.reserve("L0_2", "red0")


def test_layer_graph_validation():
    with pytest.raises(ValueError):
        build_stacking_slots(edge_m=.05, layers=[4, 2], colors_by_layer=["red", "blue"],
                              center_xy_m=[0, 0], yaw_rad=0, frame_id="table")

def test_optional_gap_preserves_centered_support_geometry():
    slots=build_stacking_slots(edge_m=.05,gap_m=.002,layers=[4,3,2,1],colors_by_layer=['red','yellow','blue','green'],center_xy_m=[0,0],yaw_rad=0,frame_id='table')
    assert slots[1].center_m[0]-slots[0].center_m[0]==pytest.approx(.052)
    assert slots[4].center_m[0]==pytest.approx((slots[0].center_m[0]+slots[1].center_m[0])/2)
    assert slots[4].supports==('L0_0','L0_1')
    assert slots[-1].center_m[2]==pytest.approx(.175)
    for gap in (-.001,.05,float('nan')):
        with pytest.raises(ValueError):build_stacking_slots(edge_m=.05,gap_m=gap,layers=[2,1],colors_by_layer=['red','yellow'],center_xy_m=[0,0],yaw_rad=0,frame_id='table')
