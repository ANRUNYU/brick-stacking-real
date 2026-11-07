import numpy as np
import pytest
from brick_stacking.localization.hand_kinematics import resolve_hand_joints,hand_link_poses
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics


def hand(tmp_path):
    p=tmp_path/'hand.urdf';p.write_text('''<robot name="test"><link name="base"/><link name="prox"/><link name="dist"/>
    <joint name="active" type="revolute"><parent link="base"/><child link="prox"/><axis xyz="0 0 1"/><limit lower="0" upper="1"/></joint>
    <joint name="coupled" type="revolute"><parent link="prox"/><child link="dist"/><origin xyz="1 0 0"/><axis xyz="0 0 1"/><limit lower="0" upper=".8"/><mimic joint="active" multiplier=".5" offset=".1"/></joint></robot>''');return p


def test_coupled_angle_and_distal_pose(tmp_path):
    p=hand(tmp_path);q=resolve_hand_joints(p,{'active':.4})
    assert q['coupled']==pytest.approx(.3)
    poses=hand_link_poses(p,{'active':.4},base_frame='base')
    np.testing.assert_allclose(poses['dist'].matrix[:3,3],[np.cos(.4),np.sin(.4),0])
    assert not poses['dist'].approved
    with pytest.raises(ValueError):urdf_forward_kinematics(p,q,base_frame='base',tip_frame='dist')


def test_unknown_raw_values_limit_and_cycle_rejected(tmp_path):
    p=hand(tmp_path)
    for q in ({'raw':[128]}, {'active':255}, {'active':float('nan')}):
        with pytest.raises(ValueError):resolve_hand_joints(p,q)
    text=p.read_text().replace('<limit lower="0" upper="1"/>','<limit lower="0" upper="1"/><mimic joint="coupled"/>');p.write_text(text)
    with pytest.raises(ValueError,match='cyclic'):resolve_hand_joints(p,{})
