"""Offline candidate evaluation with injected IK/collision providers.

Provider PASS is scoped evidence, never full-robot clearance or a motion permit.
No device imports; preserves public ArmAdapter and D task scheduler.
"""
import math
from brick_stacking.planning.joint_trajectory import build_offline_trajectory


def evaluate_candidates(candidates, *, solve_ik, check_collision, limits,
                        trajectory_context, collision_model_version):
    """IK returns joint waypoints in limits.joint_names order, or None.

    collision(trajectory) returns status PASS/FAIL/UNKNOWN, scope, missing,
    model_version. Provider must inspect complete interpolated paths, not only
    endpoints. An AABB-only provider must explicitly name its missing coverage.
    Expected data failures are reported per candidate; unexpected provider errors
    propagate so programming failures cannot be disguised as unreachability.
    """
    candidates=tuple(candidates)
    ids=[c['candidate_id'] for c in candidates]
    if not ids or len(set(ids))!=len(ids) or any(not i for i in ids):
        raise ValueError('nonempty uniquely identified candidates required')
    if not collision_model_version: raise ValueError('collision model version required')
    results=[]
    for candidate in candidates:
        row={'candidate_id':candidate['candidate_id'],'ik':'UNKNOWN',
             'trajectory_limits':'NOT_GENERATED','collision':'UNKNOWN',
             'full_collision':'UNKNOWN','feasible_within_supplied_models':False,
             'motion_enabled':False,'reason':None,'trajectory':None}
        q=solve_ik(candidate)
        if q is None:
            row.update(ik='FAIL',reason='IK_NO_SOLUTION');results.append(row);continue
        row['ik']='PASS'
        try:
            trajectory=build_offline_trajectory(q,limits,**trajectory_context)
        except ValueError as exc:
            row.update(trajectory_limits='FAIL',reason=str(exc));results.append(row);continue
        row['trajectory_limits']='PASS'
        evidence=check_collision(trajectory)
        if (not isinstance(evidence,dict) or evidence.get('status') not in ('PASS','FAIL','UNKNOWN')
                or not evidence.get('scope') or not isinstance(evidence.get('missing'),list)
                or evidence.get('model_version')!=collision_model_version):
            row['reason']='INVALID_COLLISION_EVIDENCE';results.append(row);continue
        row.update(collision=evidence['status'],collision_evidence=evidence)
        if evidence['status']!='PASS':
            row['reason']='COLLISION_'+evidence['status'];results.append(row);continue
        duration=sum(s['duration_s'] for s in trajectory['segments'])
        if not math.isfinite(duration): raise ValueError('nonfinite cost')
        trajectory.update(ik='PASS',collision_model_version=collision_model_version)
        row.update(feasible_within_supplied_models=True,trajectory=trajectory,
                   cost_duration_s=duration,reason='OFFLINE_SCOPED_CHECKS_ONLY')
        results.append(row)
    valid=[r for r in results if r['feasible_within_supplied_models']]
    selected=min(valid,key=lambda r:(r['cost_duration_s'],r['candidate_id'])) if valid else None
    return {'schema_version':'c-candidates-1','source':'offline',
            'selected_candidate_id':selected['candidate_id'] if selected else None,
            'candidates':results,'motion_enabled':False,
            'scene_version':trajectory_context.get('scene_version'),
            'calibration_version':trajectory_context.get('calibration_version'),
            'model_version':limits.model_version if limits else None,
            'collision_model_version':collision_model_version}
