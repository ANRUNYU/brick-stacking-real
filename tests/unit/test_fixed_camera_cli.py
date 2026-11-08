import importlib.util
from pathlib import Path
import cv2
import numpy as np
import pytest

s=importlib.util.spec_from_file_location('fixed_camera_cli',Path(__file__).parents[2]/'tools/solve_fixed_camera.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def dataset():
    d={k:'synthetic-'+k for k in ('dataset_id','camera_serial','camera_profile_version','arm_device_id','model_version','joint_mapping_version','target_id','target_geometry_version','attachment_version','clock_domain','epoch')}
    d.update(source='synthetic',units='m',arm_role='left',base_frame='base',flange_frame='flange',camera_frame='camera',target_frame='target',max_translation_residual_m=.001,max_rotation_residual_rad=.01,max_condition_number=1e6,training=[],validation=[])
    rng=np.random.default_rng(13);x=np.eye(4);x[:3,3]=[.4,-.2,.9];y=np.eye(4);y[:3,3]=[.02,.03,.1]
    for i in range(10):
        a=np.eye(4);a[:3,:3]=cv2.Rodrigues(rng.normal(size=3)*.5)[0];a[:3,3]=rng.normal(size=3)*.2
        b=np.linalg.inv(x)@a@y
        row={k:d[k] for k in ('camera_profile_version','target_geometry_version','attachment_version','clock_domain','epoch')}
        row.update(sample_id=str(i),image_id=f'image-{i}',joint_sample_id=f'joint-{i}',target_rigidly_fixed=True,target_orientation_observed=True,vision_validation='PASS',time_alignment_evidence='synthetic-clock-truth',flange_stamp_s=float(i),target_stamp_s=float(i),T_base_flange=a.tolist(),T_camera_target=b.tolist())
        d['training' if i<6 else 'validation'].append(row)
    return d


def test_complete_metadata_reaches_existing_tf_solver():
    r=m.solve(dataset());assert r['report']['consistency']=='PASS' and not r['approved']
    np.testing.assert_allclose(np.array(r['T_base_camera'])[:3,3],[.4,-.2,.9],atol=1e-10)


@pytest.mark.parametrize('bad',['image_reuse','joint_reuse','mount','orientation','slip','clock','vision','alignment','matrix'])
def test_missing_actual_evidence_rejected(bad):
    d=dataset();r=d['validation'][0]
    if bad=='image_reuse':r['image_id']=d['training'][0]['image_id']
    elif bad=='joint_reuse':r['joint_sample_id']=d['training'][0]['joint_sample_id']
    elif bad=='mount':r['attachment_version']='changed'
    elif bad=='orientation':r['target_orientation_observed']=False
    elif bad=='slip':r['target_rigidly_fixed']=False
    elif bad=='clock':r['epoch']='other'
    elif bad=='vision':r['vision_validation']='UNKNOWN'
    elif bad=='alignment':r['time_alignment_evidence']=''
    elif bad=='matrix':r['T_camera_target']=None
    with pytest.raises(ValueError):m.solve(d)


def test_upstream_rigid_link_is_not_relabelled_as_a_flange():
    d=dataset();d['reference_frame']='L5_Link';d['attachment_reference_frame']='L5_Link'
    for r in d['training']+d['validation']:
        r['T_base_reference']=r.pop('T_base_flange');r['reference_stamp_s']=r.pop('flange_stamp_s')
    result=m.solve(d)
    assert result['reference_frame']=='L5_Link' and 'T_flange_target' not in result
    assert result['report']['consistency']=='PASS'
    d['attachment_reference_frame']='palm'
    with pytest.raises(ValueError):m.solve(d)


def test_unmarked_point_mode_has_no_fabricated_orientation():
    d=dataset();d['observation_kind']='point_center';d['reference_frame']='L5_Link';d['attachment_reference_frame']='L5_Link'
    x=np.eye(4);x[:3,3]=[.4,-.2,.9];p=np.array([.02,.03,.1,1.])
    for r in d['training']+d['validation']:
        a=np.array(r.pop('T_base_flange'));a[2,3]+=1.5
        r['T_base_reference']=a.tolist();r['reference_stamp_s']=r.pop('flange_stamp_s')
        r['center_camera_m']=(np.linalg.inv(x)@a@p)[:3].tolist()
        r['center_stamp_s']=r.pop('target_stamp_s');r['center_quality']='PASS'
        r.pop('target_orientation_observed');r.pop('T_camera_target')
    result=m.solve(d)
    np.testing.assert_allclose(result['T_base_camera'],x,atol=1e-9)
    assert result['point_orientation_xyzw'] is None and 'T_reference_target' not in result
    d['validation'][0]['center_quality']='REJECTED'
    with pytest.raises(ValueError):m.solve(d)
