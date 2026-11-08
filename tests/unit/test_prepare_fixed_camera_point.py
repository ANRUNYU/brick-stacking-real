import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
from brick_stacking.localization.rigid_transforms import RigidTransform

s=importlib.util.spec_from_file_location('prepare_point',Path(__file__).parents[2]/'tools/prepare_fixed_camera_point_sample.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


@pytest.fixture
def inputs(tmp_path,monkeypatch):
    (tmp_path/'camera').mkdir();urdf=tmp_path/'model.urdf';urdf.write_text('synthetic stub')
    monkeypatch.setattr(m,'MODEL_SHA256',m.digest(urdf))
    monkeypatch.setattr(m,'urdf_forward_kinematics',lambda *a,**k:(RigidTransform('L_arm_root','L5_Link',np.eye(4),'synthetic'),{}))
    manifest=dict(attachment_id='synthetic-confirmed-mount',reference_frame='L5_Link',target_writes=0,enable_rest_zero_flash_commands=0,camera_serial='synthetic',pose_id='pose01',quality=dict(clock_epoch='linux_boot:synthetic'))
    (tmp_path/'record_manifest.json').write_text(json.dumps(manifest));(tmp_path/'joint_cycles.json').write_text('synthetic raw placeholder')
    (tmp_path/'camera/camera_report.json').write_text(json.dumps(dict(profiles={},aligned_geometry={})))
    centers=[];rows=[]
    for i in range(2):
        meta=dict(camera_id='synthetic',frame_id='synthetic-optical',stamp_s=10.+i,clock_domain='synthetic-device')
        path=tmp_path/f'camera/frame_{i:03d}.npz';np.savez(path,metadata=json.dumps(meta))
        centers.append(dict(frame_sha256=m.digest(path),quality=dict(consistency='FAIL' if i==0 else 'PASS'),camera_serial='synthetic',camera_stamp_s=meta['stamp_s'],camera_clock_domain=meta['clock_domain'],center_camera_m=[0,0,1],config=dict(edge_m=.05,edge_source='synthetic')))
        rows.append(dict(image_file=path.name,joint_positions_sdk_rad={},association_host_monotonic_s=20.+i,clock_observation={},joint_brackets={}))
    association=dict(schema_version='c-camera-upstream-association-1',clock_domain='host_monotonic',epoch='linux_boot:synthetic',timing_acceptance='NOT_VALIDATED',approved=False,source='synthetic',samples=rows)
    return tmp_path,centers,association,urdf


def prepare(inputs):return m.prepare(*inputs,group='training',operator_evidence='synthetic rigid mounting truth')


def test_first_vision_qualified_image_selected_with_failures_retained(inputs):
    r=prepare(inputs)
    assert r['sample']['image_id']==inputs[1][1]['frame_sha256']
    assert [v['vision_quality'] for v in r['frame_decisions']]==['FAIL','PASS']
    assert r['sample']['center_stamp_s']==21 and r['sample']['time_alignment_evidence']['original_camera_stamp_s']==11
    assert r['context']['source']=='synthetic' and not r['calibration_sample_valid'] and not r['motion_enabled']


@pytest.mark.parametrize('bad',['all_failed','duplicate','model','clock','promoted_timing','mount'])
def test_unqualified_point_candidate_rejected(inputs,bad):
    root,centers,a,urdf=inputs
    if bad=='all_failed':centers[1]['quality']['consistency']='FAIL'
    elif bad=='duplicate':centers.append(centers[0])
    elif bad=='model':urdf.write_text('changed')
    elif bad=='clock':centers[1]['camera_clock_domain']='different'
    elif bad=='promoted_timing':a['approved']=True
    elif bad=='mount':
        p=root/'record_manifest.json';v=json.loads(p.read_text());v['attachment_id']='unconfirmed';p.write_text(json.dumps(v))
    with pytest.raises(ValueError):prepare(inputs)
