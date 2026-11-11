"""Offline V single-red bundles -> C35 base points. Never emits motion permission."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def diagnose(bundles,calibration,*,calibration_hash,reference=None):
    transform=RigidTransform(calibration['base_frame'],calibration['camera_frame'],
                             np.array(calibration['T_base_camera']),
                             'derived_unapproved',calibration_hash,False)
    rows=[]
    for bundle in bundles:
        if bundle.get('control_ready') is not False:
            raise ValueError('expected non-executable V bundle')
        rgbd=bundle['rgbd']
        if rgbd['device_id']!=calibration['context']['camera_serial'] or rgbd['frame_id']!=transform.source_frame:
            raise ValueError('camera identity/frame mismatch')
        blocks=bundle['blocks']
        if len(blocks)!=1 or blocks[0]['color']!='red' or blocks[0]['validity']!='VALID':
            raise ValueError('single valid red sample required')
        block=blocks[0];ext=block['b_extensions']
        if block['frame_id']!=transform.source_frame or ext.get('top_surface_point_kind')!='visible_top_center':
            raise ValueError('explicit camera-frame visible top center required')
        top=transform.apply(ext['top_surface_point_camera_m'])
        model=transform.apply(ext['model_center_camera_m'])
        rows.append(dict(observation_id=block['observation_id'],sample_id=rgbd['sample_id'],
                         frame_id=transform.target_frame,top_center_base_m=top.tolist(),
                         model_center_base_m=model.tolist(),orientation_xyzw=None,
                         source_stamp_s=rgbd['device_stamp'],clock_domain=rgbd['clock_domain'],
                         epoch=rgbd['epoch'],control_ready=False))
    if not rows:raise ValueError('no observations')
    if len({r['observation_id'] for r in rows})!=len(rows):raise ValueError('duplicate observation')
    if len({(r['clock_domain'],r['epoch']) for r in rows})!=1:raise ValueError('mixed capture sessions')
    if any(b['source_stamp_s']<=a['source_stamp_s'] for a,b in zip(rows,rows[1:])):raise ValueError('nonincreasing source time')
    points=np.array([r['top_center_base_m'] for r in rows]);median=np.median(points,axis=0)
    error=None
    if reference is not None:
        if reference['frame_id']!=transform.target_frame or reference['point_kind']!='visible_top_center':
            raise ValueError('reference frame/point semantics mismatch')
        point=np.asarray(reference['point_m'],float);normal=np.asarray(reference['table_normal_base'],float)
        bound=reference['measurement_error_bound_m']
        if (point.shape!=(3,) or normal.shape!=(3,) or not np.isfinite(point).all() or not np.isfinite(normal).all() or
            not np.isclose(np.linalg.norm(normal),1) or not np.isfinite(bound) or bound<0):
            raise ValueError('finite independent reference and unit table normal required')
        if reference.get('independent') is not True:raise ValueError('independent reference required')
        residual=points-point;height=np.abs(residual@normal)
        planar=np.linalg.norm(residual-(residual@normal)[:,None]*normal,axis=1)
        error=dict(planar_max_m=float(planar.max()),height_max_m=float(height.max()),
                   reference_measurement_error_bound_m=bound,
                   conservative_planar_with_reference_bound_m=float(planar.max()+bound),
                   conservative_height_with_reference_bound_m=float(height.max()+bound),
                   diagnostic_budget_met=bool(planar.max()+bound<=.01 and height.max()+bound<=.008))
    timings=[b.get('timing',{}) for b in bundles]
    valid_timing=all(t.get('validity')=='VALID' and
                     type(t.get('clock_error_bound_s')) in (int,float) and
                     np.isfinite(t['clock_error_bound_s']) and t['clock_error_bound_s']>0 and
                     t.get('error_bound_evidence_ref') and
                     type(t.get('exposure_to_output_s')) in (int,float) and
                     np.isfinite(t['exposure_to_output_s']) and t['exposure_to_output_s']>=0
                     for t in timings)
    return dict(schema_version='m-h0-c35-diagnostic-1',rows=rows,frames=len(rows),
                transform_direction='T_base_camera maps camera points into base',
                calibration_hash=calibration_hash,calibration_status=calibration.get('calibration_status'),
                calibration_independent_validation=calibration.get('independent_validation'),
                median_top_center_base_m=median.tolist(),
                max_deviation_from_median_m=float(np.linalg.norm(points-median,axis=1).max()),
                repeatability_is_not_absolute_accuracy=True,reference_comparison=error,
                ruler_acceptance='NOT_PERFORMED_REFERENCE_MISSING' if error is None else 'DIAGNOSTIC_ONLY',
                clock_error_bound_s=max(t['clock_error_bound_s'] for t in timings) if valid_timing else None,
                exposure_to_output_s=max(t['exposure_to_output_s'] for t in timings) if valid_timing else None,
                exposure_latency_scope='recorded measured maximum, not a future runtime bound',
                live_freshness_checked=False,control_ready=False,motion_enabled=False,
                warnings=['Camera mount unchanged must be separately established.',
                          'C35 uses a different capture profile; identical optical-frame convention must be confirmed.',
                          'A camera-to-base point transform is not TCP or a motion permit.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundles',type=Path,required=True);p.add_argument('--calibration',type=Path,required=True)
    p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('output exists')
    calibration=json.loads(a.calibration.read_text(encoding='utf-8'))
    rows=[json.loads(line) for line in a.bundles.read_text(encoding='utf-8').splitlines() if line.strip()]
    report=diagnose(rows,calibration,calibration_hash=hashlib.sha256(a.calibration.read_bytes()).hexdigest(),
                    reference=json.loads(a.reference.read_text(encoding='utf-8')) if a.reference else None)
    report['input_bundles_sha256']=hashlib.sha256(a.bundles.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['frames','median_top_center_base_m','max_deviation_from_median_m','ruler_acceptance','control_ready']}))


if __name__=='__main__':main()
