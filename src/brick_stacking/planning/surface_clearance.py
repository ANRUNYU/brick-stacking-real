"""Conservative continuous triangle-surface clearance certificate.

For fixed-base revolute chains, point speed <= sum |qdot_j|*radius_to_axis_bound.
Triangle-surface distance is Lipschitz with sum of both surface speed bounds.
This does not certify solids, physical model coverage, or execution permission.
"""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


def surface_speed_bounds(urdf_path,vertices_by_link,trajectory):
    if trajectory.get('interpolation')!='quintic_stop_at_each_waypoint': raise ValueError('unsupported interpolation')
    names=trajectory['joint_names'];speed={n:0. for n in names}
    if len(set(names))!=len(names): raise ValueError('unique named joints required')
    for s in trajectory['segments']:
        a,b=np.asarray(s['start_rad'],float),np.asarray(s['end_rad'],float);duration=s['duration_s']
        if a.shape!=(len(names),) or b.shape!=a.shape or not np.isfinite([a,b]).all() or not np.isfinite(duration) or duration<=0:
            raise ValueError('invalid quintic segment')
        for n,v in zip(names,1.875*np.abs(b-a)/duration): speed[n]=max(speed[n],float(v))
    path=Path(urdf_path);root=ET.fromstring(path.read_bytes());parents={}
    for j in root.findall('joint'):
        child=j.find('child').get('link')
        if child in parents: raise ValueError('multiple parents')
        parents[child]=j
    bounds={}
    for link,vertices in vertices_by_link.items():
        v=np.asarray(vertices,float)
        if v.ndim!=2 or v.shape[1]!=3 or not len(v) or not np.isfinite(v).all(): raise ValueError('finite vertices required')
        radius=float(np.max(np.linalg.norm(v,axis=1)));bound=0.;node=link;visited=set()
        while node in parents:
            if node in visited: raise ValueError('cyclic model')
            visited.add(node);j=parents[node];kind=j.get('type')
            if kind=='revolute':
                if j.get('name') not in speed: raise ValueError('missing joint rate')
                axis=np.array([float(x) for x in j.find('axis').get('xyz').split()])
                if not np.isclose(np.linalg.norm(axis),1): raise ValueError('unit axis required')
                bound+=speed[j.get('name')]*radius
            elif kind!='fixed': raise ValueError('only fixed-base revolute chain supported')
            origin=j.find('origin')
            offset=np.array([float(x) for x in origin.get('xyz','0 0 0').split()]) if origin is not None else np.zeros(3)
            if offset.shape!=(3,) or not np.isfinite(offset).all(): raise ValueError('invalid origin')
            radius+=float(np.linalg.norm(offset));node=j.find('parent').get('link')
        bounds[link]=bound
    return dict(method='revolute_chain_triangle_inequality_quintic_analytic_max_velocity',
                urdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),surface_speed_m_s=bounds,
                assumptions=['fixed base','rigid meshes in link frames','unit revolute axes','declared quintic interpolation'])


def certify_surface_intervals(sampled,bounds,*,clearance_margin_m):
    if not np.isfinite(clearance_margin_m) or clearance_margin_m<0: raise ValueError('explicit nonnegative margin required')
    if not bounds.get('urdf_sha256') or sampled.get('model_version')!=bounds['urdf_sha256']:
        raise ValueError('surface-speed model version mismatch')
    coverage=sampled.get('coverage_names',[]);rates=bounds['surface_speed_m_s']
    if not coverage or set(coverage)!=set(rates) or any(not np.isfinite(v) or v<0 for v in rates.values()):
        raise ValueError('complete named speed bounds required')
    checks=sampled['checks'];gaps=[]
    for segment in {c['segment'] for c in checks}:
        times=[c['time_from_segment_start_s'] for c in checks if c['segment']==segment]
        if len(times)<2: return dict(continuous_surface_status='UNKNOWN',reason='insufficient interval samples',motion_enabled=False)
        delta=np.diff(times)
        if np.any(delta<=0): raise ValueError('strictly ordered samples required')
        gaps.extend(delta.tolist())
    pair_rate=sum(sorted(rates.values(),reverse=True)[:2])
    max_gap=max(gaps) if gaps else None
    distance=sampled.get('min_sampled_distance_m')
    deduction=pair_rate*max_gap/2 if max_gap is not None else None
    lower_bound=distance-deduction if distance is not None and deduction is not None else None
    passes=sampled['sampled_status']=='PASS' and lower_bound is not None and lower_bound>clearance_margin_m
    return dict(continuous_surface_status='PASS' if passes else 'UNKNOWN',
                conservative_surface_distance_lower_bound_m=lower_bound,max_pair_surface_speed_m_s=pair_rate,
                max_sample_gap_s=max_gap,clearance_margin_m=clearance_margin_m,
                reason='conditional on supplied model speed bounds; not solid/physical collision approval',
                full_collision='UNKNOWN',motion_enabled=False)
