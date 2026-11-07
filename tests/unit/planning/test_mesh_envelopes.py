import struct
import numpy as np
import pytest
from brick_stacking.planning.mesh_envelopes import stl_vertices,capsule_envelope
from brick_stacking.planning.capsule_collision import segment_distance


def test_binary_mesh_parser_and_truncation():
    data=bytes(80)+struct.pack('<I',1)+struct.pack('<12fH',0,0,1,0,0,0,1,0,0,0,1,0,0)
    np.testing.assert_array_equal(stl_vertices(data),[[0,0,0],[1,0,0],[0,1,0]])
    with pytest.raises(ValueError): stl_vertices(data[:-1])
    with pytest.raises(ValueError): stl_vertices(b'version https://git-lfs.github.com/spec/v1')


def test_envelope_contains_all_corners_and_explicit_padding():
    points=np.array([[x,y,z] for x in (-1,1) for y in (-.2,.2) for z in (-.1,.1)])
    capsule=capsule_envelope('link',points,frame_id='link',padding_m=.005)
    for point in points:
        assert segment_distance(capsule.start_m,capsule.end_m,point,point)<=capsule.radius_m+1e-12
    assert capsule.radius_m==pytest.approx(np.sqrt(.05)+.005)
    with pytest.raises(ValueError): capsule_envelope('link',points,frame_id='link',padding_m=-1)

def test_loader_rejects_wrong_urdf_hash(tmp_path):
    import json
    from brick_stacking.planning.mesh_envelopes import load_p7_capsule_envelopes
    (tmp_path/'arm.urdf').write_text('<robot name="x"/>')
    (tmp_path/'asset_lock.json').write_text(json.dumps(dict(urdf_sha256='wrong',meshes=[])))
    with pytest.raises(ValueError,match='checksum'): load_p7_capsule_envelopes(tmp_path,padding_m=0)


def test_loader_rejects_unlocked_mesh(tmp_path):
    import json,hashlib
    from brick_stacking.planning.mesh_envelopes import load_p7_capsule_envelopes
    xml=b'<robot name="x"><link name="link"><collision><geometry><mesh filename="../unlocked.STL"/></geometry></collision></link></robot>'
    (tmp_path/'arm.urdf').write_bytes(xml)
    (tmp_path/'asset_lock.json').write_text(json.dumps(dict(urdf_sha256=hashlib.sha256(xml).hexdigest(),meshes=[])))
    with pytest.raises(ValueError,match='unlocked'): load_p7_capsule_envelopes(tmp_path,padding_m=0)
