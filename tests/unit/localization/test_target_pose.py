import cv2
import numpy as np
import pytest
from brick_stacking.localization.target_pose import estimate_target_pose


def inputs():
    xyz=np.array([[x,y,z] for x in (-.025,.025) for y in (-.025,.025) for z in (-.025,.025)])
    r=np.array([.2,-.3,.1]);t=np.array([.1,.05,.8]);k=np.array([[610.,0,640],[0,610,400],[0,0,1]])
    d=np.array([.01,-.005,.001,.002,0.])
    uv=cv2.projectPoints(xyz,r,t,k,d)[0].reshape(-1,2)
    return xyz,uv,r,t,k,d


def solve(xyz,uv,k,d,**extra):
    kwargs=dict(K=k,distortion=d,image_size_px=(1280,800),pixel_space='raw_color',camera_frame='camera',target_frame='target',stamp_s=1.,clock_domain='mock',candidate_id='synthetic',max_reprojection_error_px=1.)
    kwargs.update(extra)
    return estimate_target_pose(xyz[:6],uv[:6],xyz[6:],uv[6:],**kwargs)


def test_nonzero_distortion_metric_pose_and_independent_validation():
    xyz,uv,r,t,k,d=inputs();pose,report=solve(xyz,uv,k,d)
    np.testing.assert_allclose(pose.matrix[:3,3],t,atol=1e-9)
    np.testing.assert_allclose(pose.matrix[:3,:3],cv2.Rodrigues(r)[0],atol=1e-9)
    assert report['consistency']=='PASS' and not pose.approved


def test_holdout_error_not_hidden():
    xyz,uv,_,_,k,d=inputs();uv[-1,0]+=5
    _,r=solve(xyz,uv,k,d);assert r['consistency']=='FAIL' and r['validation']['max_px']>4.9


def test_wrong_rectification_profile_rejected():
    xyz,uv,_,_,k,d=inputs()
    with pytest.raises(ValueError):solve(xyz,uv,k,d,pixel_space='rectified_color')


@pytest.mark.parametrize('bad',['planar','reuse','outside','missing_D','missing_time'])
def test_incomplete_or_ambiguous_landmarks_rejected(bad):
    xyz,uv,_,_,k,d=inputs();kw={}
    if bad=='planar':xyz[:6,2]=0
    elif bad=='reuse':xyz[-1]=xyz[0]
    elif bad=='outside':uv[0,0]=-1
    elif bad=='missing_D':d=[]
    elif bad=='missing_time':kw['stamp_s']=None
    with pytest.raises(ValueError):solve(xyz,uv,k,d,**kw)
