"""Three explicitly selected face interiors -> unmarked cube center diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.cube_center import center_from_faces


def analyze(path,config):
    with np.load(path,allow_pickle=False) as data:
        meta=json.loads(str(data['metadata'].item()))
        frame=CameraFrame(data['rgb'],data['depth_m'],data['k'],meta['camera_id'],meta['frame_id'],meta['stamp_s'],meta['clock_domain'],meta['source'],meta['registered'],meta['rectified'])
    if config['camera_serial']!=frame.camera_id or not config.get('edge_source') or not config.get('roi_source'):
        raise ValueError('camera binding, measured edge and ROI provenance required')
    h,w=frame.depth_m.shape;yy,xx=np.indices((h,w));used=np.zeros((h,w),bool);faces=[];counts=[]
    if len(config['face_polygons_xy'])!=3:raise ValueError('exactly three distinct visible face ROIs required')
    for polygon in config['face_polygons_xy']:
        p=np.asarray(polygon,float)
        if p.ndim!=2 or p.shape[1]!=2 or len(p)<3 or not np.isfinite(p).all() or np.any(p<0) or np.any(p[:,0]>=w) or np.any(p[:,1]>=h):raise ValueError('valid in-image convex polygon required')
        p=np.rint(p).astype(np.int32)
        if not cv2.isContourConvex(p):raise ValueError('convex face ROI required')
        mask=np.zeros((h,w),np.uint8);cv2.fillConvexPoly(mask,p,1)
        erosion=config['erosion_px']
        if type(erosion) is not int or not 0<=erosion<=10:raise ValueError('explicit ROI erosion in [0,10] pixels required')
        if erosion:mask=cv2.erode(mask,np.ones((erosion*2+1,erosion*2+1),np.uint8))
        mask=mask.astype(bool)
        if np.any(used&mask):raise ValueError('overlapping face interiors')
        used|=mask;valid=mask&np.isfinite(frame.depth_m)&(frame.depth_m>0)
        a=valid&((xx+yy)%2==0);b=valid&((xx+yy)%2==1)
        def xyz(m):return backproject(np.c_[xx[m],yy[m]],frame.depth_m[m],frame.k)
        faces.append((xyz(a),xyz(b)));counts.append(dict(selected=int(mask.sum()),valid=int(valid.sum()),training=int(a.sum()),validation=int(b.sum())))
    result=dict(schema_version='c-cube-center-observation-1',source=frame.source,camera_serial=frame.camera_id,
                frame_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),camera_stamp_s=frame.stamp_s,camera_clock_domain=frame.clock_domain,
                host_receive_stamp_s=meta.get('host_receive_stamp_s'),host_clock_domain=meta.get('host_clock_domain'),
                center_camera_m=None,config=config,face_pixel_counts=counts,approved=False,motion_enabled=False,
                time_alignment='NOT_ESTABLISHED',notice='device and host receive clocks kept separate; no reference pose/camera extrinsic here')
    try:
        center,report=center_from_faces(faces,edge_m=config['edge_m'],plane_threshold_m=config['plane_threshold_m'],
                    min_inlier_ratio=config['min_inlier_ratio'],max_holdout_m=config['max_holdout_m'],
                    max_normal_dot=config['max_normal_dot'],max_condition_number=config['max_condition_number'],
                    regular_cube_constraint=config.get('regular_cube_constraint',False))
        result.update(center_camera_m=center.tolist(),quality=report)
    except ValueError as exc:result.update(quality=dict(consistency='REJECTED',reason=str(exc)))
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('frame_npz',type=Path);p.add_argument('config',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    r=analyze(a.frame_npz,json.loads(a.config.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps(dict(quality=r['quality'],center_camera_m=r['center_camera_m'],counts=r['face_pixel_counts'])))


if __name__=='__main__':main()
