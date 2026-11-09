"""Per-frame visible support-plane discovery; no fixed image ROI or world pose.

Selects a plane with elevated, chromatic object evidence inside its visible
support hull. This is a task-conditioned tabletop hypothesis, not a general
semantic table recognizer. Ambiguous competing surfaces fail explicitly.
"""
import cv2
import numpy as np
from brick_stacking.vision.color_segmentation import segment_colors
from brick_stacking.vision.instance_quality import cube_geometry_error
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.table_plane import fit_table_plane


def discover_table_surface(frame, profile, color_masks):
    valid = np.isfinite(frame.depth_m) & (frame.depth_m > 0)
    yy, xx = np.where(valid)
    if len(xx) < 100:
        raise ValueError("insufficient depth for automatic table search")
    points = backproject(np.column_stack((xx, yy)), frame.depth_m[yy, xx], frame.k)
    stride = max(1, int(np.ceil(len(points) / profile['plane_sample_limit'])))
    sample = points[::stride]
    remaining = sample.copy()
    chromatic = np.logical_or.reduce([m > 0 for m in color_masks.values()])[yy, xx]
    hypotheses = []
    search_statistics=[]
    low, high = profile['candidate_height_range_m']
    for _ in range(profile.get('auto_max_planes', 6)):
        if len(remaining) < 100:
            break
        try:
            statistics={}
            plane = fit_table_plane(remaining, normal_hint=profile['normal_hint_camera'],
                distance_threshold_m=profile['plane_threshold_m'],
                iterations=profile.get('auto_plane_iterations',1000), min_inlier_ratio=.04,
                confidence=profile.get('auto_ransac_confidence'),statistics=statistics)
            search_statistics.append(statistics)
        except ValueError:
            break
        remainder_height = plane.heights(remaining)
        remaining = remaining[np.abs(remainder_height) > profile['plane_threshold_m'] * 2]
        heights = plane.heights(points)
        on_plane = np.abs(heights) <= profile['plane_threshold_m']
        mask = np.zeros(valid.shape, np.uint8)
        mask[yy[on_plane], xx[on_plane]] = 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        if count < 2 or plane.rms_m > profile['max_plane_rms_m']:
            continue
        largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        sy, sx = np.where(labels == largest)
        if len(sx) < valid.size * .01:
            continue
        hull = cv2.convexHull(np.column_stack((sx, sy)).astype(np.int32))
        roi = np.zeros_like(mask)
        cv2.fillConvexPoly(roi, hull, 255)
        # Objects project over the visible support. No arbitrary fixed box.
        inside = roi[yy, xx] > 0
        evidence = inside & chromatic & (heights >= low) & (heights <= high)
        support = int(np.count_nonzero(inside & on_plane))
        score = int(evidence.sum())
        hypotheses.append((score, support, plane, roi))
    hypotheses.sort(key=lambda item: item[0]*np.sqrt(item[1]), reverse=True)
    if not hypotheses or hypotheses[0][0] < profile['top_min_points']:
        raise ValueError("automatic table search: no elevated colored-object support")
    if len(hypotheses) > 1 and hypotheses[1][0]*np.sqrt(hypotheses[1][1]) >= hypotheses[0][0]*np.sqrt(hypotheses[0][1]) * .85:
        raise ValueError("automatic table search: competing support surfaces")
    score, support, plane, roi = hypotheses[0]
    return plane, roi, {'mode': 'automatic_per_frame', 'colored_support_px': score,
        'plane_support_px': support, 'hypotheses': len(hypotheses),
        'ransac_searches':search_statistics,
        'world_frame_established': False}


