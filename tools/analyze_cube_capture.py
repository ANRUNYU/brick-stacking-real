"""Manual-ROI real cube diagnostics; no TF or motion approval.

ROI config records image-space top corners, table rectangle, exclusion rectangle,
normal sign hint, and diagnostic RANSAC settings. Corner dimensions assume the
cube top is parallel to the local table; they are not independent metrology.
"""
import argparse
import itertools
import json
from pathlib import Path
import cv2
import numpy as np
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.table_plane import fit_table_plane


def analyze(directory, config):
    corners=np.asarray(config['top_corners_uv'],float)
    records=[]; top_series=[]; table_series=[]
    for path in sorted(directory.glob('frame_*.npz')):
        with np.load(path,allow_pickle=False) as data:
            d=data['depth_m'].astype(float);k=data['k'];meta=json.loads(str(data['metadata'].item()))
        yy,xx=np.indices(d.shape)
        valid=np.isfinite(d)&(d>0)
        top=np.zeros(d.shape,np.uint8)
        cv2.fillConvexPoly(top,np.rint(corners).astype(np.int32),1)
        radius=config['top_erosion_px']
        top=cv2.erode(top,np.ones((2*radius+1,2*radius+1),np.uint8)).astype(bool)
        table=np.zeros(d.shape,bool)
        x0,y0,x1,y1=config['table_rect_xyxy'];table[y0:y1,x0:x1]=True
        x0,y0,x1,y1=config['exclude_rect_xyxy'];table[y0:y1,x0:x1]=False
        train=table&valid&((xx+yy)%2==0)
        check=table&valid&((xx+yy)%2==1)
        def xyz(mask): return backproject(np.c_[xx[mask],yy[mask]],d[mask],k)
        plane=fit_table_plane(xyz(train),normal_hint=config['normal_hint_camera'],distance_threshold_m=config['ransac_threshold_m'],iterations=100,min_inlier_ratio=.8)
        heights=plane.heights(xyz(top&valid))
        if len(heights)<10: raise ValueError('too few valid top interior pixels')
        height=float(np.median(heights))
        top_points=xyz(top&valid)
        top_center=top_points.mean(0)
        _, singular, vh=np.linalg.svd(top_points-top_center,full_matrices=False)
        if singular[1]<1e-10: raise ValueError('degenerate top plane')
        top_normal=vh[-1]
        if top_normal@np.asarray(plane.normal)<0: top_normal=-top_normal
        angle=float(np.degrees(np.arccos(np.clip(top_normal@np.asarray(plane.normal),-1,1))))
        top_plane_rms=float(np.sqrt(np.mean(((top_points-top_center)@top_normal)**2)))
        # Intersect manual RGB corner rays with plane at observed median height.
        rays=backproject(corners,np.ones(4),k)
        n=np.asarray(plane.normal)
        denom=rays@n
        if np.any(np.abs(denom)<1e-6): raise ValueError('grazing ray')
        vertices=rays*((height-plane.offset_m)/denom)[:,None]
        edges=np.linalg.norm(vertices-np.roll(vertices,-1,axis=0),axis=1)
        top_denominator=rays@top_normal
        if np.any(np.abs(top_denominator)<1e-6): raise ValueError('grazing top ray')
        independent_vertices=rays*((top_center@top_normal)/top_denominator)[:,None]
        independent_edges=np.linalg.norm(independent_vertices-np.roll(independent_vertices,-1,axis=0),axis=1)
        sensitivity=[]
        for i in range(4):
            lengths=[]
            for offsets in itertools.product((-1,1),repeat=4):
                pair=corners[[i,(i+1)%4]]+np.asarray(offsets).reshape(2,2)
                rays_pair=backproject(pair,np.ones(2),k)
                points=rays_pair*((height-plane.offset_m)/(rays_pair@n))[:,None]
                lengths.append(float(np.linalg.norm(points[1]-points[0])))
            sensitivity.append([min(lengths),max(lengths)])
        heldout=plane.heights(xyz(check))
        records.append({'file':path.name,'stamp_s':meta['stamp_s'],
                        'top_valid_ratio':float(valid[top].mean()),
                        'table_fit_rms_m':plane.rms_m,
                        'table_spatial_holdout_p95_abs_m':float(np.percentile(np.abs(heldout),95)),
                        'top_height_m':height,'height_minus_measured_edge_m':height-config['measured_edge_m'],
                        'top_height_spatial_mad_m':float(np.median(np.abs(heights-height))),
                        'manual_corner_edge_m':edges.tolist(),
                        'independent_top_plane_edges_m':independent_edges.tolist(),
                        'top_table_normal_angle_deg':angle, 'top_plane_rms_m':top_plane_rms,
                        'corner_plus_minus_1px_edge_range_m':sensitivity,
                        'table_normal_camera':list(plane.normal)})
        top_series.append(np.where(valid[top],d[top],np.nan))
        table_series.append(np.where(valid[table],d[table],np.nan))
    if len(records)<2: raise ValueError('multiple frames required')
    def jitter(series):
        a=np.stack(series);a=a[:,np.isfinite(a).all(0)]
        return float(np.median(np.std(a,axis=0))) if a.shape[1] else None
    h=np.array([r['top_height_m'] for r in records])
    e=np.array([r['manual_corner_edge_m'] for r in records])
    return {'source':'real_recorded','config':config,'n_frames':len(records),
            'median_height_m':float(np.median(h)),
            'height_range_m':[float(h.min()),float(h.max())],
            'height_temporal_std_m':float(h.std()),
            'top_pixel_temporal_std_median_m':jitter(top_series),
            'table_pixel_temporal_std_median_m':jitter(table_series),
            'manual_corner_edges_median_m':np.median(e,axis=0).tolist(),
            'frames':records,'approved':False,'motion_enabled':False,
            'limitations':['manual RGB corners uncertain at low pixel resolution',
                           'corner intersection assumes parallel top/table planes',
                           'spatial holdout pixels share same sensor systematic errors',
                           'single stationary sample; no independent metrology tolerance',
                           'corner +/-1px ranges are sensitivity only, not confidence bounds',
                           'no camera-to-arm extrinsic or TCP']}


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('directory',type=Path);p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    result=analyze(args.directory,json.loads(args.config.read_text(encoding='utf-8-sig')))
    with args.output.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('frames','config')},indent=2))


if __name__=='__main__': main()
