"""Split oversized color regions only when observed RGB edges support a cut.

No expected count, layout coordinates or length/count division is used.
Each resulting region must independently satisfy the metric cube gates.
"""
import cv2
import numpy as np
from brick_stacking.vision.instance_quality import cube_geometry_error


def plausible_footprint(candidate, edge_m):
    """Compare sampling intervals with metric limits, not exact pixel edges."""
    sizes=np.asarray(candidate.get('footprint_raw_size_m',candidate['footprint_size_m']))
    half=np.asarray(candidate.get('footprint_sampling_half_extent_m',[0.,0.]))
    return bool(np.all(sizes+2*half>=.75*edge_m) and np.all(sizes-2*half<=1.35*edge_m))


def separated_instances(parts, edge_m):
    if edge_m is None:
        return True
    centers=[np.asarray(c['center_camera_m']) for _,c in parts]
    return all(np.linalg.norm(a-b) >= edge_m*.8
               for i,a in enumerate(centers) for b in centers[i+1:])


def split_with_visible_seams(rgb, component, assess, *, max_depth=4):
    """Work in the component crop; restore full-image masks only at the end."""
    yy,xx=np.where(component)
    x0=max(0,int(xx.min())-2);y0=max(0,int(yy.min())-2)
    x1=min(component.shape[1],int(xx.max())+3);y1=min(component.shape[0],int(yy.max())+3)
    local=component[y0:y1,x0:x1]
    def local_assess(mask):
        return assess(mask,offset=(x0,y0))
    attempted=[]
    for mode in ('gradient','smooth_valley','valley'):
        parts=_split_local(rgb[y0:y1,x0:x1],local,local_assess,max_depth=max_depth,evidence_mode=mode)
        attempted.append(mode)
        if all(c['status']=='SINGLE_CUBE_CANDIDATE' for _,c in parts):
            break
    result=[]
    for mask,candidate in parts:
        candidate['seam_evidence_mode']=mode
        candidate['seam_evidence_modes_tried']=attempted
        full=np.zeros_like(component);full[y0:y1,x0:x1]=mask
        if 'split_evidence_line_uv' in candidate:
            line=candidate['split_evidence_line_uv']
            candidate['split_evidence_line_uv']=[line[0]+x0,line[1]+y0,line[2]+x0,line[3]+y0]
        result.append((full,candidate))
    return result


