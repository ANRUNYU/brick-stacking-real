"""Unmarked cube center from three visible face planes, no face-axis labels.

Reuses existing plane fitter. Metric dimension and depth accuracy remain inputs;
the fit is not absolute metrology and does not recover a labelled cube orientation.
"""
import numpy as np
import cv2
from brick_stacking.localization.table_plane import fit_table_plane


def center_from_faces(faces,*,edge_m,plane_threshold_m,min_inlier_ratio,
                      max_holdout_m,max_normal_dot,max_condition_number,
                      regular_cube_constraint=False):
    limits=(edge_m,plane_threshold_m,max_holdout_m,max_condition_number)
    if len(faces)!=3 or any(not np.isscalar(x) or not np.isfinite(x) or x<=0 for x in limits) or max_condition_number<=1 or not 0<max_normal_dot<1:
        raise ValueError('three face sets and explicit geometric/quality thresholds required')
    if type(regular_cube_constraint) is not bool:raise ValueError('explicit regular-cube model selection required')
    normals=[];offsets=[];reports=[];fit_points=[]
    for train,check in faces:
        train,check=np.asarray(train,float),np.asarray(check,float)
        if train.ndim!=2 or train.shape[1]!=3 or len(train)<20 or check.ndim!=2 or check.shape[1]!=3 or len(check)<10 or not np.isfinite(train).all() or not np.isfinite(check).all() or np.any(train[:,2]<=0) or np.any(check[:,2]<=0):
            raise ValueError('three visible face interiors with >=20 training +10 validation positive-Z points required')
        plane=fit_table_plane(train,normal_hint=-train.mean(0),distance_threshold_m=plane_threshold_m,iterations=100,min_inlier_ratio=min_inlier_ratio)
        n=np.asarray(plane.normal)
        normals.append(n);offsets.append(plane.offset_m)
        fit_points.append(train[np.abs(plane.heights(train))<=plane_threshold_m])
        errors=np.abs(plane.heights(check))
        reports.append(dict(normal_camera=n.tolist(),offset_m=plane.offset_m,inlier_ratio=plane.inlier_ratio,
                            fit_rms_m=plane.rms_m,validation_n=len(check),validation_p95_m=float(np.percentile(errors,95)),validation_max_m=float(errors.max())))
    n=np.asarray(normals);gram=n@n.T
    max_dot=float(np.max(np.abs(gram-np.eye(3))))
    condition=float(np.linalg.cond(n))
    if not np.isfinite(condition) or condition>max_condition_number:raise ValueError('face intersection ill-conditioned')
    converged=True
    if regular_cube_constraint:
        # Known regular-cube geometry, not independent noisy plane orientations:
        # jointly fit three orthogonal faces; retain ALL holdout errors below.
        u,_,vt=np.linalg.svd(n);n=u@vt
        offsets=[-n[i]@p.mean(0) for i,p in enumerate(fit_points)]
    elif max_dot>max_normal_dot:
        raise ValueError('face normals not sufficiently perpendicular; no center output')
    # Normals face the camera, so interior center is half an edge behind each face.
    center=np.linalg.solve(n,-np.asarray(offsets)-edge_m/2)
    if regular_cube_constraint:
        def residual(normals,c):return np.concatenate([(p-c)@normals[i]-edge_m/2 for i,p in enumerate(fit_points)])
        converged=False
        for _ in range(100):
            e=residual(n,center)
            jac=np.vstack([np.column_stack((np.cross(n[i],p-center),-np.broadcast_to(n[i],p.shape))) for i,p in enumerate(fit_points)])
            if np.linalg.matrix_rank(jac)<6:raise ValueError('constrained cube geometry unobservable')
            delta=np.linalg.lstsq(jac,-e,rcond=None)[0]
            if np.linalg.norm(delta)<1e-10:converged=True;break
            improved=False
            for scale in (1.,.5,.25,.125,.0625,.03125,.015625,.0078125):
                new_n=n@cv2.Rodrigues(delta[:3]*scale)[0].T;new_c=center+delta[3:]*scale
                check=residual(new_n,new_c)
                if check@check<e@e:
                    n,center=new_n,new_c;improved=True;break
            if not improved:
                converged=bool(np.linalg.norm(jac.T@e,ord=np.inf)<1e-9)
                break
        for i,(_,check) in enumerate(faces):
            error=np.abs((np.asarray(check)-center)@n[i]-edge_m/2)
            reports[i].update(fitted_cube_normal_camera=n[i].tolist(),
                              constrained_validation_p95_m=float(np.percentile(error,95)),
                              constrained_validation_max_m=float(error.max()))
    if center[2]<=0:raise ValueError('reconstructed center behind camera')
    # Reject face patches lying outside the proposed 50mm face, including a table ROI.
    for (train,check),i in zip(faces,range(3)):
        coordinates=(np.vstack((train,check))-center)@n.T
        tangential=np.delete(coordinates,i,axis=1)
        if np.any(np.abs(tangential)>edge_m/2+max_holdout_m):
            raise ValueError('face patch not bounded by the measured cube dimensions')
    validation_key='constrained_validation_max_m' if regular_cube_constraint else 'validation_max_m'
    return center,dict(schema_version='c-three-face-center-1',face_reports=reports,
                       max_abs_normal_dot=max_dot,normal_condition_number=condition,
                       regular_cube_constraint=regular_cube_constraint,converged=converged,
                       consistency='PASS' if converged and all(r[validation_key]<=max_holdout_m for r in reports) else 'FAIL',
                       orientation_xyzw=None,approved=False,motion_enabled=False,
                       scope='three-face depth/size consistency only; no labelled orientation, absolute sensor accuracy or calibration approval')
