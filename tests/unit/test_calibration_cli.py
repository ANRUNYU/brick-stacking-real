import importlib.util
from pathlib import Path
import copy
import pytest

spec=importlib.util.spec_from_file_location('solve_calibration',Path(__file__).parents[2]/'tools/solve_calibration.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def dataset():
    d=dict(dataset_id='synthetic-1',source_frame='camera',target_frame='world', device_serial='SYNTHETIC', profile=dict(width=640,height=480),clock_domain='host_monotonic',epoch='mock-1',source='synthetic',units='m')
    points=[[0,0,0],[.1,0,0],[0,.1,0],[0,0,.1]]
    for group,offset in [('train',0),('validation',.02)]:
        d[group]=[dict(sample_id=f'{group}-{i}',source_m=[v+offset for v in p],target_m=[v+offset+.1 for v in p],profile=d['profile'],clock_domain=d['clock_domain'],epoch=d['epoch'],host_stamp_s=float(i)) for i,p in enumerate(points)]
    return d


def test_valid_and_rejections():
    d=dataset()
    assert module.solve(d)['validation']['max_m']<1e-10
    for key,value in [('units','mm'),('device_serial',None),('profile',{'width':0,'height':480})]:
        bad=copy.deepcopy(d); bad[key]=value
        with pytest.raises(ValueError): module.solve(bad)
    for key,value in [('profile',{}),('epoch','other'),('clock_domain','device'),('host_stamp_s',float('nan')),('sample_id','train-0')]:
        bad=copy.deepcopy(d); bad['validation'][0][key]=value
        with pytest.raises(ValueError): module.solve(bad)