def adaptive_color_masks(rgb, ranges, foreground=None):
    """Hue categories stay explicit; S/V gates follow visible colored support.

    Rejects near-neutral/dark observations rather than guessing their color.
    Broad provisional masks are used only to propose the support surface.
    """
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    result = {}
    for color, bands in ranges.items():
        if foreground is not None and color != 'yellow':
            result[color] = segment_colors(rgb, {color: bands})[color]
            continue
        hue = np.zeros(hsv.shape[:2], bool)
        for low, high in bands:
            hue |= (hsv[..., 0] >= low[0]) & (hsv[..., 0] <= high[0])
        seeds = hue & (hsv[..., 1] >= 60) & (hsv[..., 2] >= 40)
        if foreground is not None:
            seeds &= foreground
        saturation, brightness = 60., 40.
        if seeds.sum() >= 12:
            saturation = max(60., float(np.median(hsv[..., 1][seeds])) * .97)
            brightness = max(25., float(np.median(hsv[..., 2][seeds])) * .50)
        result[color] = ((hue & (hsv[..., 1] >= saturation) &
                          (hsv[..., 2] >= brightness)).astype(np.uint8) * 255)
    return result


def color_mask_hypotheses(rgb, ranges, foreground, color, base_mask):
    """Yellow shares warm table/side hues; test observed saturation hypotheses.

    Physical region validation decides which proposals survive, never a target
    count. Other color adaptation has not been validated and stays explicit.
    """
    if color != 'yellow':
        return [base_mask]
    hsv = cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    hue = np.zeros(foreground.shape,bool)
    for low,high in ranges[color]:
        hue |= (hsv[...,0]>=low[0]) & (hsv[...,0]<=high[0])
    support = hue & foreground & (hsv[...,1]>=60) & (hsv[...,2]>=40)
    result = [segment_colors(rgb,{color:ranges[color]})[color],base_mask]
    if support.sum() >= 12:
        median_s = float(np.median(hsv[...,1][support]))
        median_v = float(np.median(hsv[...,2][support]))
        for ratio in (.94,.98,1.):
            result.append((hue & (hsv[...,1]>=max(60,median_s*ratio)) &
                           (hsv[...,2]>=max(25,median_v*.5))).astype(np.uint8)*255)
    return result


