"""Recorded pivot TCP candidate + independent holdout validation, never approved."""
import argparse,json
from pathlib import Path
import numpy as np
from brick_stacking.localization.calibration import solve_pivot_tcp
from brick_stacking.localization.rigid_transforms import RigidTransform


def solve(data):
    for key in ('dataset_id','arm_role','model_version','joint_mapping_version','device_id','clock_domain','epoch','operator'):
        if not isinstance(data.get(key),str) or not data[key]:raise ValueError('explicit pivot session metadata required: '+key)
    if data.get('source') not in ('synthetic','recorded','real') or data.get('units')!='m':raise ValueError('explicit source and metre units required')
    if data['arm_role']!='left':raise ValueError('current task is selected left arm only')
    train,validation=data['training'],data['validation']
    if len(train)<4 or len(validation)<4:raise ValueError('at least 4 training and 4 independent validation poses required')
    rows=train+validation;ids=[r['sample_id'] for r in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise ValueError('distinct sample IDs required')
    transforms=[]
    for r in rows:
        if r.get('clock_domain')!=data['clock_domain'] or r.get('epoch')!=data['epoch']:raise ValueError('clock/epoch mismatch')
        transforms.append(RigidTransform(data['base_frame'],data['flange_frame'],r['T_base_flange'],'synthetic' if data['source']=='synthetic' else 'recorded',stamp_s=r['host_stamp_s'],clock_domain=data['clock_domain']))
    result=solve_pivot_tcp(transforms[:len(train)])
    p=np.array(result['tcp_translation_flange_m']);pivot=np.array(result['pivot_base_m'])
    errors=np.array([np.linalg.norm(t.apply(p)-pivot) for t in transforms[len(train):]])
    result.update(schema_version='c-pivot-candidate-1',dataset_id=data['dataset_id'],source=data['source'],model_version=data['model_version'],joint_mapping_version=data['joint_mapping_version'],training_ids=ids[:len(train)],validation_ids=ids[len(train):],validation=dict(n=len(errors),rmse_m=float(np.sqrt(np.mean(errors**2))),p95_m=float(np.percentile(errors,95)),max_m=float(errors.max())),motion_enabled=False,notice='candidate translation only; TCP rotation and physical acceptance remain unknown')
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=solve(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
