import cv2
import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.wrist_camera_calibration import (
    solve_wrist_camera,
    solve_wrist_camera_from_fixed_board_corners,
    solve_wrist_camera_from_head_bridge,
)


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


def test_head_bridge_disambiguates_180_flips_and_recovers_mount():
    rng=np.random.default_rng(42)
    x=np.eye(4)
    x[:3,:3]=cv2.Rodrigues(np.array([.25,-.18,.35]))[0]
    x[:3,3]=[.035,-.022,.068]
    grid_x,grid_y=np.meshgrid(np.arange(9)*0.0195,np.arange(6)*0.0195)
    board_local=np.stack([grid_x.ravel()-0.078,grid_y.ravel()-0.04875,np.zeros(54)],axis=1)

    flips=[True,False,True,True,False,True]
    rows=[]
    for i,flip in enumerate(flips):
        a_mat=np.eye(4)
        a_mat[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*0.15)[0]
        a_mat[:3,3]=np.array([0.35,0.05,-0.25])+rng.normal(size=3)*0.05
        a_tf=RigidTransform('L_arm_root','L8_Link',a_mat,'synthetic',stamp_s=float(i+1),clock_domain='synthetic')

        t_wrist_board=np.eye(4)
        t_wrist_board[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*0.12)[0]
        t_wrist_board[:3,3]=np.array([-0.08+0.04*i,0.03*(-1)**i,0.42+0.02*i])
        pts_wrist=(t_wrist_board[:3,:3]@board_local.T).T+t_wrist_board[:3,3]
        pts_base=a_tf.apply((x[:3,:3]@pts_wrist.T).T+x[:3,3])
        if flip:
            pts_wrist=pts_wrist[::-1].copy()
        rows.append((f'pose_{i}',a_tf,pts_base,pts_wrist,float(i+1),'synthetic'))

    found,report=solve_wrist_camera_from_head_bridge(
        rows[:4],rows[4:],camera_frame='left_wrist_camera',candidate_id='cand_bridge_test',max_residual_m=0.005
    )
    np.testing.assert_allclose(found.matrix,x,atol=1e-9)
    assert (found.target_frame,found.source_frame)==('L8_Link','left_wrist_camera')
    assert [r['flipped_180'] for r in report['training_residuals']]==flips[:4]
    assert [r['flipped_180'] for r in report['validation_residuals']]==flips[4:]
    assert report['consistency']=='PASS'
    assert not report['approved'] and not report['motion_enabled']


def test_fixed_board_corners_solver_recovers_mount_without_head_camera():
    rng=np.random.default_rng(7)
    x=np.eye(4)
    x[:3,:3]=cv2.Rodrigues(np.array([.2,-.15,.3]))[0]
    x[:3,3]=[.03,-.025,.065]
    b=np.eye(4)
    b[:3,:3]=cv2.Rodrigues(np.array([.02,-.03,.1]))[0]
    b[:3,3]=[.58,-.19,-.45]
    grid_x,grid_y=np.meshgrid(np.arange(9)*0.0193,np.arange(6)*0.0193)
    obj=np.stack([grid_x.ravel(),grid_y.ravel(),np.zeros(54)],axis=1)
    obj_c=obj-obj.mean(0)

    rows=[]
    for i in range(8):
        t_wb=np.eye(4)
        t_wb[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*0.25)[0]
        t_wb[:3,3]=np.array([-0.06+0.02*i,0.03*(-1)**i,0.38+0.015*i])
        pw=(t_wb[:3,:3]@obj_c.T).T+t_wb[:3,3]
        a_mat=b@np.linalg.inv(x@t_wb)
        a_tf=RigidTransform('L_arm_root','L8_Link',a_mat,'synthetic',stamp_s=float(i+1),clock_domain='synthetic')
        rows.append((f'pose_{i}',a_tf,pw,float(i+1),'synthetic'))

    found,report=solve_wrist_camera_from_fixed_board_corners(
        rows[:6],rows[6:],board_object_points_m=obj,camera_frame='left_wrist_camera',candidate_id='fixed_corners_test'
    )
    np.testing.assert_allclose(found.matrix,x,atol=1e-6)
    np.testing.assert_allclose(report['target_center_base_m'],b[:3,3],atol=1e-6)
    assert report['consistency']=='PASS'


def test_head_bridge_rejects_insufficient_translation_span():
    grid_x,grid_y=np.meshgrid(np.arange(9)*0.02,np.arange(6)*0.02)
    pts_wrist=np.stack([grid_x.ravel(),grid_y.ravel(),np.full(54,0.45)],axis=1)
    rows=[]
    for i in range(3):
        a_tf=RigidTransform('L_arm_root','L8_Link',np.eye(4),'synthetic',stamp_s=float(i+1),clock_domain='synthetic')
        rows.append((f'p{i}',a_tf,pts_wrist.copy(),pts_wrist.copy(),float(i+1),'synthetic'))
    with pytest.raises(ValueError,match='insufficient board-to-wrist center translation span'):
        solve_wrist_camera_from_head_bridge(
            rows[:2],rows[2:],camera_frame='left_wrist_camera',candidate_id='bad_span'
        )
