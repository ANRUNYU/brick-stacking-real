"""Bind independent table-cross ruler data; never infer a base frame from one point."""
from math import isfinite
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def reference_for_c35(reference,bridge,*,base_frame):
    """Bridge must be independently established, with a bound at this target point."""
    if bridge is None:
        raise ValueError('independent table-cross to base frame bridge required')
    if (bridge.get('independent') is not True or bridge.get('verified') is not True or
            not bridge.get('evidence_ref') or not bridge.get('version') or
            bridge.get('target_frame')!=base_frame):
        raise ValueError('verified independent bridge and version required')
    measured=reference['summary_for_M']['recommended_block_reference_m']
    if bridge.get('source_frame')!=measured['frame'] or measured['unit']!='m':
        raise ValueError('bridge source frame/units mismatch')
    if measured['point']!='red_top_center_via_table_projection_plus_height':
        raise ValueError('ruler point semantics mismatch')
    error=bridge.get('point_error_bound_m');ruler_error=measured['estimated_error_m']
    if not all(type(x) in (float,int) and isfinite(x) and x>=0 for x in (error,ruler_error)):
        raise ValueError('finite bounds including bridge angular effect at target required')
    transform=RigidTransform(base_frame,measured['frame'],np.asarray(bridge['matrix'],float),
                             'derived_unapproved',bridge['version'],False)
    point=transform.apply(measured['xyz'])
    return dict(frame_id=base_frame,point_kind='visible_top_center',point_m=point.tolist(),
                table_normal_base=(transform.matrix[:3,:3]@np.array([0.,0.,1.])).tolist(),
                measurement_error_bound_m=error+ruler_error,independent=True,
                evidence_ref=bridge['evidence_ref'],bridge_version=bridge['version'])


def audit_ruler(reference,*,bridge=None,base_frame='L_arm_root'):
    """Preserve measured reference while declaring exact missing frame relation."""
    geo=reference['accepted_scene_mm']
    hyp=float(np.hypot(geo['cross_left_of_center_column'],
                       geo['cross_foreaft_from_center_column']['value']))
    result=dict(schema_version='m-ruler-reference-audit-1',
                reference_available=True,reference_frame='table_black_cross_20mm',
                base_frame=base_frame,base_reference=None,
                j1_equals_base_confirmed=False,
                cross_column_horizontal_closure_residual_mm=abs(
                    hyp-geo['cross_to_center_column_horizontal']['measured']),
                j1_height_spread_mm=geo['J1_height_above_table']['spread_mm'],
                control_ready=False,motion_enabled=False,permit=None)
    if bridge is None:
        result.update(status='FRAME_BRIDGE_REQUIRED',missing=[
            'J1 axis center versus L_arm_root origin relation',
            'table-cross to base orientation and translation, independently verified',
            'bridge error bound including rotation contribution at reference point',
            'camera mount/frame convention unchanged since C35 independently confirmed'])
    else:
        result.update(status='DIAGNOSTIC_REFERENCE_READY',
                      base_reference=reference_for_c35(reference,bridge,base_frame=base_frame),
                      missing=['C35 independent validation/approval and remaining execution gates'])
    return result
