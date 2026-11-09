"""Metric noncoplanar landmark PnP with independent pixel validation.

Requires identified, measured landmarks. No automatic cube-corner identity,
depth-scale tuning, invisible-corner inference, or physical approval.
"""
import cv2
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def estimate_target_pose(object_train_m, image_train_px, object_check_m, image_check_px, *,
                         K, distortion, image_size_px, pixel_space,
                         camera_frame, target_frame, stamp_s, clock_domain,
                         candidate_id, max_reprojection_error_px):
    points=[]
    width,height=image_size_px
    if any(type(v) is not int or v<=0 for v in (width,height)):
        raise ValueError('explicit positive image dimensions required')
    for xyz,uv,minimum in ((object_train_m,image_train_px,6),(object_check_m,image_check_px,2)):
        xyz,uv=np.asarray(xyz,float),np.asarray(uv,float)
        if xyz.ndim!=2 or xyz.shape[1]!=3 or len(xyz)<minimum or uv.shape!=(len(xyz),2) or not np.isfinite(xyz).all() or not np.isfinite(uv).all():
            raise ValueError('paired finite metric xyz/pixels with >=6 training and >=2 holdout required')
        if np.any(uv<0) or np.any(uv[:,0]>=width) or np.any(uv[:,1]>=height):raise ValueError('landmark outside declared image')
        points.append((xyz,uv))
    xyz,uv=points[0];check_xyz,check_uv=points[1]
    all_points=np.vstack((xyz,check_xyz));all_pixels=np.vstack((uv,check_uv))
    if len(np.unique(all_points,axis=0))!=len(all_points) or len(np.unique(all_pixels,axis=0))!=len(all_pixels):
        raise ValueError('duplicate/reused landmark or pixel; holdout must be independent')
    if np.linalg.matrix_rank(xyz-xyz.mean(0),tol=1e-9)!=3:
        raise ValueError('noncoplanar identified landmarks required; this solver does not resolve planar ambiguity')
    k=np.asarray(K,float);d=np.asarray(distortion,float).reshape(-1)
    if k.shape!=(3,3) or not np.isfinite(k).all() or min(k[0,0],k[1,1])<=0 or not np.allclose(k[2],[0,0,1],atol=1e-10) or k[0,1]!=0 or k[1,0]!=0:
        raise ValueError('explicit zero-skew pinhole intrinsics required')
    if len(d) not in (4,5,8,12,14) or not np.isfinite(d).all():raise ValueError('explicit OpenCV distortion vector required')
    if pixel_space not in ('raw_color','rectified_color') or (pixel_space=='rectified_color' and np.any(d!=0)):
        raise ValueError('rectified pixels require zero distortion; raw pixels require matching original profile')
    if stamp_s is None or not candidate_id or not np.isscalar(max_reprojection_error_px) or not np.isfinite(max_reprojection_error_px) or max_reprojection_error_px<=0:
        raise ValueError('capture identity/time and explicit reprojection threshold required')
    try:ok,rvec,tvec=cv2.solvePnP(xyz,uv,k,d,flags=cv2.SOLVEPNP_SQPNP)
    except cv2.error as exc:raise ValueError('target PnP failed') from exc
    if not ok:raise ValueError('target PnP did not converge')
    matrix=np.eye(4);matrix[:3,:3]=cv2.Rodrigues(rvec)[0];matrix[:3,3]=tvec.reshape(3)
    transform=RigidTransform(camera_frame,target_frame,matrix,'offline_pnp_candidate',candidate_id,stamp_s=stamp_s,clock_domain=clock_domain)
    if np.any(transform.apply(all_points)[:,2]<=0):raise ValueError('landmarks behind camera')
    def errors(x,p):
        projected=cv2.projectPoints(x,rvec,tvec,k,d)[0].reshape(-1,2)
        e=np.linalg.norm(projected-p,axis=1)
        return dict(n=len(e),rmse_px=float(np.sqrt(np.mean(e**2))),max_px=float(e.max()))
    fit,validation=errors(xyz,uv),errors(check_xyz,check_uv)
    return transform,dict(schema_version='c-target-pnp-1',fit=fit,validation=validation,
            consistency='PASS' if max(fit['max_px'],validation['max_px'])<=max_reprojection_error_px else 'FAIL',
            approved=False,motion_enabled=False,
            scope='identified landmark reprojection only; target dimensions, visibility/identity and absolute physical accuracy require independent evidence')
