"""First-grasp diagnostic PlanBundle and path-shape checks; no execution API."""
import hashlib
import json
import numpy as np

PHASES=('SIDE_WAIT_PICK','ABOVE_PICK','GRASP','LIFT','SIDE_WAIT_PLACE',
        'ABOVE_PLACE','PLACE','RETRACT','SIDE_RETREAT')


def validate_side_approach(points,*,table_point,table_normal,approach_height_m,lift_clearance_m,
                           clearance_m,alignment_tolerance_m):
    values=[approach_height_m,lift_clearance_m,clearance_m,alignment_tolerance_m]
    if not np.isfinite(values).all() or min(values)<=0 or min(approach_height_m,lift_clearance_m)<clearance_m:
        raise ValueError('explicit positive clearance policy required')
    if tuple(x['phase'] for x in points)!=PHASES:
        return dict(shape='FAIL',reasons=['MISSING_OR_REORDERED_PHASE'],full_collision='UNKNOWN')
    positions=np.asarray([x['position_m'] for x in points],float)
    origin=np.asarray(table_point,float);normal=np.asarray(table_normal,float)
    if (positions.shape!=(9,3) or origin.shape!=(3,) or normal.shape!=(3,) or
        not np.isfinite(positions).all() or not np.isfinite(origin).all() or not np.isfinite(normal).all() or
        not np.isclose(np.linalg.norm(normal),1)):
        raise ValueError('finite positions and explicit unit table normal required')
    heights=(positions-origin)@normal
    def lateral(a,b):
        delta=positions[b]-positions[a];return np.linalg.norm(delta-normal*(delta@normal))
    reasons=[]
    for i in (0,1,4,5,8):
        if heights[i]<approach_height_m:reasons.append('LOW_HORIZONTAL_PHASE:'+PHASES[i])
    for a,b in ((1,2),(2,3),(5,6),(6,7)):
        if lateral(a,b)>alignment_tolerance_m:reasons.append('NOT_VERTICAL:'+PHASES[b])
    for low,high in ((2,3),(6,7)):
        if heights[high]-heights[low]<lift_clearance_m or heights[high]<approach_height_m:
            reasons.append('INSUFFICIENT_LIFT:'+PHASES[high])
    for a,b in ((0,1),(3,4),(4,5),(7,8)):
        if min(heights[a],heights[b])<approach_height_m:reasons.append('LOW_LATERAL_SEGMENT')
    for a,b in ((0,1),(4,5),(7,8)):
        if lateral(a,b)<=alignment_tolerance_m:reasons.append('MISSING_SIDE_APPROACH_OR_RETREAT')
    return dict(shape='FAIL' if reasons else 'PASS',reasons=sorted(set(reasons)),
                full_collision='UNKNOWN',scope='reference-point path shape only; swept arm/hand/table mesh not checked',
                motion_enabled=False)


def diagnostic_bundle(localized,c35,c49,*,refs,h0,plan_result=None):
    """Join existing reports without promoting a candidate or guessing missing inputs."""
    reasons=[]
    if not refs or not all(isinstance(v,str) and v for v in refs.values()):
        raise ValueError('versioned input references required')
    if localized.get('reference_comparison') is None:reasons.append('INDEPENDENT_RULER_REFERENCE_MISSING')
    elif localized['reference_comparison'].get('diagnostic_budget_met') is not True:reasons.append('RULER_ERROR_GATE_FAILED')
    if c35.get('approved') is not True or c35.get('report',{}).get('independent_validation')!='PASS':
        reasons.append('C35_NOT_INDEPENDENTLY_VALIDATED_AND_APPROVED')
    if localized.get('clock_error_bound_s') is None:reasons.append('CLOCK_ERROR_BOUND_UNKNOWN')
    if localized.get('exposure_to_output_s') is None:reasons.append('EXPOSURE_LATENCY_BOUND_UNKNOWN')
    if c49.get('approved') is not True:reasons.append('C49_GRASP_EXECUTION_ACCEPTANCE_PENDING')
    if plan_result is None:reasons.append('IK_TRAJECTORY_AND_FULL_COLLISION_NOT_PROVIDED')
    else:
        for key in ('config_hash','calibration_hash','collision_model_hash','scene_version'):
            if not plan_result.get(key):reasons.append('PLAN_CONTEXT_MISSING:'+key)
        if plan_result.get('feasible') is not True:reasons.append('PLAN_NOT_FEASIBLE')
        reasons.append('PRODUCTION_GATE_AND_PERMIT_REQUIRED')
    reasons+=['BLOCK_ORIENTATION_POLICY_NOT_BOUND','CURRENT_SEVEN_AXIS_STATE_NOT_BOUND',
              'TABLE_AND_FULL_ENVIRONMENT_MODEL_NOT_BOUND','REAL_PORT_AND_STOP_POLICY_NOT_BOUND']
    result=dict(schema_version='m-first-grasp-plan-bundle-diagnostic-1',source='recorded',
                input_refs=refs,localization_frame=c35['base_frame'],
                localization_points_ref=refs['localized_report'],
                grasp_version=c49.get('context',{}).get('grasp_version'),
                flange_frame=c49.get('target_frame'),
                grasp_transform_direction='T_flange_block; target flange = T_base_block @ inverse(T_flange_block)',
                temporary_C35_point_offset_used_as_TCP=False,
                flange_targets=None,plan_result=plan_result,
                error_budgets_m=h0['budget_m'],diagnostic_receive_freshness_s=h0['freshness_gate_s'],
                freshness_policy_status=h0['freshness_gate_status'],
                status='BLOCKED_FOR_EXECUTION',reasons=sorted(set(reasons)),
                permit=None,permit_request_allowed=False,motion_enabled=False,control_ready=False)
    result['bundle_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result


def flange_goal_from_declared_block_pose(block_pose,c49,*,declared_block_frame,grasp_version,
                                          same_grasp_assumption_confirmed):
    """Explicit hypothetical orientation + C49 transform, never an executable target."""
    from brick_stacking.localization.rigid_transforms import RigidTransform
    if same_grasp_assumption_confirmed is not True:
        raise ValueError('explicit same-grasp geometric assumption required')
    if grasp_version!=c49['context']['grasp_version'] or block_pose.source_frame!=declared_block_frame:
        raise ValueError('grasp version or declared block frame mismatch')
    held=RigidTransform(c49['target_frame'],declared_block_frame,np.asarray(c49['T_flange_block']),
                        'derived_unapproved',grasp_version,False)
    goal=block_pose.compose(held.inverse())
    return dict(target_frame=goal.target_frame,source_frame=goal.source_frame,matrix=goal.matrix.tolist(),
                grasp_version=grasp_version,orientation_source='caller_declared_not_observed',
                same_grasp_assumption=True,approved=False,motion_enabled=False)
