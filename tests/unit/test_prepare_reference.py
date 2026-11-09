import hashlib
import importlib.util
from pathlib import Path
import struct
import pytest

s=importlib.util.spec_from_file_location('reference_prepare',Path(__file__).parents[2]/'tools/prepare_calibration_reference.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


@pytest.fixture
def inputs(tmp_path,monkeypatch):
    p=tmp_path/'synthetic.urdf';xml='<robot name="test"><link name="L_arm_root"/>'
    for i in range(1,6):
        parent='L_arm_root' if i==1 else f'L{i-1}_Link'
        xml+=f'<link name="L{i}_Link"/><joint name="L{i}_Joint" type="revolute"><parent link="{parent}"/><child link="L{i}_Link"/><origin xyz="0.1 0 0"/><axis xyz="0 0 1"/><limit lower="-3" upper="3" effort="1" velocity="1"/></joint>'
    p.write_text(xml+'</robot>');monkeypatch.setattr(m,'MODEL_SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
    r=dict(schema_version='c-left-readonly-probe-1',source='synthetic',arm_role='left',interface='can2',clock_domain='host_monotonic',epoch='linux_boot:00000000-0000-4000-8000-000000000001',received=[])
    for mid in range(61,66):r['received'].append(dict(motor_id=mid,raw_hex=(b'\x06'+struct.pack('<f',0.)).hex(),position_sdk_rad=0.,host_receive_monotonic_s=mid*.001))
    return r,p


def prepare(inputs):return m.prepare(*inputs,sample_id='synthetic',max_receive_span_s=.01)


def test_wrist_angles_not_required_or_filled(inputs):
    r=prepare(inputs)
    assert r['reference_frame']=='L5_Link' and 'T_base_flange' not in r
    assert len(r['joint_positions_sdk_rad'])==5 and r['T_base_reference'][0][3]==pytest.approx(.5)
    assert r['camera_time_alignment']=='NOT_ESTABLISHED' and not r['approved']


@pytest.mark.parametrize('bad',['missing','duplicate','old_epoch','span','hash','raw_mismatch'])
def test_unusable_reference_input_rejected(inputs,bad):
    r,p=inputs
    if bad=='missing':r['received'].pop()
    elif bad=='duplicate':r['received'].append(r['received'][0])
    elif bad=='old_epoch':r['epoch']='old-capture-uuid'
    elif bad=='span':r['received'][0]['host_receive_monotonic_s']=0
    elif bad=='hash':p.write_text(p.read_text()+' ')
    elif bad=='raw_mismatch':r['received'][0]['position_sdk_rad']=.2
    with pytest.raises(ValueError):prepare(inputs)
