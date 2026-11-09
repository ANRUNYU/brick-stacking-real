"""Recorded cube center + exposure-associated upstream FK -> one pose candidate.

Selects the first vision-qualified image, never the lowest calibration residual.
Retains failed image decisions. Timing remains provisional, approval stays false.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics

MODEL_SHA256='233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root,centers,association,urdf,*,group,operator_evidence):
    root=Path(root)
    if group not in ('training','validation') or not operator_evidence:
        raise ValueError('preassigned train/validation group and operator mounting evidence required')
    manifest=json.loads((root/'record_manifest.json').read_text());camera=json.loads((root/'camera/camera_report.json').read_text())
    if not manifest.get('attachment_id') or manifest.get('reference_frame')!='L5_Link' or manifest.get('target_writes')!=0 or manifest.get('enable_rest_zero_flash_commands')!=0:
        raise ValueError('explicit upstream attachment and reviewed READ-only capture required')
    if 'unconfirmed' in manifest['attachment_id'] or digest(urdf)!=MODEL_SHA256:
        raise ValueError('unconfirmed attachment or model hash mismatch')
    if association.get('schema_version')!='c-camera-upstream-association-1' or association.get('clock_domain')!='host_monotonic' or association.get('epoch')!=manifest['quality']['clock_epoch']:
        raise ValueError('compatible measured exposure association and boot epoch required')
    if association.get('timing_acceptance')!='NOT_VALIDATED' or association.get('approved') is not False or association.get('source') not in ('real','recorded','synthetic'):
        raise ValueError('only explicit provisional timing/source supported by this tool')
    by_sha={r['frame_sha256']:r for r in centers}
    if len(by_sha)!=len(centers):raise ValueError('duplicate image center evidence')
    decisions=[];selected=None
    for row in association['samples']:
        filename=row['image_file']
        if Path(filename).name!=filename:raise ValueError('frame must be within capture camera directory')
        path=root/'camera'/filename;sha=digest(path);center=by_sha.get(sha)
        if center is None:raise ValueError('center evidence missing for captured image')
        quality=center['quality'].get('consistency','REJECTED')
        decisions.append(dict(image_file=filename,frame_sha256=sha,vision_quality=quality,reason=center['quality'].get('reason')))
        if quality=='PASS' and selected is None:selected=(row,center,path,sha)
    if selected is None:raise ValueError('no vision-qualified image; keep rejected capture, no pose output')
    for rejected in association.get('frame_rejections',[]):
        filename=rejected['image_file'];path=root/'camera'/filename
        if Path(filename).name!=filename:raise ValueError('rejected frame must remain in capture directory')
        sha=digest(path);center=by_sha.get(sha)
        decisions.append(dict(image_file=filename,frame_sha256=sha,vision_quality=center['quality'].get('consistency','REJECTED') if center else 'NOT_AVAILABLE',
                              exposure_qualification='REJECTED',reason=rejected['reason']))
    order={frame['file']:i for i,frame in enumerate(camera['frames'])} if camera.get('frames') else {}
    decisions.sort(key=lambda r:order.get(r['image_file'],0))
    row,center,path,sha=selected
    with np.load(path,allow_pickle=False) as data:meta=json.loads(str(data['metadata'].item()))
    if center['camera_serial']!=manifest['camera_serial'] or meta['camera_id']!=manifest['camera_serial'] or center['camera_stamp_s']!=meta['stamp_s'] or center['camera_clock_domain']!=meta['clock_domain']:
        raise ValueError('camera/frame timestamp provenance mismatch')
    pose,_=urdf_forward_kinematics(urdf,row['joint_positions_sdk_rad'],base_frame='L_arm_root',tip_frame='L5_Link')
    c=np.asarray(center['center_camera_m'],float)
    if c.shape!=(3,) or not np.isfinite(c).all() or c[2]<=0:raise ValueError('finite observed optical center required')
    profile=dict(profiles=camera['profiles'],aligned_geometry=camera['aligned_geometry'],serial=manifest['camera_serial'])
    hash_json=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    geometry=center.get('target_geometry',dict(edge_m=center['config']['edge_m'],edge_source=center['config']['edge_source']))
    context=dict(source=association['source'],units='m',arm_role='left',base_frame='L_arm_root',reference_frame='L5_Link',attachment_reference_frame='L5_Link',
                 camera_serial=manifest['camera_serial'],camera_frame=meta['frame_id'],camera_profile_version=hash_json(profile),
                 arm_device_id='operator_selected_left_P7_can2_61_to_67',model_version=MODEL_SHA256,
                 joint_mapping_version='left_can2_61_to_65_read06_float32_sdk_v1',target_id=center.get('target_id','C35_calibration_cube_50mm'),
                 target_geometry_version=hash_json(geometry),attachment_version=manifest['attachment_id'],
                 clock_domain=association['clock_domain'],epoch=association['epoch'],observation_kind='point_center')
    time_evidence=dict(method='SDK global exposure mapping + bracketed linear joint interpolation',timing_acceptance='NOT_VALIDATED',
                       device_to_host_mapping_error_bound_s=None,original_camera_stamp_s=meta['stamp_s'],original_camera_clock_domain=meta['clock_domain'],
                       clock_observation=row['clock_observation'],joint_brackets=row['joint_brackets'])
    sample=dict(sample_id=manifest['pose_id'],image_id=sha,joint_sample_id=manifest['pose_id']+'_'+row['image_file']+'_exposure_interpolation',
                target_rigidly_fixed=True,operator_evidence=operator_evidence,center_quality='PASS',center_camera_m=c.tolist(),
                T_base_reference=pose.matrix.tolist(),reference_stamp_s=row['association_host_monotonic_s'],center_stamp_s=row['association_host_monotonic_s'],
                time_alignment_evidence=time_evidence,
                **{key:context[key] for key in ('camera_profile_version','target_geometry_version','attachment_version','clock_domain','epoch')})
    return dict(schema_version='c-fixed-camera-point-prepared-1',group=group,context=context,sample=sample,
                frame_decisions=decisions,selection='first image with PASS vision quality in capture order; before any extrinsic fit',
                record_manifest_sha256=digest(root/'record_manifest.json'),joint_cycles_sha256=digest(root/'joint_cycles.json'),
                qualification='PROVISIONAL_TIMING',calibration_sample_valid=False,approved=False,motion_enabled=False)


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('capture','centers','urdf','output'):p.add_argument(name,type=Path)
    p.add_argument('--group',choices=['training','validation'],required=True);p.add_argument('--operator-evidence',required=True)
    for name in ('max-bracket-gap-s','max-bracket-step-rad','max-rgb-depth-skew-s'):p.add_argument('--'+name,type=float,required=True)
    a=p.parse_args()
    from associate_camera_joint_samples import associate_qualified_frames
    association=associate_qualified_frames(json.loads((a.capture/'joint_cycles.json').read_text()),json.loads((a.capture/'camera/camera_report.json').read_text()),
                          max_bracket_gap_s=a.max_bracket_gap_s,max_bracket_step_rad=a.max_bracket_step_rad,max_rgb_depth_skew_s=a.max_rgb_depth_skew_s)
    r=prepare(a.capture,json.loads(a.centers.read_text()),association,a.urdf,group=a.group,operator_evidence=a.operator_evidence)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
