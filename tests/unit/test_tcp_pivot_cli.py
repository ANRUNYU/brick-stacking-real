import importlib.util
from pathlib import Path
import numpy as np
import pytest
s=importlib.util.spec_from_file_location('tcp_pivot',Path(__file__).parents[2]/'tools/solve_tcp_pivot.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def dataset():
    r=dict(dataset_id='synthetic',arm_role='left',model_version='synthetic',joint_mapping_version='synthetic',device_id='synthetic',clock_domain='mock',epoch='1',operator='test',source='synthetic',units='m',base_frame='base',flange_frame='flange')
    matrices=[np.eye(3),np.array([[1,0,0],[0,0,-1],[0,1,0]]),np.array([[0,0,1],[0,1,0],[-1,0,0]]),np.diag([-1,-1,1])]
    tcp=np.array([.01,.02,.1]);pivot=np.array([.3,.2,.4])
    for group in ('training','validation'):
        rows=[]
        for i,rot in enumerate(matrices):
            a=np.eye(4);a[:3,:3]=rot;a[:3,3]=pivot-rot@tcp
            rows.append(dict(sample_id=f'{group}-{i}',clock_domain='mock',epoch='1',host_stamp_s=float(i),T_base_flange=a.tolist()))
        r[group]=rows
    return r


def test_independent_pivot_validation_and_corruption():
    d=dataset();r=m.solve(d)
    np.testing.assert_allclose(r['tcp_translation_flange_m'],[.01,.02,.1],atol=1e-12)
    assert r['validation']['max_m']<1e-12 and r['tcp_orientation_xyzw'] is None and not r['approved']
    d['validation'][0]['T_base_flange'][0][3]+=.01
    assert m.solve(d)['validation']['max_m']==pytest.approx(.01)


def test_session_epoch_and_sample_leakage_refused():
    d=dataset();d['validation'][0]['epoch']='2'
    with pytest.raises(ValueError):m.solve(d)
    d=dataset();d['validation'][0]['sample_id']='training-0'
    with pytest.raises(ValueError):m.solve(d)
