import numpy as np
import pytest
from brick_stacking.planning.obj_geometry import obj_triangles


def test_obj_negative_indices_and_texture_fields():
    v,t=obj_triangles(b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3/1 -2/2 -1/3\n')
    np.testing.assert_array_equal(t,[[0,1,2]])
    assert v.shape==(3,3)


@pytest.mark.parametrize('face',[b'f 0 1 2',b'f 1 2 99',b'f 1 2 3 1'])
def test_obj_invalid_or_untriangulated_faces_refused(face):
    with pytest.raises(ValueError):obj_triangles(b'v 0 0 0\nv 1 0 0\nv 0 1 0\n'+face)
