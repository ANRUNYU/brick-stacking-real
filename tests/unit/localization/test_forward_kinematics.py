import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.forward_kinematics import RevoluteJoint, forward_kinematics


def chain():
    def origin(a,b,t):
        m=np.eye(4);m[:3,3]=t
        return RigidTransform(a,b,m,'synthetic')
    return [RevoluteJoint('J1',origin('base','j1',[0,0,0]),(0,0,1)),
            RevoluteJoint('J2',origin('j1','j2',[1,0,0]),(0,0,1)),
            RevoluteJoint('J3',origin('j2','tip',[1,0,0]),(0,0,1))]


def test_planar_two_link_independent_geometry():
    fk=forward_kinematics(chain(),{'J1':np.pi/2,'J2':-np.pi/2,'J3':0},model_version='synthetic-1')
    np.testing.assert_allclose(fk.matrix[:3,3],[1,1,0],atol=1e-12)
    np.testing.assert_allclose(fk.matrix[:3,:3],np.eye(3),atol=1e-12)
    assert fk.target_frame=='base' and fk.source_frame=='tip' and not fk.approved


@pytest.mark.parametrize('q',[{'J1':0},{'J1':0,'J2':0,'J3':float('nan')},{'J1':0,'J2':0,'J3':0,'J4':0}])
def test_bad_joint_mapping(q):
    with pytest.raises(ValueError): forward_kinematics(chain(),q,model_version='mock')


def test_chain_frame_break_and_axis_rejected():
    c=chain()
    with pytest.raises(ValueError): forward_kinematics([c[1],c[0]],{'J1':0,'J2':0},model_version='mock')
    with pytest.raises(ValueError): RevoluteJoint('bad',c[0].origin,(0,0,2))
