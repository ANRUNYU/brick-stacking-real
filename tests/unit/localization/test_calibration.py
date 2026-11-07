import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.calibration import solve_point_pairs, error_report, solve_pivot_tcp, tcp_target_for_block


def tf(target, source, r=np.eye(3), t=(0,0,0)):
    m=np.eye(4); m[:3,:3]=r; m[:3,3]=t
    return RigidTransform(target,source,m,'synthetic')


def test_fit_rotation_translation_and_heldout_error():
    a=np.array([[0,0,0],[.1,0,0],[0,.2,0],[0,0,.3]])
    expected=tf('world','camera', [[0,-1,0],[1,0,0],[0,0,1]], [.4,.2,.1])
    fit=solve_point_pairs(a, expected.apply(a), source_frame='camera',target_frame='world',candidate_id='synthetic-1')
    np.testing.assert_allclose(fit.matrix,expected.matrix,atol=1e-12)
    b=a+.01
    report=error_report(fit,b,expected.apply(b)+[.003,.004,0])
    assert report['rmse_m']==pytest.approx(.005)
    assert not fit.approved


@pytest.mark.parametrize('points', [np.zeros((4,3)), np.ones((3,3)), np.full((4,3),np.nan), [[0,0,0],[1,0,0],[2,0,0],[3,0,0]]])
def test_bad_samples(points):
    with pytest.raises(ValueError):
        solve_point_pairs(points,points,source_frame='a',target_frame='b',candidate_id='x')


def test_pivot_and_unobservable_orientation():
    rs=[np.eye(3),np.array([[1,0,0],[0,0,-1],[0,1,0]]),np.array([[0,0,1],[0,1,0],[-1,0,0]]),np.diag([-1,-1,1])]
    p=np.array([.01,.02,.12]); pivot=np.array([.3,.2,.4])
    samples=[tf('base','flange',r,pivot-r@p) for r in rs]
    result=solve_pivot_tcp(samples)
    np.testing.assert_allclose(result['tcp_translation_flange_m'],p,atol=1e-12)
    assert result['tcp_orientation_xyzw'] is None
    with pytest.raises(ValueError): solve_pivot_tcp([samples[0]]*4)


def test_offset_direction():
    result=tcp_target_for_block(tf('world','block',t=[1,2,3]),tf('tcp','block',t=[0,0,.1]))
    assert result.source_frame=='tcp'
    np.testing.assert_allclose(result.matrix[:3,3],[1,2,2.9])
