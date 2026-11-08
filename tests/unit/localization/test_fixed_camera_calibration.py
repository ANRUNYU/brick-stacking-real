import cv2
import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.fixed_camera_calibration import solve_fixed_camera


def matrix(rot,t):
    m=np.eye(4);m[:3,:3]=cv2.Rodrigues(np.array(rot,dtype=float))[0];m[:3,3]=t;return m


def samples():
    rng=np.random.default_rng(32)
    x=matrix([.2,-.3,.1],[.5,-.1,.8]);y=matrix([-.1,.4,.2],[.02,.01,.1])
    rows=[]
    for i in range(10):
        a=matrix(rng.normal(size=3)*.5,rng.normal(size=3)*.2)
        b=np.linalg.inv(x)@a@y
        rows.append((str(i),RigidTransform('base','flange',a,'synthetic',stamp_s=float(i),clock_domain='mock@epoch1'),RigidTransform('camera','target',b,'synthetic',stamp_s=float(i),clock_domain='mock@epoch1')))
    return rows,x,y


def solve(rows):return solve_fixed_camera(rows[:6],rows[6:],candidate_id='synthetic',max_translation_residual_m=.001,max_rotation_residual_rad=.01,max_condition_number=1e6)


def test_recovers_both_directions_without_known_tcp():
    rows,x,y=samples();a,b,r=solve(rows)
    np.testing.assert_allclose(a.matrix,x,atol=1e-10);np.testing.assert_allclose(b.matrix,y,atol=1e-10)
    assert (a.target_frame,a.source_frame)==('base','camera')
    assert (b.target_frame,b.source_frame)==('flange','target')
    assert r['consistency']=='PASS' and not a.approved and not b.approved


def test_independent_validation_error_is_retained():
    rows,_,_=samples();i,a,b=rows[-1];m=b.matrix.copy();m[0,3]+=.02
    rows[-1]=(i,a,RigidTransform('camera','target',m,'synthetic',stamp_s=b.stamp_s,clock_domain=b.clock_domain))
    _,_,r=solve(rows);assert r['consistency']=='FAIL' and r['validation']['max_m']>.019


@pytest.mark.parametrize('bad',['duplicate','clock','stamp','frame'])
def test_contract_changes_rejected(bad):
    rows,_,_=samples();i,a,b=rows[-1]
    if bad=='duplicate':rows[-1]=rows[0]
    else:
        rows[-1]=(i,a,RigidTransform('other' if bad=='frame' else 'camera','target',b.matrix,'synthetic',stamp_s=b.stamp_s+.01 if bad=='stamp' else b.stamp_s,clock_domain='other' if bad=='clock' else b.clock_domain))
    with pytest.raises(ValueError):solve(rows)


def test_single_axis_and_no_rotation_cannot_produce_extrinsics():
    for rotating in (False,True):
        rows=[]
        for i in range(10):
            a=matrix([0,0,i*.1 if rotating else 0],[i*.01,0,.2])
            rows.append((str(i),RigidTransform('base','flange',a,'synthetic',stamp_s=float(i),clock_domain='mock'),RigidTransform('camera','target',a,'synthetic',stamp_s=float(i),clock_domain='mock')))
        with pytest.raises(ValueError,match='nonparallel'):solve(rows)
