import hashlib
import numpy as np
import pytest
from brick_stacking.localization.joint_conventions import JointConventionMap
from brick_stacking.planning.capsule_collision import Capsule
from brick_stacking.planning.urdf_capsules import MappedUrdfCapsules


def test_proxy_follows_mapped_joint_rotation_and_checks_version(tmp_path):
    p=tmp_path/'test.urdf';p.write_text('<robot name="test"><link name="base"/><link name="link"/><joint name="J1" type="revolute"><parent link="base"/><child link="link"/><axis xyz="0 0 1"/></joint></robot>')
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    mapping=JointConventionMap(('J1',),(-1,),(0,),'source',sha)
    local=[Capsule('body',(1,0,0),(2,0,0),.01,'link')]
    provider=MappedUrdfCapsules(p,local,mapping,base_frame='base',source_model_version='source')
    body=provider.at_source_q([np.pi/2])[0]
    np.testing.assert_allclose(body.start_m,[0,-1,0],atol=1e-12)
    assert body.frame_id=='base'
    p.write_text(p.read_text().replace('0 0 1','0 1 0'))
    with pytest.raises(ValueError,match='changed'): provider.at_source_q([0])
