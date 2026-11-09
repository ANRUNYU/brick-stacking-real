from copy import deepcopy
from pathlib import Path
from dataclasses import replace
import numpy as np
import pytest
import yaml
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.vision.tabletop_segmentation import TabletopDetector, make_roi
from brick_stacking.vision.evaluation import evaluate_candidates


def fixture_profile():
    root=Path(__file__).resolve().parents[3]
    p=yaml.safe_load((root/'config/vision_profiles/head_sunlight_candidate.yaml').read_text())["tabletop"]
    p.update(camera_id="fixture",image_size_wh=[128,96],roi_polygon_uv=[[20,20],[120,20],[120,90],[20,90]],
             min_area_px=20,opening_kernel_px=1,top_min_points=12,plane_iterations=70)
    return p


def frame(*, touching=False, table_red=False, outside=False):
    rgb=np.full((96,128,3),100,np.uint8)
    if table_red: rgb[:]=(255,0,0)
    depth=np.ones((96,128),float)
    if outside:
        rgb[30:42,1:13]=(255,0,0);depth[30:42,1:13]=.95
    else:
        rgb[40:52,45:(69 if touching else 57)]=(255,0,0)
        depth[40:52,45:(69 if touching else 57)]=.95
    return CameraFrame(rgb,depth,np.array([[200,0,64],[0,200,48],[0,0,1.]]),
                       "fixture","fixture_optical",1.,"fixture_epoch","synthetic",True,True)


def test_single_cube_height_and_camera_center():
    result=TabletopDetector(fixture_profile()).detect(frame())
    assert len(result.candidates)==1
    c=result.candidates[0]
    assert c['status']=='SINGLE_CUBE_CANDIDATE'
    assert c['top_height_m']==pytest.approx(.05,abs=1e-5)
    assert c['center_camera_m'][2]==pytest.approx(.975,abs=1e-5)
    assert c['control_ready'] is False


def test_same_color_table_not_a_block():
    result=TabletopDetector(fixture_profile()).detect(frame(table_red=True))
    assert len(result.candidates)==1
    assert result.candidates[0]['bbox_xywh']==[45,40,12,12]


def test_unobservable_touching_rectangle_not_split_by_length():
    result=TabletopDetector(fixture_profile()).detect(frame(touching=True))
    assert len(result.candidates)==1
    assert result.candidates[0]['status']=='AMBIGUOUS'
    assert result.candidates[0]['center_camera_m'] is None


def test_outside_roi_excluded():
    assert TabletopDetector(fixture_profile()).detect(frame(outside=True)).candidates==[]


def test_missing_depth_not_replaced_with_invented_plane():
    f=frame(); bad=replace(f,depth_m=np.full(f.depth_m.shape,np.nan))
    with pytest.raises(ValueError,match="insufficient"):
        TabletopDetector(fixture_profile()).detect(bad)


@pytest.mark.parametrize('change',['camera','size'])
def test_profile_camera_and_resolution_must_match(change):
    p=fixture_profile()
    if change=='camera': p['camera_id']='other'
    else:p['image_size_wh']=[640,480]
    with pytest.raises(ValueError): TabletopDetector(p).detect(frame())


def test_roi_out_of_bounds_rejected():
    with pytest.raises(ValueError): make_roi((96,128),[[0,0],[128,0],[10,10]])


def test_annotation_counts_require_distinct_color_and_location():
    c={"candidate_id":"one","color":"red","bbox_xywh":[0,0,10,10],"status":"SINGLE_CUBE_CANDIDATE"}
    labels=[{"id":"a","color":"red","bbox_xywh":[0,0,10,10]},
            {"id":"b","color":"red","bbox_xywh":[0,0,10,10]}]
    e=evaluate_candidates([c],labels,min_iou=.25)
    assert e['true_positives']==1 and e['false_negatives']==1
    wrong=deepcopy(c);wrong['color']='blue'
    assert evaluate_candidates([wrong],labels,min_iou=.25)['true_positives']==0
    moved=deepcopy(c);moved['bbox_xywh']=[50,50,10,10]
    assert evaluate_candidates([moved],labels,min_iou=.25)['false_positives']==1
