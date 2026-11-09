import copy
import hashlib
import importlib.util
import struct
from pathlib import Path

import numpy as np
import pytest


spec = importlib.util.spec_from_file_location('prepare_pivot', Path(__file__).parents[2]/'tools/prepare_tcp_pivot_sample.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    # Synthetic seven-axis URDF and raw bytes; never persisted as real evidence.
    links = ['L_arm_root']+[f'L{i}_Link' for i in range(1, 9)]
    xml = '<robot name="test">'+''.join(f'<link name="{n}"/>' for n in links)
    for i in range(1, 9):
        kind = 'revolute' if i < 8 else 'fixed'
        xml += f'<joint name="L{i}_Joint" type="{kind}"><parent link="{links[i-1]}"/><child link="{links[i]}"/><origin xyz="0.1 0 0"/><axis xyz="0 0 1"/>'
        if i < 8: xml += '<limit lower="-3" upper="3" effort="1" velocity="1"/>'
        xml += '</joint>'
    xml += '</robot>'
    p = tmp_path/'model.urdf';p.write_text(xml)
    monkeypatch.setattr(m, 'SDK_URDF_SHA256', hashlib.sha256(p.read_bytes()).hexdigest())
    raw = dict(schema_version='c-left-supported-rest-1', source='real', arm_role='left', interface='can2', status='RAW_SEVEN_AXIS_CAPTURED', clock_domain='host_monotonic', epoch='unit-test-synthetic', received=[])
    for mid in range(61, 68):
        payload = (b'\x06'+struct.pack('<f',0.)).hex() if mid <= 65 else '0000007ff0000019'
        raw['received'].append(dict(motor_id=mid, host_receive_monotonic_s=mid*.001, position_sdk_rad=0., raw_hex=payload))
    profile = {str(mid): dict(verified=True, evidence='synthetic-test-only', units='rad', theta_min_rad=0., theta_max_rad=1.) for mid in (66, 67)}
    return raw, profile, p


def run(inputs, **kwargs):
    return m.prepare(*inputs, sample_id='test', contact_confirmed=True, contact_evidence='unit-test', max_receive_span_s=.01, **kwargs)


def test_explicit_verified_ranges_generate_existing_row_schema(inputs):
    row = run(inputs)
    np.testing.assert_allclose(np.array(row['T_base_flange'])[:3,3], [.8,0,0])
    assert row['approved'] is False and row['epoch'] == 'unit-test-synthetic'


def test_unknown_range_never_generates_default_fk(inputs):
    raw, profile, model = inputs
    profile['66']['verified'] = False
    with pytest.raises(ValueError, match='verified'): run(inputs)
    profile['66']['verified'] = True;profile['66']['theta_min_rad'] = None
    with pytest.raises(ValueError): run(inputs)


@pytest.mark.parametrize('failure', ['missing','duplicate','fault','clock','skew','hash','raw_mismatch'])
def test_bad_capture_or_wrong_model_rejected(inputs, failure):
    raw, profile, model = inputs
    if failure == 'missing':raw['received'].pop()
    elif failure == 'duplicate':raw['received'].append(copy.deepcopy(raw['received'][0]))
    elif failure == 'fault':raw['received'][-1]['raw_hex']='0000007ff0000319'
    elif failure == 'clock':raw['clock_domain']='device'
    elif failure == 'skew':raw['received'][0]['host_receive_monotonic_s']=0
    elif failure == 'hash':model.write_text(model.read_text()+' ')
    elif failure == 'raw_mismatch':raw['received'][0]['position_sdk_rad']=.1
    with pytest.raises(ValueError):run(inputs)
