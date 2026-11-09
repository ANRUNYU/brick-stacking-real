"""Fixed-camera joint extrinsic/rigid-target candidates, no known TCP required.

A_i=T_base_reference, B_i=T_camera_target, unknown X=T_base_camera,
Y=T_reference_target; A_i Y = X B_i. Reference may be a flange or a
verified upstream rigid link with the target attached to that same link.
Outputs are never physical approvals.
OpenCV robot-world-hand-eye is given inv(B_i), inv(A_i), returning inv(X), inv(Y).
"""
import cv2
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def solve_fixed_camera(training, validation, *, candidate_id,
                       max_translation_residual_m, max_rotation_residual_rad,
                       max_condition_number):
    training, validation = tuple(training), tuple(validation)
    if len(training)<4 or len(validation)<4 or not candidate_id:
        raise ValueError('identified candidate and >=4 training + 4 independent validation poses required')
    limits=(max_translation_residual_m,max_rotation_residual_rad,max_condition_number)
    if any(not np.isscalar(v) or not np.isfinite(v) or v<=0 for v in limits) or max_condition_number<=1:
        raise ValueError('explicit positive residual and conditioning thresholds required')
    rows=training+validation;ids=[row[0] for row in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('unique sample IDs, no train/validation leakage')
    signature=None
    for _,a,b in rows:
        current=(a.target_frame,a.source_frame,b.target_frame,b.source_frame,a.clock_domain)
        if len(set(current[:4]))!=4:raise ValueError('four distinct physical frame names required')
        if signature is None:signature=current
        if current!=signature or a.clock_domain!=b.clock_domain:
            raise ValueError('frame/clock/epoch changed')
        if a.stamp_s is None or b.stamp_s is None or a.stamp_s!=b.stamp_s:
            raise ValueError('paired poses must share a proven capture instant')
    # Rotation about a single common axis leaves part of X/Y unobservable.
    for which in (1,2):
        first=training[0][which].matrix[:3,:3]
        vectors=np.array([cv2.Rodrigues(first.T@row[which].matrix[:3,:3])[0].ravel() for row in training[1:]])
        singular=np.linalg.svd(vectors,compute_uv=False)
        if singular[1]<1e-6:raise ValueError('at least two nonparallel rotation motions required')
        if singular[0]/singular[1]>max_condition_number:raise ValueError('rotation excitation ill-conditioned')
    design=np.vstack([np.hstack((a.matrix[:3,:3],-np.eye(3))) for _,a,_ in training])
    singular=np.linalg.svd(design,compute_uv=False)
    condition=float(singular[0]/singular[-1]) if singular[-1]>0 else float('inf')
    if not np.isfinite(condition) or condition>max_condition_number:
        raise ValueError('translation system ill-conditioned')
    p=[b.inverse().matrix for _,_,b in training]
    q=[a.inverse().matrix for _,a,_ in training]
    try:
        rx,tx,ry,ty=cv2.calibrateRobotWorldHandEye(
            [m[:3,:3] for m in p],[m[:3,3] for m in p],
            [m[:3,:3] for m in q],[m[:3,3] for m in q],method=cv2.CALIB_ROBOT_WORLD_HAND_EYE_SHAH)
    except cv2.error as exc:raise ValueError('joint calibration numerical failure') from exc
    def transform(target,source,r,t):
        m=np.eye(4);m[:3,:3]=r;m[:3,3]=np.asarray(t).reshape(3)
        return RigidTransform(target,source,m,'offline_candidate',candidate_id)
    base,flange,camera,target=signature[:4]
    x=transform(camera,base,rx,tx).inverse()
    y=transform(target,flange,ry,ty).inverse()
    def errors(group):
        translations=[];rotations=[]
        for _,a,b in group:
            left=a.matrix@y.matrix;right=x.matrix@b.matrix
            translations.append(float(np.linalg.norm(left[:3,3]-right[:3,3])))
            rotations.append(float(np.arccos(np.clip((np.trace(left[:3,:3].T@right[:3,:3])-1)/2,-1,1))))
        return dict(n=len(group),rmse_m=float(np.sqrt(np.mean(np.square(translations)))),
                    p95_m=float(np.percentile(translations,95)),max_m=max(translations),
                    max_rotation_rad=max(rotations))
    fit,check=errors(training),errors(validation)
    passes=all(r['max_m']<=max_translation_residual_m and r['max_rotation_rad']<=max_rotation_residual_rad for r in (fit,check))
    return x,y,dict(schema_version='c-fixed-camera-joint-1',candidate_id=candidate_id,
                    training_ids=ids[:len(training)],validation_ids=ids[len(training):],fit=fit,validation=check,
                    translation_condition_number=condition,consistency='PASS' if passes else 'FAIL',
                    approved=False,motion_enabled=False,
                    scope='joint pose consistency assuming fixed camera/base and rigid target; no absolute physical accuracy, grasp offset or motion approval')
