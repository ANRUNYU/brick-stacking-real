"""Joint fixed-camera extrinsic / rigid calibration target candidate. No device access."""
import argparse
import json
from pathlib import Path
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.fixed_camera_calibration import solve_fixed_camera
from brick_stacking.localization.point_target_calibration import solve_point_target


def solve(data):
    kind=data.get('observation_kind','target_pose')
    if kind not in ('target_pose','point_center'):raise ValueError('explicit supported observation kind required')
    point_mode=kind=='point_center'
    context=('dataset_id','camera_serial','camera_profile_version','arm_device_id','model_version',
             'joint_mapping_version','target_id','target_geometry_version','attachment_version','clock_domain','epoch')
    for key in context:
        if not isinstance(data.get(key),str) or not data[key].strip():raise ValueError('explicit context required: '+key)
    if data.get('source') not in ('synthetic','recorded','real') or data.get('units')!='m' or data.get('arm_role')!='left':
        raise ValueError('selected-left source and metre units required')
    reference=data.get('reference_frame',data.get('flange_frame'))
    if not isinstance(reference,str) or not reference:raise ValueError('explicit reference link required')
    upstream='reference_frame' in data
    if upstream and data.get('attachment_reference_frame')!=reference:
        raise ValueError('target must be attached rigidly to the declared reference link')
    groups=[];images=[];joint_samples=[]
    signature=('camera_profile_version','target_geometry_version','attachment_version','clock_domain','epoch')
    for group in ('training','validation'):
        parsed=[]
        for row in data[group]:
            for key in signature:
                if row.get(key)!=data[key]:raise ValueError('sample context mismatch: '+key)
            if row.get('target_rigidly_fixed') is not True or (not point_mode and row.get('target_orientation_observed') is not True):
                raise ValueError('rigid target and observed unambiguous orientation required')
            if row.get('center_quality' if point_mode else 'vision_validation')!='PASS' or not row.get('time_alignment_evidence'):
                raise ValueError('validated target pose and explicit time alignment evidence required')
            for key,values in (('image_id',images),('joint_sample_id',joint_samples)):
                if not isinstance(row.get(key),str) or not row[key]:raise ValueError('unique image/joint evidence IDs required')
                values.append(row[key])
            clock=json.dumps([data['clock_domain'],data['epoch']],separators=(',',':'))
            a=RigidTransform(data['base_frame'],reference,row['T_base_reference' if upstream else 'T_base_flange'],data['source'],stamp_s=row['reference_stamp_s' if upstream else 'flange_stamp_s'],clock_domain=clock)
            if point_mode:parsed.append((row['sample_id'],a,row['center_camera_m'],row['center_stamp_s'],clock))
            else:
                b=RigidTransform(data['camera_frame'],data['target_frame'],row['T_camera_target'],data['source'],stamp_s=row['target_stamp_s'],clock_domain=clock)
                parsed.append((row['sample_id'],a,b))
        groups.append(parsed)
    if len(set(images))!=len(images) or len(set(joint_samples))!=len(joint_samples):
        raise ValueError('same image/joint sample reused; training/validation evidence leakage')
    if point_mode:
        x,report=solve_point_target(*groups,camera_frame=data['camera_frame'],candidate_id=data['dataset_id'],
                                  max_residual_m=data['max_translation_residual_m'],max_condition_number=data['max_condition_number'])
        return dict(schema_version=report['schema_version'],source=data['source'],context={k:data[k] for k in context},
                    base_frame=x.target_frame,camera_frame=x.source_frame,reference_frame=reference,
                    T_base_camera=x.matrix.tolist(),point_offset_reference_m=report['point_offset_reference_m'],
                    point_orientation_xyzw=None,report=report,approved=False,motion_enabled=False,
                    notice='unmarked point center mode; no labelled target orientation, grasp offset or physical approval')
    x,y,report=solve_fixed_camera(*groups,candidate_id=data['dataset_id'],
                    max_translation_residual_m=data['max_translation_residual_m'],
                    max_rotation_residual_rad=data['max_rotation_residual_rad'],
                    max_condition_number=data['max_condition_number'])
    result=dict(schema_version=report['schema_version'],source=data['source'],context={k:data[k] for k in context},
                base_frame=x.target_frame,camera_frame=x.source_frame,reference_frame=y.target_frame,target_frame=y.source_frame,
                T_base_camera=x.matrix.tolist(),T_reference_target=y.matrix.tolist(),report=report,
                approved=False,motion_enabled=False,
                notice='calibration-target mount is not a grasp offset; physical validation still required')
    if not upstream:result.update(flange_frame=y.target_frame,T_flange_target=y.matrix.tolist())
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=solve(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
