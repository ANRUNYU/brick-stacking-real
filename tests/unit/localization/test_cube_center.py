import cv2
import numpy as np
import pytest
from brick_stacking.localization.cube_center import center_from_faces


def faces():
    # Camera sees three faces. Columns point from center towards the camera octant.
    r=cv2.Rodrigues(np.array([.6,-.5,.2]))[0]
    # Rotate an orthogonal basis so camera direction has negative projection on all.
    z=np.array([1.,1.,1.]);z/=np.linalg.norm(z)
    x=np.cross([0,1,0],z);x/=np.linalg.norm(x);y=np.cross(z,x)
    basis=np.stack((x,y,z))
    center=np.array([0.,0.,.8]);rng=np.random.default_rng(5);result=[]
    for i in range(3):
        points=np.zeros((80,3));points[:,i]=-.025
        other=[j for j in range(3) if j!=i];points[:,other]=rng.uniform(-.02,.02,(80,2))
        points=points@basis.T+center
        result.append((points[:50],points[50:]))
    return result,center


def solve(points):return center_from_faces(points,edge_m=.05,plane_threshold_m=.001,min_inlier_ratio=.9,max_holdout_m=.002,max_normal_dot=.1,max_condition_number=10)


def test_center_independent_of_face_identity_or_cube_orientation():
    f,c=faces();point,report=solve(f)
    np.testing.assert_allclose(point,c,atol=1e-10)
    point,_=solve([f[2],f[0],f[1]]);np.testing.assert_allclose(point,c,atol=1e-10)
    assert report['orientation_xyzw'] is None and report['consistency']=='PASS'


def test_repeated_same_face_rejected():
    f,_=faces()
    with pytest.raises(ValueError,match='perpendicular|ill-conditioned'):solve([f[0]]*3)


def test_holdout_error_not_removed():
    f,_=faces();train,check=f[0];check=check.copy();check[0]+=[.005,.005,.005];f[0]=(train,check)
    try:
        _,r=solve(f);assert r['consistency']=='FAIL'
    except ValueError as exc:assert 'bounded' in str(exc)


def test_missing_third_face_not_guessed():
    f,_=faces()
    with pytest.raises(ValueError):solve(f[:2])


def test_constrained_model_keeps_independent_holdout_errors():
    f,c=faces()
    kwargs=dict(edge_m=.05,plane_threshold_m=.001,min_inlier_ratio=.9,max_holdout_m=.002,max_normal_dot=.1,max_condition_number=10,regular_cube_constraint=True)
    point,r=center_from_faces(f,**kwargs)
    np.testing.assert_allclose(point,c,atol=1e-9);assert r['consistency']=='PASS'
    train,check=f[0];check=check.copy();check[0]+=[.005,.005,.005];f[0]=(train,check)
    try:
        _,r=center_from_faces(f,**kwargs);assert r['consistency']=='FAIL'
    except ValueError as exc:assert 'bounded' in str(exc)
