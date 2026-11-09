"""Recorded rectified RGB-D checkerboard -> metric center for fixed-camera fit.

Planar IPPE candidates are retained. Center is invariant to a 180-degree corner
ordering reversal; no permanently labelled board orientation or robot TF is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from brick_stacking.models.camera_frame import CameraFrame


def observe(path,*,columns,rows,square_m,max_pixel_error,max_depth_error_m,max_center_ambiguity_m):
    if min(columns,rows)<3 or not all(np.isfinite(v) and v>0 for v in (square_m,max_pixel_error,max_depth_error_m,max_center_ambiguity_m)):
        raise ValueError('explicit pattern, measured square length and diagnostic thresholds required')
    with np.load(path,allow_pickle=False) as d:
        meta=json.loads(str(d['metadata'].item()))
        frame=CameraFrame(d['rgb'],d['depth_m'],d['k'],meta['camera_id'],meta['frame_id'],meta['stamp_s'],meta['clock_domain'],meta['source'],meta['registered'],meta['rectified'])
    gray=cv2.cvtColor(frame.rgb,cv2.COLOR_RGB2GRAY)
    ok,corners=cv2.findChessboardCornersSB(gray,(columns,rows),flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE)
    geometry=dict(kind='checkerboard_center',inner_corners=[columns,rows],square_m=square_m,square_source='operator measured printed board')
    result=dict(schema_version='c-checkerboard-center-1',source=frame.source,camera_serial=frame.camera_id,
                frame_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),camera_stamp_s=frame.stamp_s,camera_clock_domain=frame.clock_domain,
                host_receive_stamp_s=meta.get('host_receive_stamp_s'),host_clock_domain=meta.get('host_clock_domain'),
                target_id=f'checkerboard_{columns}x{rows}_{square_m:g}m_C37',target_geometry=geometry,
                config=dict(edge_m=square_m,edge_source='operator measured printed checkerboard square'),
                center_camera_m=None,orientation_xyzw=None,approved=False,motion_enabled=False)
    if not ok:
        result['quality']=dict(consistency='REJECTED',reason='complete declared corner pattern not detected');return result
    obj=np.zeros((columns*rows,3),np.float32);obj[:,:2]=np.mgrid[0:columns,0:rows].T.reshape(-1,2)*square_m
    ok,rvecs,tvecs,_=cv2.solvePnPGeneric(obj,corners,frame.k,np.zeros(5),flags=cv2.SOLVEPNP_IPPE)
    if not ok:raise ValueError('planar board PnP failed')
    observed=[]
    for u,v in corners.reshape(-1,2):
        x,y=int(round(float(u))),int(round(float(v)))
        patch=frame.depth_m[max(0,y-2):y+3,max(0,x-2):x+3];valid=patch[np.isfinite(patch)&(patch>0)]
        observed.append(float(np.median(valid)) if len(valid)>=5 else np.nan)
    observed=np.array(observed);valid=np.isfinite(observed);candidates=[]
    for rv,tv in zip(rvecs,tvecs):
        rotation=cv2.Rodrigues(rv)[0];xyz=obj@rotation.T+tv.ravel()
        if np.any(xyz[:,2]<=0):continue
        pixels,_=cv2.projectPoints(obj,rv,tv,frame.k,np.zeros(5));errors=np.linalg.norm(pixels.reshape(-1,2)-corners.reshape(-1,2),axis=1)
        candidates.append(dict(center_camera_m=xyz.mean(0).tolist(),reprojection_rms_px=float(np.sqrt(np.mean(errors**2))),reprojection_max_px=float(errors.max()),
                               depth_median_abs_error_m=float(np.median(np.abs(xyz[valid,2]-observed[valid]))) if valid.any() else None))
    if not candidates:raise ValueError('no positive-depth planar solution')
    candidates.sort(key=lambda r:r['reprojection_rms_px']);best=candidates[0]
    ambiguity=max((float(np.linalg.norm(np.array(v['center_camera_m'])-best['center_camera_m'])) for v in candidates),default=0.)
    passes=best['reprojection_max_px']<=max_pixel_error and valid.sum()>=10 and best['depth_median_abs_error_m']<=max_depth_error_m and ambiguity<=max_center_ambiguity_m
    result.update(center_camera_m=best['center_camera_m'],corners_xy=corners.reshape(-1,2).tolist(),candidates=candidates,
                  quality=dict(consistency='PASS' if passes else 'FAIL',corner_count=len(corners),depth_corner_count=int(valid.sum()),
                               reprojection_rms_px=best['reprojection_rms_px'],reprojection_max_px=best['reprojection_max_px'],
                               depth_median_abs_error_m=best['depth_median_abs_error_m'],planar_center_ambiguity_m=ambiguity,
                               max_pixel_error=max_pixel_error,max_depth_error_m=max_depth_error_m,max_center_ambiguity_m=max_center_ambiguity_m),
                  notice='camera-frame board center only; robot extrinsic requires rigid mounting and matched joint observations; board orientation unlabelled')
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('frame',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--columns',type=int,required=True);p.add_argument('--rows',type=int,required=True);p.add_argument('--square-mm',type=float,required=True)
    p.add_argument('--max-pixel-error',type=float,required=True);p.add_argument('--max-depth-error-mm',type=float,required=True);p.add_argument('--max-center-ambiguity-mm',type=float,required=True)
    a=p.parse_args();r=observe(a.frame,columns=a.columns,rows=a.rows,square_m=a.square_mm/1000,max_pixel_error=a.max_pixel_error,max_depth_error_m=a.max_depth_error_mm/1000,max_center_ambiguity_m=a.max_center_ambiguity_mm/1000)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps(r['quality']))


if __name__=='__main__':main()
