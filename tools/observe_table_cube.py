"""Recorded RGB-D + explicit table/top ROIs -> observed table frame / cube pose.

Reuses CameraFrame, BlockDetection, localize_top_face, RigidTransform and plane
fitting. No robot-base calibration, persistent object identity or motion permit.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.models.block_detection import BlockDetection,SegmentationStatus
from brick_stacking.localization.block_localization import localize_top_face
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.table_plane import fit_table_plane
from brick_stacking.localization.table_coordinates import table_coordinates,resting_cube_geometry


def observe(path,config):
    with np.load(path,allow_pickle=False) as data:
        meta=json.loads(str(data['metadata'].item()))
        frame=CameraFrame(data['rgb'],data['depth_m'],data['k'],meta['camera_id'],meta['frame_id'],meta['stamp_s'],meta['clock_domain'],meta['source'],meta['registered'],meta['rectified'])
    if frame.camera_id!=config['camera_serial'] or not config.get('edge_source') or not config.get('roi_source') or config.get('rests_on_table') is not True:
        raise ValueError('camera binding, measured dimension/ROI provenance and resting-table hypothesis required')
    for name in ('plane_threshold_m','max_holdout_m','max_edge_error_m','max_adjacent_edge_abs_cos'):
        if not np.isfinite(config[name]) or config[name]<=0:raise ValueError('explicit positive geometric quality thresholds required')
    h,w=frame.depth_m.shape;yy,xx=np.indices((h,w))
    def mask(polygon):
        p=np.asarray(polygon,float)
        if p.shape!=(4,2) or not np.isfinite(p).all() or np.any(p<0) or np.any(p[:,0]>=w) or np.any(p[:,1]>=h):raise ValueError('four in-image ordered corners required')
        p=np.rint(p).astype(np.int32)
        if not cv2.isContourConvex(p):raise ValueError('convex ROI required')
        a=np.zeros((h,w),np.uint8);cv2.fillConvexPoly(a,p,1);return a
    table=mask(config['table_polygon_xy']).astype(bool)
    top=mask(config['top_corners_xy'])
    if np.any(table&top.astype(bool)):raise ValueError('table/top ROIs overlap')
    radius=config['top_erosion_px']
    if type(radius) is not int or not 0<=radius<=10:raise ValueError('explicit erosion 0..10 required')
    if radius:top=cv2.erode(top,np.ones((2*radius+1,2*radius+1),np.uint8))
    valid=np.isfinite(frame.depth_m)&(frame.depth_m>0)
    def xyz(m):return backproject(np.c_[xx[m],yy[m]],frame.depth_m[m],frame.k)
    offset=config.get('pixel_partition_offset_xy',[0,0])
    if len(offset)!=2 or any(type(v) is not int or v<0 for v in offset):raise ValueError('nonnegative integer source-pixel partition offset required')
    train=table&valid&((xx+offset[0])%4==0)&((yy+offset[1])%4==0);check=table&valid&((xx+offset[0])%4==2)&((yy+offset[1])%4==2)
    top_check=top.astype(bool)&valid
    if min(train.sum(),check.sum(),top_check.sum())<20:raise ValueError('insufficient independent table and valid top points')
    points=xyz(train)
    plane=fit_table_plane(points,normal_hint=-points.mean(0),distance_threshold_m=config['plane_threshold_m'],iterations=100,min_inlier_ratio=.9)
    table_errors=np.abs(plane.heights(xyz(check)));top_errors=np.abs(plane.heights(xyz(top_check))-config['edge_m'])
    ray=backproject(np.asarray(config['table_origin_xy']),1.,frame.k)
    world=table_coordinates(plane,ray,camera_frame=frame.frame_id,table_frame=config['table_frame'],version=config['version'])
    cube,geometry=resting_cube_geometry(plane,config['top_corners_xy'],frame.k,edge_m=config['edge_m'],camera_frame=frame.frame_id,block_frame=config['candidate_id'],version=config['version'],rests_on_table=True)
    corners=np.asarray(config['top_corners_xy']);uv=corners.mean(0);lo=np.floor(corners.min(0)).astype(int);hi=np.ceil(corners.max(0)).astype(int)
    detection=BlockDetection(config['candidate_id'],config['color'],frame.camera_id,frame.frame_id,frame.stamp_s,frame.clock_domain,tuple(uv),tuple(np.r_[lo,hi-lo]),int(top.sum()),float(valid[top.astype(bool)].mean()),SegmentationStatus.UNAMBIGUOUS,'manually reviewed single top-face ROI',tuple(geometry['top_center_camera_m']),None)
    block=localize_top_face(detection,world.inverse(),outward_normal_target=[0.,0.,1.],edge_m=config['edge_m'],top_face_confirmed=True,max_tf_delta_s=0.)
    good=max(table_errors.max(),top_errors.max())<=config['max_holdout_m'] and max(abs(v) for v in geometry['edge_errors_m'])<=config['max_edge_error_m'] and geometry['adjacent_edge_abs_cos']<=config['max_adjacent_edge_abs_cos']
    return dict(schema_version='c-observed-table-cube-1',source=frame.source,frame_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                camera_serial=frame.camera_id,stamp_s=frame.stamp_s,clock_domain=frame.clock_domain,config=config,
                table_plane=asdict(plane),T_camera_table=world.matrix.tolist(),T_table_camera=world.inverse().matrix.tolist(),
                table_frame_convention='origin: selected ray on table; +Z: outward normal; +X: projected camera optical X; +Y: Z cross X',
                T_camera_cube_representative=cube.matrix.tolist(),T_table_cube_representative=world.inverse().compose(cube).matrix.tolist(),
                block_pose=asdict(block),geometry=geometry,
                checks=dict(consistency='PASS' if good else 'FAIL',table_validation_n=len(table_errors),table_max_abs_m=float(table_errors.max()),table_p95_abs_m=float(np.percentile(table_errors,95)),
                            top_depth_n=len(top_errors),top_height_median_m=float(np.median(plane.heights(xyz(top_check)))),top_max_height_error_m=float(top_errors.max()),top_p95_height_error_m=float(np.percentile(top_errors,95))),
                T_base_camera=None,T_base_table=None,approved=False,motion_enabled=False,
                scope='observed table/cube geometry with explicit resting-cube model; no arm calibration or executable target')


def render_preview(path,result,output):
    if Path(output).exists():raise FileExistsError('choose a fresh preview path')
    with np.load(path,allow_pickle=False) as data:
        image=cv2.cvtColor(data['rgb'],cv2.COLOR_RGB2BGR);k=data['k']
    def pixel(points):
        p=np.asarray(points);q=p@k.T
        return np.rint(q[:,:2]/q[:,2:]).astype(int)
    def axes(matrix,length):
        pts=np.vstack((np.zeros(3),np.eye(3)*length))@matrix[:3,:3].T+matrix[:3,3]
        uv=pixel(pts)
        for i,color in enumerate(((0,0,255),(0,180,0),(255,0,0))):
            cv2.arrowedLine(image,tuple(uv[0]),tuple(uv[i+1]),color,2,tipLength=.15)
            cv2.putText(image,'XYZ'[i],tuple(uv[i+1]+[3,-3]),cv2.FONT_HERSHEY_SIMPLEX,.5,color,1,cv2.LINE_AA)
        return uv[0]
    origin=axes(np.asarray(result['T_camera_table']),.07)
    cv2.putText(image,'table origin',tuple(origin+[5,18]),cv2.FONT_HERSHEY_SIMPLEX,.45,(30,30,30),1,cv2.LINE_AA)
    cube=np.asarray(result['T_camera_cube_representative']);axes(cube,.035)
    from itertools import product
    local=np.asarray(list(product((-1,1),repeat=3)))*result['config']['edge_m']/2
    uv=pixel(local@cube[:3,:3].T+cube[:3,3])
    for i,a in enumerate(local):
        for j,b in enumerate(local):
            if j>i and np.sum(a!=b)==1:cv2.line(image,tuple(uv[i]),tuple(uv[j]),(0,165,255),1,cv2.LINE_AA)
    points=np.vstack((result['config']['table_polygon_xy'],result['config']['top_corners_xy']))
    lo=np.maximum(np.floor(points.min(0)).astype(int)-80,0);hi=np.minimum(np.ceil(points.max(0)).astype(int)+80,[image.shape[1],image.shape[0]])
    crop=image[lo[1]:hi[1],lo[0]:hi[0]]
    canvas=np.full((crop.shape[0]+95,max(crop.shape[1],520),3),255,np.uint8);canvas[70:70+crop.shape[0],:crop.shape[1]]=crop
    center=np.asarray(result['block_pose']['center_m'])*1000
    lines=['Observed table frame + 50 mm cube (candidate)',f'Cube center in table: [{center[0]:+.1f}, {center[1]:+.1f}, {center[2]:+.1f}] mm','Z=25 mm assumes cube rests flat; base transform UNKNOWN']
    for i,line in enumerate(lines):cv2.putText(canvas,line,(8,18+i*21),cv2.FONT_HERSHEY_SIMPLEX,.43,(20,20,20),1,cv2.LINE_AA)
    cv2.putText(canvas,'Geometry checks: '+result['checks']['consistency']+' | NO MOTION',(8,canvas.shape[0]-8),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,80,180),1,cv2.LINE_AA)
    if not cv2.imwrite(str(output),canvas):raise ValueError('preview write failed')


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('frame','config','output'):p.add_argument(name,type=Path)
    p.add_argument('--preview',type=Path)
    a=p.parse_args();r=observe(a.frame,json.loads(a.config.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    if a.preview:render_preview(a.frame,r,a.preview)


if __name__=='__main__':main()
