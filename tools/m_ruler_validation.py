"""Independent ruler handoff + C35 offline diagnostic, no inferred base-frame pose."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
from copy import deepcopy
import numpy as np
from brick_stacking.localization.ruler_reference import audit_ruler
from brick_stacking.localization.rigid_transforms import RigidTransform


def validate(root,*,bridge=None,camera_bridge=None):
    field=root/'docs/team/B/evidence/field_20261110'
    rp=field/'independent_ruler_reference_v0.1.json'
    bp=field/'ruler_bind_observation_bundles.jsonl'
    cp=root/'calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json'
    ref=json.loads(rp.read_text(encoding='utf-8'));c=json.loads(cp.read_text(encoding='utf-8'))
    rows=[json.loads(x) for x in bp.read_text(encoding='utf-8').splitlines() if x.strip()]
    raw_median=np.median(np.array([r['blocks'][0]['b_extensions']['top_surface_point_camera_m']
                                   for r in rows]),axis=0).tolist()
    audit=audit_ruler(ref,bridge=bridge,base_frame=c['base_frame'])
    diagnose=runpy.run_path(str(root/'tools/h0_c35_diagnostic.py'))['diagnose']
    source_frames=sorted(set(r['rgbd']['frame_id'] for r in rows))
    source_check=dict(observed_frames=source_frames,c35_camera_frame=c['camera_frame'],
                      status='MATCH' if source_frames==[c['camera_frame']] else 'FRAME_CONVENTION_UNCONFIRMED')
    if camera_bridge is not None:
        if (len(source_frames)!=1 or camera_bridge.get('verified') is not True or
                not camera_bridge.get('evidence_ref') or not camera_bridge.get('version') or
                camera_bridge.get('source_frame')!=source_frames[0] or
                camera_bridge.get('target_frame')!=c['camera_frame']):
            raise ValueError('explicit verified camera-frame relation required')
        transform=RigidTransform(c['camera_frame'],source_frames[0],np.array(camera_bridge['matrix']),
                                 'derived_unapproved',camera_bridge['version'],False)
        rows=deepcopy(rows)
        for row in rows:
            row['rgbd']['frame_id']=c['camera_frame']
            for block in row['blocks']:
                if block['frame_id']!=source_frames[0]:raise ValueError('block frame differs from source')
                block['frame_id']=c['camera_frame'];ext=block['b_extensions']
                for key in ('top_surface_point_camera_m','model_center_camera_m'):
                    ext[key]=transform.apply(ext[key]).tolist()
        source_check.update(status='EXPLICIT_BRIDGE_APPLIED',bridge=camera_bridge)
    localized=None
    if source_check['status'] in ('MATCH','EXPLICIT_BRIDGE_APPLIED'):
        localized=diagnose(rows,c,calibration_hash=hashlib.sha256(cp.read_bytes()).hexdigest(),
                           reference=audit['base_reference'])
    # Orientation-invariant sanity check ONLY under the unconfirmed J1=base-origin hypothesis.
    j=ref['summary_for_M']['recommended_J1_relative_to_cross_mm']
    j1=np.array([j['robot_right'],j['toward_robot'],j['above_table']])/1000.
    red=np.array(ref['summary_for_M']['recommended_block_reference_m']['xyz'])
    measured_radius=float(np.linalg.norm(red-j1))
    transformed_radius=float(np.linalg.norm(localized['median_top_center_base_m'])) if localized else None
    return dict(schema_version='m-ruler-validation-handoff-1',ruler_audit=audit,
                source_frame_check=source_check,source_frames_count=len(rows),
                raw_top_center_source_frame_median_m=raw_median,
                localize=localized,conditional_radius_check=dict(
                    assumption='J1 axis center equals L_arm_root origin; NOT CONFIRMED',
                    ruler_radius_m=measured_radius,c35_radius_m=transformed_radius,
                    absolute_radius_difference_m=abs(measured_radius-transformed_radius) if localized else None,
                    acceptance='NOT_AN_XY_OR_HEIGHT_ACCEPTANCE',
                    note='One distance cannot recover orientation; ruler J1 height spread is 7 mm.'),
                input_sha256={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (rp,bp,cp)},control_ready=False,motion_enabled=False,
                commands_sent=0,permit=None)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bridge',type=Path,help='independently verified frame bridge JSON, no default')
    p.add_argument('--camera-frame-bridge',type=Path,help='verified head-to-C35-camera relation, no identity default')
    a=p.parse_args();bridge=json.loads(a.bridge.read_text(encoding='utf-8')) if a.bridge else None
    camera_bridge=json.loads(a.camera_frame_bridge.read_text(encoding='utf-8')) if a.camera_frame_bridge else None
    report=validate(Path(__file__).resolve().parents[1],bridge=bridge,camera_bridge=camera_bridge)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(frames=report['source_frames_count'],
                         ruler_status=report['ruler_audit']['status'],
                         source_frame_status=report['source_frame_check']['status'],
                         base_top_center_m=report['localize']['median_top_center_base_m'] if report['localize'] else None,
                         conditional_radius=report['conditional_radius_check'],control_ready=False)))


if __name__=='__main__':main()
