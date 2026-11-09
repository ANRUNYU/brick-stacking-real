"""Held-block offset candidates from synchronized frame-aware pose pairs.

No outlier dropping, physical calibration approval or automatic motion correction.
"""
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def estimate_held_offset(training, validation, *, candidate_id, grasp_version,
                         max_translation_residual_m, max_rotation_residual_rad):
    """Rows: (sample_id, T_world_tcp, T_world_block), aligned at one instant.

    Common clock_domain must include the run epoch; interpolation is producer's
    responsibility. Object orientation must be observed, not assumed identity.
    Independent validation rows may not reuse training IDs.
    """
    training,validation=tuple(training),tuple(validation)
    if len(training)<3 or len(validation)<3 or not candidate_id or not grasp_version:
        raise ValueError('identified candidate, grasp version and >=3 train/validation samples required')
    tolerances=(max_translation_residual_m,max_rotation_residual_rad)
    if any(not np.isscalar(v) or not np.isfinite(v) or v<=0 for v in tolerances):
        raise ValueError('explicit positive residual thresholds required')
    rows=training+validation
    ids=[r[0] for r in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(ids)!=len(set(ids)):
        raise ValueError('distinct sample IDs, no validation leakage')
    offsets=[];signature=None
    for _,tcp,block in rows:
        if tcp.stamp_s is None or block.stamp_s is None:
            raise ValueError('capture-time poses required, no static latest TF')
        current=(tcp.target_frame,tcp.source_frame,block.source_frame,tcp.clock_domain)
        if signature is None: signature=current
        if current!=signature: raise ValueError('frame/clock/epoch changed')
        offsets.append(tcp.inverse().compose(block))
    matrices=np.stack([t.matrix for t in offsets[:len(training)]])
    u,s,vt=np.linalg.svd(matrices[:,:3,:3].mean(0))
    if s[-1]<1e-6: raise ValueError('inconsistent rotation samples')
    correction=np.eye(3);correction[2,2]=np.linalg.det(u@vt)
    m=np.eye(4);m[:3,:3]=u@correction@vt;m[:3,3]=matrices[:,:3,3].mean(0)
    candidate=RigidTransform(signature[1],signature[2],m,'offline_candidate',candidate_id)
    def errors(group):
        translation=[float(np.linalg.norm(t.matrix[:3,3]-m[:3,3])) for t in group]
        rotation=[float(np.arccos(np.clip((np.trace(m[:3,:3].T@t.matrix[:3,:3])-1)/2,-1,1))) for t in group]
        return dict(n=len(group),max_translation_m=max(translation),max_rotation_rad=max(rotation))
    fit=errors(offsets[:len(training)]);check=errors(offsets[len(training):])
    passes=all(e['max_translation_m']<=max_translation_residual_m and e['max_rotation_rad']<=max_rotation_residual_rad for e in (fit,check))
    return candidate,dict(schema_version='c-held-offset-1',candidate_id=candidate_id,grasp_version=grasp_version,
                          training_ids=ids[:len(training)],validation_ids=ids[len(training):],fit=fit,validation=check,
                          consistency='PASS' if passes else 'FAIL',approved=False,motion_enabled=False,
                          scope='pose-pair consistency only; upstream calibration accuracy not established')
