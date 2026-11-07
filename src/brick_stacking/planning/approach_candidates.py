"""Generate explicit approach alternatives; no assumed world-up or feasibility."""
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.calibration import tcp_target_for_block


def generate_approaches(world_pick,world_place,tcp_block,*,directions_world,clearance_m,scene_version):
    if world_pick.target_frame!=world_place.target_frame:raise ValueError('pick/place world frame mismatch')
    if not scene_version or not np.isfinite(clearance_m) or clearance_m<=0:raise ValueError('explicit scene/positive clearance required')
    directions=np.asarray(directions_world,float)
    if directions.ndim!=2 or directions.shape[1]!=3 or not len(directions) or not np.isfinite(directions).all():raise ValueError('explicit finite approach directions required')
    if not np.allclose(np.linalg.norm(directions,axis=1),1,atol=1e-8,rtol=0):raise ValueError('directions must be unit vectors in world frame')
    for i,d in enumerate(directions):
        if any(np.allclose(d,other,atol=1e-8) for other in directions[:i]):raise ValueError('duplicate approach direction')
    pick=tcp_target_for_block(world_pick,tcp_block);place=tcp_target_for_block(world_place,tcp_block)
    def candidate_pose(p,delta):
        m=p.matrix.copy();m[:3,3]+=delta
        return RigidTransform(p.target_frame,p.source_frame,m,'offline_approach_candidate',p.calibration_id)
    result=[]
    for i,d in enumerate(directions):
        a=candidate_pose(pick,d*clearance_m);b=candidate_pose(place,d*clearance_m)
        result.append(dict(candidate_id=f'approach_{i:03d}',direction_world=d.tolist(),scene_version=scene_version,
            phases=['approach','grasp','lift','transfer','release','retreat'],targets=[a,pick,a,b,place,b],
            input_capture_stamps_s=[world_pick.stamp_s,world_place.stamp_s],
            ik='NOT_CHECKED',full_collision='UNKNOWN',motion_enabled=False,
            assumptions=['direction supplied by task/grasp policy','targets alone do not enforce Cartesian straight segments']))
    return result
