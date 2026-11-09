import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.held_offset import estimate_held_offset


def samples():
    rows=[]
    for i in range(6):
        a=i*.3;c,s=np.cos(a),np.sin(a)
        m=np.eye(4);m[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]];m[:3,3]=[i*.1,0,.2]
        offset=np.eye(4);offset[:3,3]=[.02,.01,-.05]
        tcp=RigidTransform('world','tcp',m,'synthetic',stamp_s=float(i),clock_domain='mock_epoch1')
        block=RigidTransform('world','block',m@offset,'synthetic',stamp_s=float(i),clock_domain='mock_epoch1')
        rows.append((str(i),tcp,block))
    return rows


def estimate(rows):
    return estimate_held_offset(rows[:3],rows[3:],candidate_id='synthetic',grasp_version='preset-1',max_translation_residual_m=.001,max_rotation_residual_rad=.01)


def test_independent_rotated_world_poses_recover_tcp_offset():
    candidate,report=estimate(samples())
    np.testing.assert_allclose(candidate.matrix[:3,3],[.02,.01,-.05],atol=1e-12)
    assert report['consistency']=='PASS' and not candidate.approved


def test_validation_outlier_not_hidden():
    rows=samples();i,t,b=rows[-1];m=b.matrix.copy();m[0,3]+=.01
    rows[-1]=(i,t,RigidTransform(b.target_frame,b.source_frame,m,'synthetic',stamp_s=b.stamp_s,clock_domain=b.clock_domain))
    _,report=estimate(rows)
    assert report['consistency']=='FAIL'


def test_leakage_and_clock_mismatch_rejected():
    rows=samples();rows[-1]=rows[0]
    with pytest.raises(ValueError): estimate(rows)
    rows=samples();i,t,b=rows[-1]
    rows[-1]=(i,t,RigidTransform(b.target_frame,b.source_frame,b.matrix,'synthetic',stamp_s=b.stamp_s,clock_domain='other'))
    with pytest.raises(ValueError): estimate(rows)
