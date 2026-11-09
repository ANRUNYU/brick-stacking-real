"""RGB-D tabletop prototype with explicit fixed/automatic surface modes.

No world/grasp calibration. Automatic mode re-estimates surface per frame;
seam proposals need image evidence and independent metric validation.
"""
from dataclasses import dataclass
import cv2
import numpy as np
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.table_plane import fit_table_plane
from brick_stacking.vision.color_segmentation import segment_colors
from brick_stacking.vision.adaptive_table_surface import (discover_table_surface, adaptive_color_masks,
    color_mask_hypotheses, consolidate_color_proposals)
from brick_stacking.vision.seam_segmentation import split_with_visible_seams


@dataclass
class TabletopObservation:
    plane: object
    roi_mask: np.ndarray
    heights_m: np.ndarray
    candidates: list[dict]
    diagnostics: dict | None = None


def make_roi(shape, polygon):
    points = np.asarray(polygon, float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
        raise ValueError("finite polygon ROI with at least three vertices required")
    if np.any(points < 0) or np.any(points[:,0] >= shape[1]) or np.any(points[:,1] >= shape[0]):
        raise ValueError("ROI vertices outside configured image")
    if not np.all(points == np.round(points)):
        raise ValueError("integer pixel ROI required")
    result = np.zeros(shape, np.uint8)
    cv2.fillPoly(result, [points.astype(np.int32)], 255)
    if np.count_nonzero(result) < 10:
        raise ValueError("ROI has negligible area")
    return result


class TabletopDetector:
    def __init__(self, profile):
        self.profile = profile
        if profile.get('surface_mode','fixed_roi') not in {'fixed_roi','automatic'}:
            raise ValueError('unsupported surface mode')
        if profile.get('surface_mode')=='automatic':
            for name,default in [('auto_max_planes',6),('auto_plane_iterations',1000)]:
                value=profile.get(name,default)
                if type(value) is not int or not 1 <= value <= (12 if name=='auto_max_planes' else 10000):
                    raise ValueError(f'invalid {name}')
        edge = profile["nominal_edge_m"]
        if not np.isfinite(edge) or edge <= 0:
            raise ValueError("positive nominal edge required")
        if not 0 < profile["span_relative_tolerance"] < 1:
            raise ValueError("invalid span tolerance")
        for name in ("min_area_px", "top_min_points", "top_band_m", "plane_threshold_m", "plane_iterations",
                     "plane_sample_limit", "max_plane_rms_m", "max_height_spread_m"):
            if not np.isfinite(profile[name]) or profile[name] <= 0:
                raise ValueError(f"positive {name} required")
        if type(profile["opening_kernel_px"]) is not int or profile["opening_kernel_px"] not in {1,3,5}:
            raise ValueError("opening kernel must be 1,3,5")
        if not 0 < profile["min_plane_inlier_ratio"] <= 1:
            raise ValueError("invalid plane support ratio")
        lo, hi = profile["candidate_height_range_m"]
        if not np.isfinite([lo,hi]).all() or not 0 < lo < hi:
            raise ValueError("invalid candidate height range")

    def detect(self, frame):
        p = self.profile
        automatic = p.get('surface_mode', 'fixed_roi') == 'automatic'
        if not automatic and [frame.rgb.shape[1],frame.rgb.shape[0]] != p["image_size_wh"]:
            raise ValueError("ROI profile image size mismatch")
        if frame.camera_id != p["camera_id"]:
            raise ValueError("profile belongs to a different camera")
        if automatic:
            plane, roi, diagnostics = discover_table_surface(frame, p,
                adaptive_color_masks(frame.rgb, p['hsv']))
        else:
            roi = make_roi(frame.depth_m.shape,p["roi_polygon_uv"])
            diagnostics = {'mode': 'fixed_roi'}
        valid = (roi > 0) & np.isfinite(frame.depth_m) & (frame.depth_m > 0)
        rows, cols = np.where(valid)
        if len(rows) < 30:
            raise ValueError("insufficient valid ROI depth")
        xyz = backproject(np.column_stack((cols,rows)),frame.depth_m[rows,cols],frame.k)
        stride = max(1,int(np.ceil(len(rows)/p["plane_sample_limit"])))
        if not automatic:
            plane = fit_table_plane(xyz[::stride],normal_hint=p["normal_hint_camera"],
                distance_threshold_m=p["plane_threshold_m"],iterations=p["plane_iterations"],
                min_inlier_ratio=p["min_plane_inlier_ratio"])
        if plane.rms_m > p["max_plane_rms_m"]:
            raise ValueError("plane residual above configured gate")
        normal = np.array(plane.normal)
        # This tangent basis is camera-referenced, not a calibrated table XY.
        tx = np.array([1.,0.,0.])
        tx -= tx.dot(normal)*normal
        if np.linalg.norm(tx) < 1e-8:
            raise ValueError("table tangent basis degenerate")
        tx /= np.linalg.norm(tx)
        ty = np.cross(normal,tx)
        height = np.full(frame.depth_m.shape,np.nan)
        height[rows,cols] = plane.heights(xyz)
        low, high = p["candidate_height_range_m"]
        object_mask = valid & (height >= low) & (height <= high)
        candidates = []
        masks = (adaptive_color_masks(frame.rgb,p['hsv'],object_mask) if p.get('adaptive_color',False)
                 else segment_colors(frame.rgb,p['hsv']))
        for color, base_mask in masks.items():
            adaptive = p.get('adaptive_color',False)
            variants = (color_mask_hypotheses(frame.rgb,p['hsv'],object_mask,color,base_mask)
                        if adaptive else [base_mask])
            proposals=[]
            for variant_index,mask in enumerate(variants):
                mask=mask.copy()
                mask[~object_mask] = 0
                kernel = np.ones((p["opening_kernel_px"],)*2,np.uint8)
                mask = cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)
                count,labels,stats,_ = cv2.connectedComponentsWithStats(mask)
                for label in range(1,count):
                    area=int(stats[label,cv2.CC_STAT_AREA])
                    min_area = p['min_area_px']
                    if automatic:
                        z = float(np.median(frame.depth_m[labels == label]))
                        min_area = max(9., .15 * (frame.k[0,0]*p['nominal_edge_m']/z)**2)
                    if area < min_area:
                        continue
                    component = labels == label
                    def assess(component,offset=(0,0)):
                        return self._assess(frame, component, height, plane, normal, tx, ty, color,offset=offset)
                    parts = (split_with_visible_seams(frame.rgb, component, assess)
                             if p.get('seam_splitting', False)
                             else [(component, assess(component))])
                    for part_index, (part_mask, candidate) in enumerate(parts):
                        candidate['candidate_id'] = f'{color}_{variant_index}_{label}_{part_index}'
                        candidate['color_hypothesis'] = variant_index
                        proposals.append((part_mask,candidate))
            selected = (consolidate_color_proposals(proposals,p['nominal_edge_m'],frame=frame,
                        noise_m=min(2*plane.rms_m,p['nominal_edge_m']*.1),diagnostics=diagnostics,
                        residual_support_gate=automatic)
                        if len(variants)>1 else proposals)
            diagnostics.setdefault('color_proposals',{})[color] = {
                'generated':len(proposals),'selected':len(selected),'hypotheses':len(variants)}
            candidates.extend(c for _,c in selected)
        return TabletopObservation(plane,roi,height,candidates,diagnostics)

    def _assess(self, frame, component, height, plane, normal, tx, ty, color,offset=(0,0)):
        p = self.profile
        ys,xs = np.where(component)
        xs=xs+offset[0];ys=ys+offset[1]
        x,y,w,h = cv2.boundingRect(np.column_stack((xs,ys)).astype(np.int32))
        area = len(xs)
        top = np.abs(height[ys,xs]-p["nominal_edge_m"]) <= p["top_band_m"]
        yy,xx = ys[top],xs[top]
        candidate = dict(candidate_id='',color=color,
            bbox_xywh=[x,y,w,h],centroid_uv=[float(xs.mean()),float(ys.mean())],area_px=area,
            top_points=len(xx),status="AMBIGUOUS",reason="insufficient_top_face_support",
            footprint_size_m=None,top_height_m=None,center_camera_m=None,
            frame_id=frame.frame_id,stamp_s=frame.stamp_s,clock_domain=frame.clock_domain,
            control_ready=False,nominal_edge_m=p['nominal_edge_m'])
        if len(xx) >= p["top_min_points"]:
            points = backproject(np.column_stack((xx,yy)),frame.depth_m[yy,xx],frame.k)
            tangent = np.column_stack((points@tx,points@ty)).astype(np.float32)
            rect = cv2.minAreaRect(tangent)
            hull_area = float(cv2.contourArea(cv2.convexHull(tangent)))
            theta=np.deg2rad(rect[2])
            rotation=np.array([[np.cos(theta),np.sin(theta)],[-np.sin(theta),np.cos(theta)]])
            oriented=tangent@rotation.T
            lower,upper=np.quantile(oriented,[.05,.95],axis=0)
            robust_center=((lower+upper)/2)@rotation
            nominal_corners=cv2.boxPoints((tuple(map(float,robust_center)),(p['nominal_edge_m'],p['nominal_edge_m']),rect[2]))
            sizes = sorted(float(v) for v in rect[1])
            top_height = float(np.median(height[yy,xx]))
            spread = float(np.ptp(np.quantile(height[yy,xx],[.1,.9])))
            good_size = all(abs(v/p["nominal_edge_m"]-1) <= p["span_relative_tolerance"] for v in sizes)
            good_spread = spread <= p["max_height_spread_m"]
            candidate.update(footprint_size_m=sizes,top_height_m=top_height,height_spread_m=spread,
                footprint_area_m2=hull_area,footprint_fill_ratio=hull_area/max(np.prod(sizes),1e-12))
            angle=np.deg2rad(rect[2])
            candidate['geometry_axes_camera']=[(np.cos(angle)*tx+np.sin(angle)*ty).tolist(),
                (-np.sin(angle)*tx+np.cos(angle)*ty).tolist(),normal.tolist()]
            candidate['geometry_extent_m']=[max(p['nominal_edge_m'],float(rect[1][0])),
                max(p['nominal_edge_m'],float(rect[1][1])),p['nominal_edge_m']]
            support_center=(tx*rect[0][0]+ty*rect[0][1]+
                            normal*(top_height-plane.offset_m-p['nominal_edge_m']/2))
            candidate['support_volume_center_camera_m']=support_center.tolist()
            candidate['geometry_model_uncertainty_m']=[abs(float(rect[1][0])-p['nominal_edge_m'])/2,
                abs(float(rect[1][1])-p['nominal_edge_m'])/2,spread/2]
            ray=np.array([(float(np.median(xx))-frame.k[0,2])/frame.k[0,0],
                (float(np.median(yy))-frame.k[1,2])/frame.k[1,1],1.])
            denominator=float(normal@ray)
            if abs(denominator)>1e-8:
                z=float(np.median(points[:,2]))
                du=np.array([z/frame.k[0,0],0.,0.])-ray*z*normal[0]/(frame.k[0,0]*denominator)
                dv=np.array([0.,z/frame.k[1,1],0.])-ray*z*normal[1]/(frame.k[1,1]*denominator)
                axes=np.asarray(candidate['geometry_axes_camera'])[:2]
                candidate['footprint_sampling_half_extent_m']=(.5*(np.abs(axes@du)+np.abs(axes@dv))).tolist()
            candidate['footprint_raw_size_m']=[float(v) for v in rect[1]]
            corners_camera=(nominal_corners[:,0,None]*tx+nominal_corners[:,1,None]*ty+
                            normal*(top_height-plane.offset_m))
            projected=corners_camera@frame.k.T
            if np.all(projected[:,2]>0):
                candidate['nominal_top_polygon_uv']=(projected[:,:2]/projected[:,2:]).tolist()
            if good_size and good_spread:
                # Tangent rectangle center, median top height, half-edge
                # normal correction. Hypothesis, not absolute truth.
                surface = tx*robust_center[0] + ty*robust_center[1] + normal*(top_height-plane.offset_m)
                center = surface-normal*p["nominal_edge_m"]/2
                candidate.update(status="SINGLE_CUBE_CANDIDATE",reason="color_height_footprint_supported",
                                 center_camera_m=center.tolist(),center_estimator='trimmed_top_surface_midrange',
                                 center_trim_quantiles=[.05,.95])
            else:
                candidate["reason"] = "merged_or_partial_or_irregular_geometry"
        return candidate
