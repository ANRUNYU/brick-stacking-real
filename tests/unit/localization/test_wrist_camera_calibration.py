import cv2
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.wrist_camera_calibration import solve_wrist_camera


def test_eye_in_hand_inverse_direction_recovers_mount_and_fixed_board():
    rng=np.random.default_rng(11);x=np.eye(4);x[:3,:3]=cv2.Rodrigues(np.array([.1,.05,-.08]))[0];x[:3,3]=[.02,0,.05]
    board=np.array([.2,.1,1.2,1.]);rows=[]
    for i in range(12):
        a=np.eye(4);a[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*.2)[0];a[:3,3]=rng.normal(size=3)*.08
        c=(np.linalg.inv(a@x)@board)[:3]
        rows.append((str(i),RigidTransform('base','flange',a,'synthetic',stamp_s=float(i),clock_domain='synthetic'),c,float(i),'synthetic'))
    found,report=solve_wrist_camera(rows[:8],rows[8:],camera_frame='wrist_camera',candidate_id='synthetic',max_residual_m=.01,max_condition_number=1e6)
    np.testing.assert_allclose(found.matrix,x,atol=1e-9)
    np.testing.assert_allclose(report['target_center_base_m'],board[:3],atol=1e-9)
    assert (found.target_frame,found.source_frame)==('flange','wrist_camera')
    assert report['consistency']=='PASS' and not report['approved'] and not report['motion_enabled']
