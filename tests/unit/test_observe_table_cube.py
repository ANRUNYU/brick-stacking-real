import importlib.util
import json
from pathlib import Path
import numpy as np


s=importlib.util.spec_from_file_location('observe_table',Path(__file__).parents[2]/'tools/observe_table_cube.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def test_recorded_geometry_reuses_existing_block_pose_and_keeps_source(tmp_path):
    depth=np.ones((128,128),np.float32);depth[44:68,44:68]=.95
    k=np.array([[400.,0,64.],[0,400.,64.],[0,0,1.]])
    meta=dict(camera_id='synthetic-camera',frame_id='synthetic-optical',stamp_s=1.,clock_domain='synthetic-device',source='synthetic',registered=True,rectified=True)
    path=tmp_path/'frame.npz'
    np.savez(path,rgb=np.zeros((128,128,3),np.uint8),depth_m=depth,k=k,metadata=json.dumps(meta))
    config=dict(camera_serial='synthetic-camera',edge_m=.05,edge_source='synthetic ground truth',roi_source='synthetic polygons',rests_on_table=True,
                table_polygon_xy=[[80,80],[120,80],[120,120],[80,120]],top_corners_xy=[[45,45],[66.05263158,45],[66.05263158,66.05263158],[45,66.05263158]],
                table_origin_xy=[100,100],top_erosion_px=3,plane_threshold_m=.002,max_holdout_m=.003,max_edge_error_m=.004,max_adjacent_edge_abs_cos=.1,
                table_frame='synthetic-table',candidate_id='synthetic-cube',version='synthetic',color='red')
    r=m.observe(path,config)
    assert r['source']=='synthetic' and r['checks']['consistency']=='PASS'
    assert r['block_pose']['frame_id']=='synthetic-table' and r['block_pose']['orientation_xyzw'] is None
    np.testing.assert_allclose(r['block_pose']['center_m'][2],.025)
    assert not r['block_pose']['control_ready'] and r['T_base_camera'] is None and not r['motion_enabled']
