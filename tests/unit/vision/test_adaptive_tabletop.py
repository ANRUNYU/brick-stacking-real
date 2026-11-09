"""Moved scene geometry, observable seams and unobservable same-color regions."""
from dataclasses import replace
from pathlib import Path
import cv2
import numpy as np
import pytest
import yaml
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.vision.tabletop_segmentation import TabletopDetector


def profile():
    p=yaml.safe_load((Path(__file__).resolve().parents[3]/
        'config/vision_profiles/head_adaptive_candidate.yaml').read_text())['tabletop']
    p.update(camera_id='fixture',image_size_wh=[160,120],top_min_points=8,
             plane_sample_limit=4000,auto_plane_iterations=400)
    return p


def scene(distance=1.,uv=(80,60),angle=0.,count=1,seam=True,tilt=0.,positions=None,joint_drop=110):
    h,w=120,160;k=np.array([[240.,0,80],[0,240.,60],[0,0,1.]])
    yy,xx=np.indices((h,w));rays=np.stack(((xx-80)/240,(yy-60)/240,np.ones((h,w))),axis=-1)
    n=np.array([0.,np.sin(tilt),-np.cos(tilt)])
    denom=rays@n;depth=-distance/denom
    rgb=np.full((h,w,3),140,np.uint8)
    # A metric rectangle, translated and rotated in a visible support plane.
    tx=np.array([1.,0,0]);ty=np.cross(n,tx)
    center=rays[uv[1],uv[0]]*(-(distance-.05)/denom[uv[1],uv[0]])
    ca,sa=np.cos(angle),np.sin(angle);axis=ca*tx+sa*ty;cross=-sa*tx+ca*ty
    offsets=positions if positions is not None else [(index-(count-1)/2,0.) for index in range(count)]
    for ax,ay in offsets:
        c=center+axis*.05*ax+cross*.05*ay
        corners=np.array([c+axis*a*.025+cross*b*.025 for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]])
        uv_c=(corners@k.T);uv_c=np.rint(uv_c[:,:2]/uv_c[:,2:]).astype('int32')
        mask=np.zeros((h,w),np.uint8);cv2.fillConvexPoly(mask,uv_c,1)
        rgb[mask>0]=(220,15,15)
        depth[mask>0]=(-(distance-.05)/denom)[mask>0]
        if seam and len(offsets)>1:
            cv2.polylines(rgb,[uv_c],True,(220-joint_drop,max(0,15-joint_drop),max(0,15-joint_drop)),1)
    return CameraFrame(rgb,depth,k,'fixture','fixture_optical',1.,'fixture','synthetic',True,True)


@pytest.mark.parametrize('distance,uv,angle,tilt',[
    (.85,(42,35),0.,0.),(1.2,(110,83),.6,.15),(1.5,(90,45),1.1,-.12)])
def test_surface_and_cube_follow_translation_height_and_rotation(distance,uv,angle,tilt):
    result=TabletopDetector(profile()).detect(scene(distance,uv,angle,tilt=tilt))
    accepted=[c for c in result.candidates if c['status']=='SINGLE_CUBE_CANDIDATE']
    assert len(accepted)==1
    assert accepted[0]['top_height_m']==pytest.approx(.05,abs=.004)
    assert result.diagnostics['mode']=='automatic_per_frame'
    assert not accepted[0]['control_ready']


@pytest.mark.parametrize('count,angle',[(2,0.),(2,np.pi/2),(3,0.)])
def test_visible_seams_support_multiple_instances(count,angle):
    result=TabletopDetector(profile()).detect(scene(count=count,seam=True,angle=angle))
    assert len([c for c in result.candidates if c['status']=='SINGLE_CUBE_CANDIDATE'])==count


def test_uniform_touching_rectangle_cannot_be_split_by_known_size_alone():
    result=TabletopDetector(profile()).detect(scene(count=2,seam=False))
    assert len(result.candidates)==1
    assert result.candidates[0]['status']=='AMBIGUOUS'


def test_table_without_object_evidence_rejected():
    f=scene();f=replace(f,rgb=np.full(f.rgb.shape,140,np.uint8))
    with pytest.raises(ValueError,match='no elevated'):
        TabletopDetector(profile()).detect(f)


def test_bad_surface_mode_rejected():
    p=profile();p['surface_mode']='guess'
    with pytest.raises(ValueError,match='surface mode'):TabletopDetector(p)


def test_automatic_mode_uses_actual_image_and_intrinsics_without_pixel_roi():
    p=profile();p['image_size_wh']=[640,480]
    result=TabletopDetector(p).detect(scene())
    assert result.roi_mask.shape==(120,160)
    assert result.candidates[0]['status']=='SINGLE_CUBE_CANDIDATE'


@pytest.mark.parametrize('positions',[
    [(-.5,-.5),(.5,-.5),(-.5,.5),(.5,.5)],
    [(-.5,-.5),(.5,-.5),(-.5,.5)]])
def test_observable_grid_and_l_shape_not_limited_to_one_dimensional_rows(positions):
    result=TabletopDetector(profile()).detect(scene(positions=positions,joint_drop=8))
    assert len(result.candidates)==len(positions)
    assert all(c['status']=='SINGLE_CUBE_CANDIDATE' for c in result.candidates)


def test_no_seam_square_is_not_fabricated_into_four_cubes():
    result=TabletopDetector(profile()).detect(scene(
        positions=[(-.5,-.5),(.5,-.5),(-.5,.5),(.5,.5)],seam=False))
    assert len(result.candidates)==1 and result.candidates[0]['status']=='AMBIGUOUS'


def test_sampling_bound_is_not_an_unlimited_size_relaxation():
    from brick_stacking.vision.seam_segmentation import plausible_footprint
    c={'footprint_size_m':[.036,.046],'footprint_raw_size_m':[.036,.046],
       'footprint_sampling_half_extent_m':[.001,.001]}
    assert plausible_footprint(c,.05)
    c['footprint_raw_size_m']=[.03,.046]
    assert not plausible_footprint(c,.05)
