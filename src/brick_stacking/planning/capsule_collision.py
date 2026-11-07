"""Sampled capsule diagnostics for named, explicitly dimensioned geometry.

No mesh/full-robot or continuous clearance claim. UNKNOWN on sampled clearance;
FAIL on detected contact. Every endpoint is expressed in the declared frame.
"""
from dataclasses import dataclass
import math
import numpy as np
from brick_stacking.planning.joint_trajectory import sample_segment


def xyz(value):
    a=np.asarray(value,float)
    if a.shape!=(3,) or not np.isfinite(a).all(): raise ValueError('finite xyz required')
    return a


@dataclass(frozen=True)
class Capsule:
    name: str
    start_m: tuple
    end_m: tuple
    radius_m: float
    frame_id: str

    def __post_init__(self):
        if not self.name or not self.frame_id or not np.isfinite(self.radius_m) or self.radius_m<=0:
            raise ValueError('named frame and positive explicit radius required')
        object.__setattr__(self,'start_m',tuple(xyz(self.start_m)))
        object.__setattr__(self,'end_m',tuple(xyz(self.end_m)))


def segment_distance(a,b,c,d):
    """Euclidean closest distance for two closed segments, including points."""
    a,b,c,d=map(xyz,(a,b,c,d));u=b-a;v=d-c;w=a-c
    aa,bb,cc,dd,ee=u@u,u@v,v@v,u@w,v@w
    if aa<1e-20 and cc<1e-20: return float(np.linalg.norm(w))
    if aa<1e-20: s=0.;t=np.clip(ee/cc,0,1)
    elif cc<1e-20: t=0.;s=np.clip(-dd/aa,0,1)
    else:
        denom=aa*cc-bb*bb
        s=np.clip((bb*ee-cc*dd)/denom,0,1) if denom>1e-20 else 0.
        t=(bb*s+ee)/cc
        if t<0: t=0.;s=np.clip(-dd/aa,0,1)
        elif t>1: t=1.;s=np.clip((bb-dd)/aa,0,1)
    return float(np.linalg.norm(w+s*u-t*v))


def sampled_capsule_check(trajectory, geometry_at_q, obstacles, *, frame_id,
                          model_version, scene_version, collision_model_version,
                          sample_dt_s, self_exclusions, missing_coverage):
    """obstacles: named plane(normal,offset) free side n·x>=offset; or sphere.

    self_exclusions maps sorted (capsule_name,capsule_name) tuples to reasons.
    geometry_at_q returns Capsule objects with stable names at every sample.
    A failure is geometry-model contact, not proof of physical impact.
    """
    if not all(isinstance(x,str) and x for x in (frame_id,model_version,scene_version,collision_model_version)):
        raise ValueError('explicit frame and immutable versions required')
    if trajectory.get('model_version')!=model_version or trajectory.get('scene_version')!=scene_version:
        raise ValueError('stale model/scene')
    if trajectory.get('interpolation')!='quintic_stop_at_each_waypoint':
        raise ValueError('unsupported trajectory interpolation')
    if not np.isfinite(sample_dt_s) or sample_dt_s<=0 or not isinstance(missing_coverage,list):
        raise ValueError('positive sampling interval and explicit coverage list required')
    for pair,reason in self_exclusions.items():
        if not isinstance(pair,tuple) or len(pair)!=2 or pair[0]>=pair[1] or not reason:
            raise ValueError('named ordered self-pair exclusions need reasons')
    obstacles=tuple(obstacles);names=[o['name'] for o in obstacles]
    if len(names)!=len(set(names)) or any(not n for n in names): raise ValueError('unique obstacles required')
    for o in obstacles:
        if o.get('frame_id')!=frame_id: raise ValueError('obstacle frame mismatch')
        if o.get('type')=='plane':
            normal=xyz(o['normal'])
            if not np.isclose(np.linalg.norm(normal),1,atol=1e-8) or not np.isfinite(o['offset_m']):
                raise ValueError('unit plane normal and finite offset required')
        elif o.get('type')=='sphere':
            xyz(o['center_m'])
            if not np.isfinite(o['radius_m']) or o['radius_m']<=0: raise ValueError('explicit sphere radius required')
        else: raise ValueError('unsupported obstacle model')
    segments=trajectory.get('segments',[])
    if not segments: raise ValueError('nonempty trajectory required')
    total=sum(math.ceil(s['duration_s']/sample_dt_s)+1 for s in segments)
    if total>100000: raise ValueError('diagnostic sample budget exceeded')
    hits=[];minimum=math.inf;signature=None;count=0
    for index,segment in enumerate(segments):
        duration=segment['duration_s']
        for t in np.linspace(0,duration,math.ceil(duration/sample_dt_s)+1):
            q,_,_=sample_segment(segment,float(t));capsules=tuple(geometry_at_q(q));count+=1
            current=tuple(c.name for c in capsules)
            if not current or len(set(current))!=len(current): raise ValueError('nonempty uniquely named geometry required')
            if signature is None:
                signature=current
                if any(n not in signature for pair in self_exclusions for n in pair):
                    raise ValueError('exclusion refers to unknown geometry')
            if current!=signature or any(c.frame_id!=frame_id for c in capsules):
                raise ValueError('geometry topology/frame changed')
            def record(clearance,a,b):
                nonlocal minimum
                minimum=min(minimum,clearance)
                if clearance<=0:
                    hits.append(dict(segment=index,time_from_segment_start_s=float(t),first=a,second=b,clearance_m=clearance))
            for c in capsules:
                for o in obstacles:
                    if o['type']=='plane':
                        n=xyz(o['normal']);clearance=min(n@c.start_m,n@c.end_m)-o['offset_m']-c.radius_m
                    else:
                        clearance=segment_distance(c.start_m,c.end_m,o['center_m'],o['center_m'])-c.radius_m-o['radius_m']
                    record(float(clearance),c.name,o['name'])
            for i,a in enumerate(capsules):
                for b in capsules[i+1:]:
                    if tuple(sorted((a.name,b.name))) in self_exclusions: continue
                    clearance=segment_distance(a.start_m,a.end_m,b.start_m,b.end_m)-a.radius_m-b.radius_m
                    record(clearance,a.name,b.name)
            if hits: break
        if hits: break
    return dict(status='FAIL' if hits else 'UNKNOWN',sampled_status='FAIL' if hits else 'PASS',
                scope='named capsules at sampled quintic joint poses against static planes/spheres and self pairs',
                missing=list(missing_coverage)+['continuous motion between samples','unmodeled geometry and deformation'],
                model_version=collision_model_version,kinematic_model_version=model_version,
                scene_version=scene_version,samples_checked=count,sample_dt_s=sample_dt_s,
                min_sampled_clearance_m=minimum if np.isfinite(minimum) else None,
                coverage_names=list(signature),self_exclusions=[dict(pair=list(p),reason=r) for p,r in self_exclusions.items()],
                contacts=hits,full_collision='UNKNOWN',motion_enabled=False)
