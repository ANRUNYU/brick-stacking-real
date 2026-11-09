import numpy as np
import pytest
from brick_stacking.localization.table_plane import TablePlane
from brick_stacking.localization.table_coordinates import table_coordinates,resting_cube_geometry


def plane():return TablePlane((0.,0.,-1.),1.,1.,0.)


def test_observed_table_axes_are_right_handed_and_origin_on_plane():
    t=table_coordinates(plane(),[0.,0.,1.],camera_frame='camera',table_frame='table',version='synthetic')
    np.testing.assert_allclose(t.apply([0.,0.,0.]),[0,0,1])
    np.testing.assert_allclose(t.inverse().apply([.2,-.3,.975]),[.2,.3,.025])
    assert not t.approved and t.target_frame=='camera' and t.source_frame=='table'


def test_known_cube_dimensions_and_resting_model_do_not_infer_robot_base():
    k=np.array([[1000.,0,320.],[0,1000.,240.],[0,0,1.]])
    uv=np.array([[-.025,-.025],[.025,-.025],[.025,.025],[-.025,.025]])/.95*1000+[320,240]
    t,r=resting_cube_geometry(plane(),uv,k,edge_m=.05,camera_frame='camera',block_frame='cube',version='synthetic',rests_on_table=True)
    np.testing.assert_allclose(t.matrix[:3,3],[0,0,.975],atol=1e-12)
    np.testing.assert_allclose(r['observed_corner_edges_m'],.05)
    assert r['base_transform'] is None and not r['approved']


@pytest.mark.parametrize('bad',['grazing','behind','nonunit'])
def test_invalid_table_frame_rejected(bad):
    p=plane();ray=[0.,0.,1.]
    if bad=='grazing':ray=[1.,0.,0.]
    elif bad=='behind':ray=[0.,0.,-1.]
    else:p=TablePlane((0,0,-2),1,1,0)
    with pytest.raises(ValueError):table_coordinates(p,ray,camera_frame='camera',table_frame='table',version='synthetic')
