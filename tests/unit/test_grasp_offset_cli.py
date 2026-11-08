import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest


s = importlib.util.spec_from_file_location('grasp_cli',Path(__file__).parents[2]/'tools/solve_grasp_offset.py')
m = importlib.util.module_from_spec(s);s.loader.exec_module(m)


def dataset():
    d = {k:'synthetic-'+k for k in ('dataset_id','arm_device_id','model_version','joint_mapping_version','grasp_version','hand_binding_version','block_id','world_frame','flange_frame','block_frame','clock_domain','epoch','pose_basis_version')}
    d.update(source='synthetic',arm_role='left',units='m',trial_kind='continuous_hold',max_translation_residual_m=.001,max_rotation_residual_rad=.01,training=[],validation=[])
    offset = np.eye(4);offset[:3,3] = [.02,-.01,.08]
    for i in range(6):
        a = i*.2;c,t = np.cos(a),np.sin(a)
        f = np.eye(4);f[:3,:3] = [[c,-t,0],[t,c,0],[0,0,1]];f[:3,3] = [i*.1,.2,.3]
        r = {k:d[k] for k in ('clock_domain','epoch','grasp_version','block_id','pose_basis_version')}
        r.update(sample_id=str(i),flange_stamp_s=float(i),block_stamp_s=float(i),block_orientation_observed=True,T_world_flange=f.tolist(),T_world_block=(f@offset).tolist())
        d['training' if i<3 else 'validation'].append(r)
    return d


def test_named_flange_output_without_tcp_identity_assumption():
    d=dataset();r=m.solve(d)
    np.testing.assert_allclose(np.array(r['T_flange_block'])[:3,3],[.02,-.01,.08],atol=1e-12)
    assert r['target_frame']==d['flange_frame'] and r['report']['consistency']=='PASS'
    assert not r['approved'] and not r['motion_enabled']


@pytest.mark.parametrize('bad',['stamp','epoch','preset','orientation','missing_pose','leakage'])
def test_missing_or_unaligned_actual_grasp_input_rejected(bad):
    d=dataset();r=d['validation'][0]
    if bad=='stamp':r['block_stamp_s']+=.01
    elif bad=='epoch':r['epoch']='other'
    elif bad=='preset':r['grasp_version']='other'
    elif bad=='orientation':r['block_orientation_observed']=False
    elif bad=='missing_pose':r['T_world_block']=None
    elif bad=='leakage':r['sample_id']=d['training'][0]['sample_id']
    with pytest.raises(ValueError):m.solve(d)


def test_validation_slip_preserved_as_failure():
    d=dataset();d['validation'][-1]['T_world_block'][0][3]+=.01
    assert m.solve(d)['report']['consistency']=='FAIL'
