import numpy as np
import pytest
from brick_stacking.planning.surface_clearance import surface_speed_bounds,certify_surface_intervals


def test_known_rotating_point_rate_bound(tmp_path):
    p=tmp_path/'chain.urdf';p.write_text('<robot><joint name="J1" type="revolute"><parent link="base"/><child link="link"/><axis xyz="0 0 1"/></joint></robot>')
    t=dict(interpolation='quintic_stop_at_each_waypoint',joint_names=['J1'],segments=[dict(start_rad=[0],end_rad=[1],duration_s=2)])
    b=surface_speed_bounds(p,{'link':np.array([[2,0,0],[0,2,0]])},t)
    assert b['surface_speed_m_s']['link']==pytest.approx(1.875)


def test_gap_certificate_pass_and_insufficient_clearance():
    sampled=dict(model_version='model',coverage_names=['a','b'],checks=[dict(segment=0,time_from_segment_start_s=0),dict(segment=0,time_from_segment_start_s=.1)],min_sampled_distance_m=.02,sampled_status='PASS')
    bounds=dict(urdf_sha256='model',surface_speed_m_s={'a':.1,'b':.1})
    r=certify_surface_intervals(sampled,bounds,clearance_margin_m=0)
    assert r['continuous_surface_status']=='PASS' and r['conservative_surface_distance_lower_bound_m']==pytest.approx(.01)
    assert r['full_collision']=='UNKNOWN' and not r['motion_enabled']
    assert certify_surface_intervals(sampled,bounds,clearance_margin_m=.015)['continuous_surface_status']=='UNKNOWN'
    with pytest.raises(ValueError): certify_surface_intervals(sampled,dict(urdf_sha256='model',surface_speed_m_s={'a':.1}),clearance_margin_m=0)
