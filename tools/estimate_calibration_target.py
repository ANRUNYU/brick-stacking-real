"""Observed target pose from explicitly identified measured 3-D landmarks."""
import argparse
import json
from pathlib import Path
from brick_stacking.localization.target_pose import estimate_target_pose


def solve(data):
    metadata=('sample_id','image_id','image_sha256','camera_serial','camera_frame','target_frame',
              'camera_profile_version','target_geometry_version','annotation_evidence','clock_domain','epoch')
    for key in metadata:
        if not isinstance(data.get(key),str) or not data[key]:raise ValueError('explicit image/target provenance required: '+key)
    if data.get('source') not in ('synthetic','recorded','real') or data.get('units')!='m' or data.get('landmark_identity_confirmed') is not True:
        raise ValueError('identified metric landmarks and explicit source required')
    train,check=data['training'],data['validation']
    ids=[row['landmark_id'] for row in train+check]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise ValueError('unique training/validation landmark IDs required')
    pose,report=estimate_target_pose([r['xyz_m'] for r in train],[r['pixel_xy'] for r in train],
                [r['xyz_m'] for r in check],[r['pixel_xy'] for r in check],K=data['K'],distortion=data['distortion'],
                image_size_px=data['image_size_px'],pixel_space=data['pixel_space'],camera_frame=data['camera_frame'],
                target_frame=data['target_frame'],stamp_s=data['host_stamp_s'],
                clock_domain=json.dumps([data['clock_domain'],data['epoch']],separators=(',',':')),
                candidate_id=data['sample_id'],max_reprojection_error_px=data['max_reprojection_error_px'])
    return dict(schema_version=report['schema_version'],source=data['source'],metadata={k:data[k] for k in metadata},
                target_stamp_s=data['host_stamp_s'],T_camera_target=pose.matrix.tolist(),vision_validation=report['consistency'],
                report=report,approved=False,motion_enabled=False,
                notice='landmark identity/dimensions and original image must be externally audited; not absolute physical accuracy')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    r=solve(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
