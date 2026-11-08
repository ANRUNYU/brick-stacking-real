"""Synthetic geometry integration, NOT hardware calibration or acceptance."""
import cv2
import numpy as np
from brick_stacking.localization.cube_center import center_from_faces
from brick_stacking.localization.point_target_calibration import solve_point_target
from brick_stacking.localization.rigid_transforms import RigidTransform


def test_unlabelled_face_planes_to_joint_camera_calibration():
    rng=np.random.default_rng(76)
    rx=cv2.Rodrigues(np.array([.2,-.1,.3]))[0];tx=np.array([.4,-.2,.8]);p=np.array([.02,.01,.09]);rows=[]
    while len(rows)<14:
        i=len(rows)
        a=np.eye(4);a[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*.6)[0];a[:3,3]=rng.normal(size=3)*.15+[0,0,1.5]
        center=rx.T@(a[:3,:3]@p+a[:3,3]-tx);cube_rotation=rx.T@a[:3,:3]
        # A camera inside a cube's infinite face slab cannot see that face.
        # Generate only genuinely three-face-visible synthetic observations.
        if center[2]<=.1 or np.min(np.abs(cube_rotation.T@center))<.05:continue
        faces=[]
        for axis in rng.permutation(3):
            points=rng.uniform(-.02,.02,(60,3))
            sign=-1 if cube_rotation[:,axis]@center>0 else 1
            points[:,axis]=sign*.025
            points=points@cube_rotation.T+center;faces.append((points[:40],points[40:]))
        measured,quality=center_from_faces(faces,edge_m=.05,plane_threshold_m=.001,min_inlier_ratio=.9,max_holdout_m=.002,max_normal_dot=.1,max_condition_number=10)
        assert quality['consistency']=='PASS' and quality['orientation_xyzw'] is None
        pose=RigidTransform('base','reference',a,'synthetic',stamp_s=float(i),clock_domain='mock@1')
        rows.append((str(i),pose,measured,float(i),'mock@1'))
    result,report=solve_point_target(rows[:10],rows[10:],camera_frame='camera',candidate_id='synthetic-integration',max_residual_m=.001,max_condition_number=1e6)
    np.testing.assert_allclose(result.matrix[:3,:3],rx,atol=1e-10)
    np.testing.assert_allclose(result.matrix[:3,3],tx,atol=1e-10)
    assert report['consistency']=='PASS' and not result.approved
