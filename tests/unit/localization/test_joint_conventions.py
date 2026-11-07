import numpy as np
import pytest
from brick_stacking.localization.joint_conventions import JointConventionMap


def test_signed_mapping_and_asymmetric_joint2_limits():
    m=JointConventionMap(('L1_Joint','L2_Joint'),(-1,-1),(0,0),'sdk','vendor')
    assert m.map_positions({'L1_Joint':.2,'L2_Joint':.3},source_model_version='sdk',target_model_version='vendor')=={'L1_Joint':-.2,'L2_Joint':-.3}
    lo,hi=m.map_bounds([-2.91,-.07],[2.91,3.2])
    np.testing.assert_allclose(lo,[-2.91,-3.2]);np.testing.assert_allclose(hi,[2.91,.07])


def test_wrong_versions_and_unknown_joint_values_rejected():
    m=JointConventionMap(('J1',),(-1,),(0,),'sdk','vendor')
    for q,src in [({'J1':.1},'old'),({'other':0},'sdk'),({'J1':float('nan')},'sdk')]:
        with pytest.raises(ValueError): m.map_positions(q,source_model_version=src,target_model_version='vendor')
