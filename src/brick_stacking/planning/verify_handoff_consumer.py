"""Consume V's side-car through M's existing source/evidence checks, offline only."""
from brick_stacking.planning.placement_bridge import (
    LocalizedReviewEvidence, audit_bundle, to_shadow_inspection)
from brick_stacking.planning.placement_review import ErrorBound
from brick_stacking.planning.yaw_policy import (
    normalize_yaw_policy, yaw_unknown_allowed_by_policy)


def consume_handoff(row,bundle,binding,*,context,now_s,expected_color):
    """Return (Inspection|None, diagnostic). No defaults for unknown measurements."""
    audit=audit_bundle(bundle,binding,now_s=now_s,expected_color=expected_color)
    reasons=list(audit['problems']);timing=bundle.get('timing',{})
    if row.get('schema_version') not in ('v-verify-field-handoff-0.1','v-verify-field-handoff-0.2'):
        reasons.append('HANDOFF_SCHEMA_MISMATCH')
    if (row.get('schema_version')=='v-verify-field-handoff-0.2' and
            row.get('formal_verify_point_kind')!='model_center'):
        reasons.append('FORMAL_MODEL_CENTER_SEMANTICS_REQUIRED')
    expected=dict(sample_id=bundle['rgbd']['sample_id'],
                  observation_id=audit['selected_observation_id'],
                  frame_id=bundle['rgbd']['frame_id'],profile_hash=bundle.get('profile_hash'),
                  calibration_hash=bundle.get('calibration_hash'),epoch=bundle['rgbd']['epoch'],
                  clock_domain=timing.get('host_clock_domain'),
                  exposure_host_stamp_s=timing.get('exposure_host_stamp_s'),
                  clock_error_bound_s=timing.get('clock_error_bound_s'),
                  error_bound_evidence_ref=timing.get('error_bound_evidence_ref'),
                  expected_color=expected_color)
    if any(row.get(k)!=v for k,v in expected.items()):
        reasons.append('SIDECAR_SOURCE_FIELDS_MISMATCH')
    if row.get('color_check')!=audit['observed_candidate_color_check']:
        reasons.append('SIDECAR_COLOR_DIAGNOSTIC_MISMATCH')
    if row.get('target_association_confirmed') is not True:
        reasons.append('TARGET_ASSOCIATION_UNCONFIRMED')
    if not row.get('target_id') or not row.get('region_id'):
        reasons.append('TARGET_OR_REGION_MISSING')
    if not row.get('reference_id'):reasons.append('REFERENCE_MISSING')
    if not bundle.get('calibration_hash'):reasons.append('CALIBRATION_BINDING_MISSING')
    if context is None:reasons.append('M_CONTEXT_MISSING')
    elif row.get('target_id')!=context.target_id or row.get('scope')!=context.scope:
        reasons.append('M_TARGET_CONTEXT_MISMATCH')
    if row.get('point_kind')!='visible_top_center':reasons.append('TOP_CENTER_SEMANTICS_REQUIRED')
    if row.get('control_ready') is not False:reasons.append('UNEXPECTED_SIDECAR_PROMOTION')
    bounds={}
    yaw_policy=normalize_yaw_policy(row.get('yaw_policy'))
    yaw_policy_applied=None
    for name in ('xy_m','height_m','yaw_rad'):
        metric=row.get(name) or {}
        if name=='yaw_rad' and yaw_unknown_allowed_by_policy(metric,row.get('yaw_policy')):
            # Keep yaw UNKNOWN; do not invent MEASURED value/bound. Inspection.yaw_rad=None.
            bounds[name]=None
            yaw_policy_applied=yaw_policy['id']
            continue
        if metric.get('status')!='MEASURED':
            reasons.append('ERROR_BOUND_UNKNOWN:'+name);continue
        try:
            # None/bool/string/NaN are not measurement bounds.
            if any(type(metric.get(k)) not in (float,int) for k in ('value','bound')):
                raise ValueError('invalid metric type')
            bounds[name]=ErrorBound(metric['value'],metric['bound'])
        except (ValueError,TypeError):reasons.append('ERROR_BOUND_INVALID:'+name)
    if type(row.get('hand_clear')) is not bool:
        reasons.append('HAND_CLEAR_EVIDENCE_MISSING')
    for name in ('support_ok','stable','neighbors_unchanged'):
        if row.get(name) is not None and type(row[name]) is not bool:
            reasons.append('EVIDENCE_TYPE_INVALID:'+name)
    inspection=None
    if not reasons:
        evidence=LocalizedReviewEvidence(context,row['sample_id'],row['observation_id'],
                    row['reference_id'],row['point_kind'],True,bounds['xy_m'],bounds['height_m'],
                    bounds['yaw_rad'],row.get('support_ok'),row.get('stable'),row['hand_clear'],
                    row.get('neighbors_unchanged'))
        try:
            inspection=to_shadow_inspection(bundle,binding,evidence,now_s=now_s,
                                             expected_color=expected_color)
        except ValueError as error:reasons.append('M_BINDING_REJECTED:'+str(error))
    diagnostic=dict(status='SHADOW_INSPECTION_READY' if inspection else 'BLOCKED',
                    reasons=sorted(set(reasons)),
                    observation_id=row.get('observation_id'),
                    color_diagnostic=audit['observed_candidate_color_check'],
                    formal_placement_verdict='UNKNOWN',control_ready=False,
                    motion_enabled=False,permit=None)
    if yaw_policy_applied:
        diagnostic['yaw_policy_applied']=yaw_policy_applied
        diagnostic['yaw_bound_source']='POLICY_UNBOUNDED_NOT_MEASURED'
        diagnostic['yaw_rad_status']='UNKNOWN'
    return inspection,diagnostic
