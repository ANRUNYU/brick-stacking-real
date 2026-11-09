import numpy as np
import pytest
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics


def test_fixed_tip_and_rpy_after_revolute(tmp_path):
    p=tmp_path/'chain.urdf'
    p.write_text('''<robot name="test"><link name="base"/><link name="joint"/><link name="tip"/>
    <joint name="q" type="revolute"><parent link="base"/><child link="joint"/><axis xyz="0 0 1"/><origin xyz="1 0 0"/></joint>
    <joint name="fixed" type="fixed"><parent link="joint"/><child link="tip"/><origin xyz="1 0 0" rpy="0 0 1.5707963267948966"/></joint></robot>''')
    t,report=urdf_forward_kinematics(p,{'q':np.pi/2},base_frame='base',tip_frame='tip')
    np.testing.assert_allclose(t.matrix[:3,3],[1,1,0],atol=1e-12)
    np.testing.assert_allclose(t.matrix[:3,:3],np.diag([-1,-1,1]),atol=1e-12)
    assert not t.approved and report['collision_geometry_count']==0
    for bad in ({},{'J1':0},{'q':float('nan')}):
        with pytest.raises(ValueError): urdf_forward_kinematics(p,bad,base_frame='base',tip_frame='tip')
    with pytest.raises(ValueError): urdf_forward_kinematics(p,{'q':0},base_frame='unknown',tip_frame='tip')
