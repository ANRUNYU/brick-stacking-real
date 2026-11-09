"""Joint fixed-camera / unknown rigid point-offset calibration, no target orientation.

R_i p + a_i = R c_i + t. Linear 15-unknown initialization is projected onto
SO(3), then refined against metric point residuals. Degenerate data is rejected.
Rows: (id, T_base_reference, center_camera_m, camera_stamp_s, camera_clock).
"""
import cv2
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def _skew(v):
    x,y,z=v;return np.array([[0,-z,y],[z,0,-x],[-y,x,0]])


def solve_point_target(training,validation,*,camera_frame,candidate_id,
                       max_residual_m,max_condition_number,diagnostic_fit_only=False):
    training,validation=tuple(training),tuple(validation)
    if type(diagnostic_fit_only) is not bool:raise ValueError('explicit boolean fit-only mode required')
    if len(training)<6 or (not diagnostic_fit_only and len(validation)<4) or (diagnostic_fit_only and validation) or not candidate_id or not camera_frame:
        raise ValueError('>=6 training +4 independent validation poses and identities required')
    if any(not np.isscalar(x) or not np.isfinite(x) or x<=0 for x in (max_residual_m,max_condition_number)) or max_condition_number<=1:
        raise ValueError('explicit residual/conditioning thresholds required')
    rows=training+validation;ids=[r[0] for r in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise ValueError('unique sample IDs required')
    signature=None
    for _,a,c,stamp,clock in rows:
        current=(a.target_frame,a.source_frame,a.clock_domain)
        if signature is None:signature=current
        c=np.asarray(c,float)
        if current!=signature or clock!=a.clock_domain or a.stamp_s is None or stamp!=a.stamp_s:
            raise ValueError('frame/clock/epoch/capture-time mismatch')
        if c.shape!=(3,) or not np.isfinite(c).all() or c[2]<=0:raise ValueError('finite positive-Z optical camera point required')
    if len({signature[0],signature[1],camera_frame})!=3:raise ValueError('distinct base/reference/camera frames required')
    design=np.vstack([np.hstack((a.matrix[:3,:3],-np.kron(np.asarray(c).reshape(1,3),np.eye(3)),-np.eye(3))) for _,a,c,_,_ in training])
    rhs=np.concatenate([-a.matrix[:3,3] for _,a,_,_,_ in training])
    singular=np.linalg.svd(design,compute_uv=False)
    if np.linalg.matrix_rank(design)<15:raise ValueError('insufficient diverse pose/translation excitation; point calibration unobservable')
    condition=float(singular[0]/singular[-1])
    if condition>max_condition_number:raise ValueError('point calibration ill-conditioned')
    solution=np.linalg.lstsq(design,rhs,rcond=None)[0]
    p=solution[:3];rotation=solution[3:12].reshape(3,3,order='F')
    u,_,vt=np.linalg.svd(rotation);fix=np.eye(3);fix[2,2]=np.linalg.det(u@vt);rotation=u@fix@vt
    # Refit translations after projecting R onto SO(3).
    h=np.vstack([np.hstack((a.matrix[:3,:3],-np.eye(3))) for _,a,_,_,_ in training])
    g=np.concatenate([rotation@np.asarray(c)-a.matrix[:3,3] for _,a,c,_,_ in training])
    pt=np.linalg.lstsq(h,g,rcond=None)[0];p,t=pt[:3],pt[3:]
    def residual(group,point,rot,trans):
        return np.concatenate([a.matrix[:3,:3]@point+a.matrix[:3,3]-rot@np.asarray(c)-trans for _,a,c,_,_ in group])
    converged=False
    for iteration in range(100):
        error=residual(training,p,rotation,t)
        jac=np.vstack([np.hstack((a.matrix[:3,:3],_skew(rotation@np.asarray(c)),-np.eye(3))) for _,a,c,_,_ in training])
        delta=np.linalg.lstsq(jac,-error,rcond=None)[0]
        if np.linalg.norm(delta)<1e-10:converged=True;break
        found=False
        for scale in (1.,.5,.25,.125,.0625,.03125,.015625,.0078125):
            new_r=cv2.Rodrigues(delta[3:6]*scale)[0]@rotation
            new_p,new_t=p+delta[:3]*scale,t+delta[6:]*scale
            e=residual(training,new_p,new_r,new_t)
            if e@e<error@error:
                p,t,rotation=new_p,new_t,new_r;found=True;break
        if not found:
            converged=bool(np.linalg.norm(jac.T@error,ord=np.inf)<1e-9)
            break
    matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=t
    transform=RigidTransform(signature[0],camera_frame,matrix,'offline_candidate',candidate_id)
    def stats(group):
        e=np.linalg.norm(residual(group,p,rotation,t).reshape(-1,3),axis=1)
        return dict(n=len(e),rmse_m=float(np.sqrt(np.mean(e**2))),p95_m=float(np.percentile(e,95)),max_m=float(e.max()))
    fit,check=stats(training),stats(validation) if validation else None
    fit_quality='PASS' if converged and fit['max_m']<=max_residual_m else 'FAIL'
    def per_pose(group):
        errors=residual(group,p,rotation,t).reshape(-1,3)
        return [dict(sample_id=row[0],residual_base_m=error.tolist(),norm_m=float(np.linalg.norm(error))) for row,error in zip(group,errors)]
    report=dict(schema_version='c-point-target-joint-1',candidate_id=candidate_id,reference_frame=signature[1],
                point_offset_reference_m=p.tolist(),point_orientation_xyzw=None,fit=fit,validation=check,
                training_residuals=per_pose(training),validation_residuals=per_pose(validation) if validation else [],
                training_ids=ids[:len(training)],validation_ids=ids[len(training):],linear_condition_number=condition,
                converged=converged,iterations=iteration+1,
                fit_quality=fit_quality,diagnostic_fit_only=diagnostic_fit_only,
                independent_validation='NOT_PERFORMED' if diagnostic_fit_only else 'PERFORMED',
                consistency='INCOMPLETE' if diagnostic_fit_only else ('PASS' if converged and max(fit['max_m'],check['max_m'])<=max_residual_m else 'FAIL'),
                approved=False,motion_enabled=False,
                scope='joint point mapping consistency; no target orientation, grasp calibration, absolute metrology or motion permission')
    return transform,report