def _split_local(rgb, component, assess, *, max_depth=4, budget=None,evidence_mode='gradient'):
    if budget is None:
        budget = [1024]
    parent = assess(component)
    if parent['status'] == 'SINGLE_CUBE_CANDIDATE' or max_depth == 0 or budget[0] <= 0:
        return [(component, parent)]
    ys, xs = np.where(component)
    if len(xs) < 20:
        return [(component, parent)]
    x, y, w, h = cv2.boundingRect(np.column_stack((xs, ys)).astype(np.int32))
    x0,y0=x,y
    x,y=max(0,x-2),max(0,y-2)
    w,h=min(rgb.shape[1]-x,w+x0-x+2),min(rgb.shape[0]-y,h+y0-y+2)
    local = component[y:y+h, x:x+w]
    feature_rgb=rgb[y:y+h,x:x+w]
    if evidence_mode=='smooth_valley':
        feature_rgb=cv2.GaussianBlur(feature_rgb,(3,3),0)
    gray = cv2.cvtColor(feature_rgb, cv2.COLOR_RGB2GRAY)
    # Scale thresholds from foreground contrast, not camera location/resolution.
    values = gray[local]
    contrast = max(12., float(np.quantile(values, .9) - np.quantile(values, .1)))
    edges = cv2.Canny(feature_rgb, max(6., contrast * .20), max(18., contrast * .60))
    channel=int(np.argmax([np.ptp(np.quantile(feature_rgb[:,:,i][local],[.1,.9])) for i in range(3)]))
    channel_image=np.ascontiguousarray(feature_rgb[:,:,channel])
    polygon=np.asarray(parent.get('nominal_top_polygon_uv',[]))
    cell_px=(float(np.median(np.linalg.norm(polygon-np.roll(polygon,1,axis=0),axis=1)))
             if polygon.shape==(4,2) else min(w,h)/2)
    kernel_size=max(3,min(15,int(round(cell_px*.15))|1))
    valley=cv2.morphologyEx(channel_image,cv2.MORPH_BLACKHAT,np.ones((kernel_size,kernel_size),np.uint8))
    baseline=float(np.median(valley[local]))
    mad=float(np.median(np.abs(valley[local].astype(float)-baseline)))
    valley_mask=((valley>=max(2.,baseline+3*mad)).astype(np.uint8)*255)
    # Thin dark joints can have low grayscale contrast. Use their observed
    # chromatic-channel valleys as well as gradients, with a noise floor.
    if evidence_mode!='gradient':
        edges=cv2.bitwise_or(edges,valley_mask)
    edges[cv2.dilate(local.astype(np.uint8),np.ones((3,3),np.uint8)) == 0] = 0
    short_side = min(w, h)
    # Edge barriers yield interior markers; watershed recovers region extent.
    # A featureless rectangle has one marker and cannot be split by this path.
    interior = local.astype(np.uint8)
    barrier = cv2.dilate(edges, np.ones((3,3),np.uint8))
    interior[barrier > 0] = 0
    count, seed_labels, stats, _ = cv2.connectedComponentsWithStats(interior)
    seeds = [i for i in range(1,count) if stats[i,cv2.CC_STAT_AREA] >= max(8, local.sum()*.04)]
    if len(seeds) >= 2:
        markers = np.zeros(local.shape,np.int32)
        markers[~cv2.dilate(local.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)] = 1
        for index, seed in enumerate(seeds,2):
            markers[seed_labels==seed] = index
        cv2.watershed(np.ascontiguousarray(rgb[y:y+h,x:x+w]),markers)
        regions = []
        edge_m = parent.get('nominal_edge_m')
        for index in range(2,len(seeds)+2):
            mask = np.zeros_like(component)
            mask[y:y+h,x:x+w] = (markers==index)&local
            if mask.sum() < 8:
                break
            candidate = assess(mask)
            if candidate['status'] != 'SINGLE_CUBE_CANDIDATE' or (edge_m is not None and
                (not plausible_footprint(candidate,edge_m) or
                 candidate.get('footprint_fill_ratio',0)<.72)):
                break
            candidate.update(reason='rgb_edge_markers_watershed_and_metric_footprints_supported')
            regions.append((mask,candidate))
        if len(regions)==len(seeds) and separated_instances(regions,edge_m) and sum(m.sum() for m,_ in regions) >= component.sum()*.80:
            return regions
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=max(5, int(short_side*.22)),
        minLineLength=max(5, int(short_side*.30)), maxLineGap=max(1, int(short_side*.12)))
    local_lines = cv2.createLineSegmentDetector(0).detect(gray)[0]
    color_lines = cv2.createLineSegmentDetector(0).detect(channel_image)[0]
    available = [a.reshape(-1,4) for a in (local_lines,color_lines,lines) if a is not None]
    if not available:
        return [(component, parent)]
    lines = np.concatenate(available)
    lengths = np.linalg.norm(lines[:,2:]-lines[:,:2],axis=1)
    lines = lines[np.argsort(-lengths)]
    ly, lx = np.where(local)
    grid_y,grid_x=np.indices(local.shape)
    edge_domain=cv2.dilate(local.astype(np.uint8),np.ones((3,3),np.uint8))>0
    solutions = []
    cut_proposals=[]
    edge_m = parent.get('nominal_edge_m')
    for line in lines[:64]:
        if budget[0] <= 0:
            break
        budget[0] -= 1
        x1, y1, x2, y2 = map(float, line)
        dx, dy = x2-x1, y2-y1
        length = np.hypot(dx, dy)
        if length < 1:
            continue
        distance = ((lx-x1)*dy - (ly-y1)*dx)/length
        # Interior chord evidence, not just a line on the silhouette.
        chord_distance=((grid_x-x1)*dy-(grid_y-y1)*dx)/length
        # A real dark seam can be absent from the color mask. Its edge is
        # evidence even when it lies in the one-pixel gap between regions.
        near = (np.abs(chord_distance) <= 1.25)&edge_domain
        if near.sum() < short_side * .5:
            continue
        edge_support = np.mean(edges[near] > 0)
        if edge_support < .20:
            continue
        side = distance >= 0
        if min(side.sum(), (~side).sum()) < len(lx)*.15:
            continue
        masks=[]
        for selection in (side, ~side):
            mask = np.zeros_like(component)
            mask[ly[selection]+y, lx[selection]+x] = True
            masks.append(mask)
        children=[assess(m) for m in masks]
        if edge_m is not None and any(c['footprint_size_m'] is None or
                np.any(np.asarray(c.get('footprint_raw_size_m',c['footprint_size_m']))+
                       2*np.asarray(c.get('footprint_sampling_half_extent_m',[0.,0.]))<.75*edge_m) or
                c.get('footprint_fill_ratio',0)<.72 for c in children):
            continue
        # Rank all observable cuts before recursive search. Otherwise a long
        # diagonal texture edge can consume the entire shared budget before
        # the straight, rectangular split is visited.
        rectangularity=min(c.get('footprint_fill_ratio',0) for c in children)
        balance=min(m.sum() for m in masks)/max(m.sum() for m in masks)
        quality=(rectangularity,balance,edge_support)
        cut_proposals.append((quality,edge_support,masks,children,[x1+x,y1+y,x2+x,y2+y]))
    for _,edge_support,masks,children,cut_line in sorted(cut_proposals,key=lambda v:v[0],reverse=True)[:4]:
        parts=[]
        for mask,child in zip(masks,children):
            if child['status']=='SINGLE_CUBE_CANDIDATE':
                parts.append((mask,child))
            else:
                parts.extend(_split_local(rgb,mask,assess,max_depth=max_depth-1,budget=budget,evidence_mode=evidence_mode))
        if not all(c['status'] == 'SINGLE_CUBE_CANDIDATE' and
                   (edge_m is None or (plausible_footprint(c,edge_m) and
                    c.get('footprint_fill_ratio',0)>=.72))
                   for _, c in parts):
            continue
        if not separated_instances(parts,edge_m):
            continue
        # A bounded depth and physical checks avoid unlimited texture slicing.
        solutions.append((edge_support, parts, cut_line))
    if not solutions:
        parent['split_search']={'budget_exhausted':budget[0]<=0,'valid_solutions':0,
                               'marker_seeds':len(seeds),'line_proposals':len(lines)}
        return [(component, parent)]
    solutions.sort(key=lambda item:(np.mean([cube_geometry_error(c,edge_m) for _,c in item[1]])
                                   if edge_m is not None else 0.,-item[0]))
    _, parts, line = solutions[0]
    # Different object counts from supported cuts are contradictory evidence.
    if len({len(parts) for _, parts, _ in solutions}) > 1:
        parent['reason'] = 'contradictory_seam_partitions'
        return [(component, parent)]
    for _, candidate in parts:
        candidate.update(reason='visible_rgb_seam_and_metric_footprints_supported',
                         split_evidence_line_uv=line)
    return parts
