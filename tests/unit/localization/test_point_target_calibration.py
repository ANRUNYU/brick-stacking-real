import cv2
import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.point_target_calibration import solve_point_target


def samples(noise=0):
    rng=np.random.default_rng(33);r=cv2.Rodrigues(np.array([.2,-.1,.3]))[0];p=np.array([.02,.01,.09]);t=np.array([.4,-.2,.8]);rows=[]
    for i in range(16):
        a=np.eye(4);a[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*.6)[0];a[:3,3]=rng.normal(size=3)*.2+[0,0,1.5]
        c=r.T@(a[:3,:3]@p+a[:3,3]-t)+rng.normal(size=3)*noise
        rows.append((str(i),RigidTransform('base','L5',a,'synthetic',stamp_s=float(i),clock_domain='mock@1'),c,float(i),'mock@1'))
    x=np.eye(4);x[:3,:3]=r;x[:3,3]=t
    return rows,x,p


def solve(rows):return solve_point_target(rows[:12],rows[12:],camera_frame='camera',candidate_id='synthetic',max_residual_m=.002,max_condition_number=1e6)


def test_unmarked_point_recovers_extrinsic_and_unknown_mount_offset():
    rows,x,p=samples();tf,report=solve(rows)
    np.testing.assert_allclose(tf.matrix,x,atol=1e-10)
    np.testing.assert_allclose(report['point_offset_reference_m'],p,atol=1e-10)
    assert report['point_orientation_xyzw'] is None and report['consistency']=='PASS' and not tf.approved


def test_explicit_fit_only_never_claims_independent_validation():
    rows,x,_=samples()
    tf,r=solve_point_target(rows[:6],[],camera_frame='camera',candidate_id='synthetic-fit-only',max_residual_m=.002,max_condition_number=1e6,diagnostic_fit_only=True)
    np.testing.assert_allclose(tf.matrix,x,atol=1e-9)
    assert r['fit_quality']=='PASS' and r['consistency']=='INCOMPLETE'
    assert r['validation'] is None and r['independent_validation']=='NOT_PERFORMED'
    assert len(r['training_residuals'])==6 and not r['approved'] and not r['motion_enabled']


def test_fit_only_preserves_large_training_errors():
    rows,_,_=samples(.01)
    _,r=solve_point_target(rows[:6],[],camera_frame='camera',candidate_id='synthetic-noisy',max_residual_m=.002,max_condition_number=1e6,diagnostic_fit_only=True)
    assert r['fit_quality']=='FAIL' and r['consistency']=='INCOMPLETE'
    assert r['fit']['max_m']>.002 and r['validation'] is None


@pytest.mark.parametrize('bad',['implicit','nonempty','string'])
def test_fit_only_does_not_weaken_default_validation_requirement(bad):
    rows,_,_=samples();flag=True;check=[]
    if bad=='implicit':flag=False
    elif bad=='nonempty':check=rows[12:]
    else:flag='true'
    with pytest.raises(ValueError):solve_point_target(rows[:6],check,camera_frame='camera',candidate_id='synthetic',max_residual_m=.002,max_condition_number=1e6,diagnostic_fit_only=flag)


def test_noisy_data_and_heldout_outlier_not_dropped():
    rows,_,_=samples(.0001);_,r=solve(rows);assert r['consistency']=='PASS'
    i,a,c,t,clock=rows[-1];rows[-1]=(i,a,c+[.02,0,0],t,clock)
    _,r=solve(rows);assert r['consistency']=='FAIL' and r['validation']['max_m']>.019


def test_no_rotation_is_unobservable():
    rows,_,_=samples()
    for i,(identity,a,c,t,clock) in enumerate(rows):
        m=a.matrix.copy();m[:3,:3]=np.eye(3)
        rows[i]=(identity,RigidTransform('base','L5',m,'synthetic',stamp_s=t,clock_domain=clock),c,t,clock)
    with pytest.raises(ValueError,match='excitation'):solve(rows)


@pytest.mark.parametrize('bad',['id','clock','stamp','point'])
def test_bad_observation_rejected(bad):
    rows,_,_=samples();i,a,c,t,clock=rows[-1]
    if bad=='id':i=rows[0][0]
    elif bad=='clock':clock='other'
    elif bad=='stamp':t+=.1
    elif bad=='point':c=[0,0,-1]
    rows[-1]=(i,a,c,t,clock)
    with pytest.raises(ValueError):solve(rows)
