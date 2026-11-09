"""Local bounded numerical IK using supplied FK; never accesses hardware.
Failure is local nonconvergence, not proof of global unreachability.
"""
import numpy as np


def rotation_log(r):
    angle=np.arccos(np.clip((np.trace(r)-1)/2,-1,1))
    v=np.array([r[2,1]-r[1,2],r[0,2]-r[2,0],r[1,0]-r[0,1]])
    if angle<1e-7: return v/2
    if np.pi-angle<1e-5:
        _,e=np.linalg.eigh((r+r.T)/2);axis=e[:,-1]
        return axis*angle*(-1 if axis@v<0 else 1)
    return v*angle/(2*np.sin(angle))


def solve_pose_ik(fk,target,seed_rad,limits,*,position_tolerance_m,rotation_tolerance_rad,
                  orientation_weight_m_per_rad,damping,max_step_rad,max_iterations,difference_step_rad):
    settings=(position_tolerance_m,rotation_tolerance_rad,orientation_weight_m_per_rad,damping,max_step_rad,difference_step_rad)
    if not all(np.isscalar(v) and np.isfinite(v) and v>0 for v in settings) or type(max_iterations) is not int or max_iterations<1:
        raise ValueError('explicit positive solver settings required')
    if limits is None: raise ValueError('unknown model/limits')
    q=np.array(seed_rad,float,copy=True);lo=np.array(limits.lower_rad);hi=np.array(limits.upper_rad)
    if q.shape!=lo.shape or not np.isfinite(q).all() or np.any(q<lo) or np.any(q>hi):
        raise ValueError('seed must match named bounds')
    weights=np.array([1.,1.,1.]+[orientation_weight_m_per_rad]*3)
    def residual(x):
        current=fk(x)
        if (current.target_frame,current.source_frame)!=(target.target_frame,target.source_frame):
            raise ValueError('FK and target frame mismatch')
        return np.r_[target.matrix[:3,3]-current.matrix[:3,3],rotation_log(target.matrix[:3,:3]@current.matrix[:3,:3].T)]
    reason='ITERATION_LIMIT'
    for iteration in range(max_iterations+1):
        raw=residual(q)
        if not np.isfinite(raw).all(): raise ValueError('nonfinite FK residual')
        if np.linalg.norm(raw[:3])<=position_tolerance_m and np.linalg.norm(raw[3:])<=rotation_tolerance_rad:
            reason='CONVERGED';break
        if iteration==max_iterations: break
        e=raw*weights;jac=np.empty((6,len(q)))
        for i in range(len(q)):
            step=min(difference_step_rad,hi[i]-q[i])
            if step<difference_step_rad*.1: step=-min(difference_step_rad,q[i]-lo[i])
            if step==0: raise ValueError('locked joint unsupported')
            trial=q.copy();trial[i]+=step
            jac[:,i]=(residual(trial)*weights-e)/step
        delta=-jac.T@np.linalg.solve(jac@jac.T+damping**2*np.eye(6),e)
        peak=np.max(np.abs(delta))
        if peak>max_step_rad: delta*=max_step_rad/peak
        accepted=False
        for scale in (1.,.5,.25,.125,.0625,.03125):
            trial=np.clip(q+delta*scale,lo,hi)
            if np.linalg.norm(residual(trial)*weights)<np.linalg.norm(e):
                q=trial;accepted=True;break
        if not accepted: reason='LOCAL_STALL';break
    success=reason=='CONVERGED'
    return dict(schema_version='c-ik-1',ik='PASS' if success else 'FAIL',reason=reason,
                joint_names=list(limits.joint_names),positions_rad=q.tolist() if success else None,
                position_error_m=float(np.linalg.norm(raw[:3])),rotation_error_rad=float(np.linalg.norm(raw[3:])),
                iterations=iteration,model_version=limits.model_version,trajectory='NOT_GENERATED',
                full_collision='UNKNOWN',motion_enabled=False,scope='local solve against caller FK only')
