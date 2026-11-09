"""Larger color masks must not win when they include a neighbour's surface."""
from copy import deepcopy
import numpy as np
from brick_stacking.vision.adaptive_table_surface import consolidate_color_proposals


def test_geometry_ranking_beats_maximum_color_area():
    mask=np.ones((30,30),bool)
    correct={'candidate_id':'square','status':'SINGLE_CUBE_CANDIDATE','area_px':500,
        'center_camera_m':[0,0,1],'footprint_size_m':[.046,.049],'footprint_fill_ratio':.95}
    leaking=deepcopy(correct)
    leaking.update(candidate_id='leaks_into_neighbour',area_px=800,
        center_camera_m=[.01,0,1],footprint_size_m=[.044,.064])
    result=consolidate_color_proposals([(mask,leaking),(mask,correct)],.05)
    assert len(result)==1 and result[0][1]['candidate_id']=='square'
