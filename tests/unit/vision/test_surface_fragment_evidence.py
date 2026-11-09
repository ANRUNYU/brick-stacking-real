"""Repeat surface evidence must not erase an adjacent partial/raised object."""
from copy import deepcopy
import numpy as np
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.vision.adaptive_table_surface import consolidate_color_proposals


def inputs():
    shape=(64,64)
    frame=CameraFrame(np.full((*shape,3),100,np.uint8),np.ones(shape),
        np.array([[200,0,32],[0,200,32],[0,0,1.]]),
        'fixture','fixture_optical',1.,'epoch','synthetic',True,True)
    mask=np.zeros(shape,bool);mask[28:37,28:37]=True
    candidate={'candidate_id':'cube','status':'SINGLE_CUBE_CANDIDATE',
        'center_camera_m':[0.,0.,1.],'geometry_axes_camera':np.eye(3).tolist(),
        'geometry_extent_m':[.05]*3,'geometry_model_uncertainty_m':[0.]*3,
        'area_px':int(mask.sum())}
    return frame,mask,candidate


def fragment(shape,ys,xs):
    mask=np.zeros(shape,bool);mask[ys,xs]=True
    return mask,{'candidate_id':'fragment','status':'AMBIGUOUS','area_px':int(mask.sum()),
                 'bbox_xywh':[xs.start,ys.start,xs.stop-xs.start,ys.stop-ys.start]}


def test_inside_cube_volume_recorded_as_explained_not_new_object():
    frame,mask,candidate=inputs();part=fragment(mask.shape,slice(30,35),slice(33,37));audit={}
    result=consolidate_color_proposals([(mask,candidate),part],.05,frame=frame,noise_m=.001,diagnostics=audit)
    assert len(result)==1
    assert audit['explained_surface_fragments'][0]['explained_fraction']==1.
    assert audit['explained_surface_fragments'][0]['proposal']['candidate_id']=='fragment'


def test_pixel_adjacent_but_outside_cube_stays_ambiguous():
    frame,mask,candidate=inputs();part=fragment(mask.shape,slice(30,35),slice(38,39));audit={}
    result=consolidate_color_proposals([(mask,candidate),part],.05,frame=frame,noise_m=.001,diagnostics=audit)
    assert len(result)==2 and result[1][1]['status']=='AMBIGUOUS'
    assert not audit.get('explained_surface_fragments')


def test_same_pixel_location_different_depth_not_deleted():
    frame,mask,candidate=inputs();part=fragment(mask.shape,slice(30,35),slice(33,37))
    depth=frame.depth_m.copy();depth[part[0]]=.90
    frame=CameraFrame(frame.rgb,depth,frame.k,frame.camera_id,frame.frame_id,frame.stamp_s,
        frame.clock_domain,frame.source,True,True)
    result=consolidate_color_proposals([(mask,candidate),part],.05,frame=frame,noise_m=.001)
    assert len(result)==2


def test_uncertainty_growth_bounded_and_cannot_hide_far_object():
    frame,mask,candidate=inputs();candidate=deepcopy(candidate)
    candidate['geometry_model_uncertainty_m']=[100.]*3
    part=fragment(mask.shape,slice(30,35),slice(40,42))
    result=consolidate_color_proposals([(mask,candidate),part],.05,frame=frame,noise_m=.001)
    assert len(result)==2


def test_residual_below_existing_instance_support_gate_keeps_diagnostic_evidence():
    frame,mask,candidate=inputs();part=fragment(mask.shape,slice(30,35),slice(38,39));audit={}
    result=consolidate_color_proposals([(mask,candidate),part],.05,frame=frame,noise_m=.001,
        diagnostics=audit,residual_support_gate=True)
    assert len(result)==1
    warning=audit['low_support_unassigned_surfaces'][0]
    assert warning['unassigned_points']==5 and warning['not_object_absence_evidence']
    assert warning['proposal']['status']=='AMBIGUOUS'


def test_connected_partial_object_above_support_gate_remains_unresolved():
    frame,mask,candidate=inputs();part=fragment(mask.shape,slice(28,37),slice(38,42));audit={}
    result=consolidate_color_proposals([(mask,candidate),part],.05,frame=frame,noise_m=.001,
        diagnostics=audit,residual_support_gate=True)
    assert len(result)==2 and result[1][1]['status']=='AMBIGUOUS'
    assert not audit.get('low_support_unassigned_surfaces')