def consolidate_color_proposals(proposals, edge_m, *, frame=None, noise_m=0., diagnostics=None,
                                residual_support_gate=False):
    """Deduplicate multiple threshold proposals using observed metric centers.

    Ambiguous regions are retained if their pixels remain unexplained. Return
    the suppression evidence for diagnostics, not only the accepted list.
    """
    good = [(m,c) for m,c in proposals if c['status']=='SINGLE_CUBE_CANDIDATE']
    # Maximum color area can include a neighbour's surface and move a center by
    # centimetres. Prefer cube-like geometry, using area only as a tie breaker.
    good.sort(key=lambda item:(cube_geometry_error(item[1],edge_m),-item[1]['area_px']))
    kept=[]
    for mask,c in good:
        center=np.array(c['center_camera_m'])
        if any(np.linalg.norm(center-np.array(k['center_camera_m'])) < edge_m*.65 for _,k in kept):
            continue
        kept.append((mask,c))
    explained=np.logical_or.reduce([m for m,_ in kept]) if kept else None
    ambiguous=[]
    for mask,c in proposals:
        if c['status']!='AMBIGUOUS':
            continue
        if frame is not None and kept:
            yy,xx=np.where(mask)
            points=backproject(np.column_stack((xx,yy)),frame.depth_m[yy,xx],frame.k)
            excess=[]
            tolerances=[]
            for _,instance in kept:
                axes=np.asarray(instance['geometry_axes_camera'])
                local=(points-np.asarray(instance.get('support_volume_center_camera_m',instance['center_camera_m'])))@axes.T
                half_extent=np.asarray(instance.get('geometry_extent_m',[edge_m]*3))/2
                uncertainty=np.minimum(np.asarray(instance.get('geometry_model_uncertainty_m',[0.]*3)),edge_m*.1)
                tolerance=noise_m+uncertainty
                # A depth pixel samples a finite RGB footprint. Propagate its
                # half-pixel lateral extent through the actual K and cube axes,
                # rather than expanding masks by a fixed pixel radius.
                rays=points/points[:,2,None]
                normal=axes[2];denominator=rays@normal
                observable=np.abs(denominator)>.1
                safe_denominator=np.where(observable,denominator,1.)
                du=np.zeros_like(points);dv=np.zeros_like(points)
                du[:,0]=points[:,2]/frame.k[0,0];dv[:,1]=points[:,2]/frame.k[1,1]
                du-=rays*(points[:,2]*normal[0]/(frame.k[0,0]*safe_denominator))[:,None]
                dv-=rays*(points[:,2]*normal[1]/(frame.k[1,1]*safe_denominator))[:,None]
                pixel_extent=.5*(np.abs(du@axes.T)+np.abs(dv@axes.T))
                pixel_extent=np.minimum(pixel_extent,edge_m*.1)
                pixel_extent[~observable]=0.
                excess.append(np.max(np.abs(local)-half_extent-tolerance-pixel_extent,axis=1))
                tolerances.append(tolerance.tolist())
            errors=np.asarray(excess)
            explained_fraction=float(np.mean(np.min(errors,axis=0)<=0))
            if diagnostics is not None:
                diagnostics.setdefault('fragment_volume_checks',[]).append({
                    'candidate_id':c['candidate_id'],'bbox_xywh':c['bbox_xywh'],
                    'explained_fraction':explained_fraction,
                    'outside_tolerance_q95_m':float(np.quantile(np.min(errors,axis=0),.95)),
                    'axis_tolerances_m':tolerances,'plane_tolerance_m':noise_m,
                    'pixel_sampling_extent_included':True,'sampling_model':'support_plane_ray_differential'})
            if explained_fraction >= .95:
                if diagnostics is not None:
                    diagnostics.setdefault('explained_surface_fragments',[]).append({
                        'proposal':c,'reason':'depth_points_inside_existing_cube_volumes',
                        'explained_fraction':explained_fraction,'axis_tolerances_m':tolerances,
                        'supporting_candidate_ids':[k['candidate_id'] for index,(_,k) in enumerate(kept)
                            if np.any(errors[index]<=0)]})
                continue
            if residual_support_gate:
                residual=np.zeros_like(mask)
                residual[yy,xx]=np.min(errors,axis=0)>0
                count,_,stats,_=cv2.connectedComponentsWithStats(residual.astype(np.uint8))
                largest=int(stats[1:,cv2.CC_STAT_AREA].max()) if count>1 else 0
                z=float(np.median(points[:,2]))
                minimum=max(9.,.15*(frame.k[0,0]*edge_m/z)**2)
                if largest<minimum:
                    if diagnostics is not None:
                        diagnostics.setdefault('low_support_unassigned_surfaces',[]).append({
                            'proposal':c,'status':'LOW_SUPPORT_UNASSIGNED_SURFACE',
                            'unassigned_points':int(residual.sum()),'largest_connected_support_px':largest,
                            'minimum_instance_support_px':minimum,'not_object_absence_evidence':True})
                    continue
            # No pixel-nearness fallback: an adjacent partial object outside
            # the supported 3D volumes must remain unresolved.
            if not any(np.count_nonzero(mask & m) >= min(mask.sum(),m.sum())*.5 for m,_ in ambiguous):
                ambiguous.append((mask,c))
            continue
        # Account for contour/threshold uncertainty of a few image pixels.
        covered=(cv2.dilate(explained.astype(np.uint8),np.ones((5,5),np.uint8))>0
                 if explained is not None else np.zeros_like(mask))
        if np.count_nonzero(mask & ~covered) > mask.sum()*.25:
            if not any(np.count_nonzero(mask & m) >= min(mask.sum(),m.sum())*.5 for m,_ in ambiguous):
                ambiguous.append((mask,c))
    return kept+ambiguous
