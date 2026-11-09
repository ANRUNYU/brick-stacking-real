"""Cartesian translation-only offline diagnostics, never a motion permit.

Coverage: swept axis-aligned tool/payload envelope versus supplied static AABBs.
Missing: articulated arm, orientation changes, cables, meshes, dynamics, uncertainty.
"""
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.calibration import tcp_target_for_block


def _xyz(value, positive=False):
    a=np.asarray(value,float)
    if a.shape!=(3,) or not np.isfinite(a).all() or (positive and np.any(a<=0)):
        raise ValueError('finite xyz (positive extents) required')
    return a


def swept_aabb_hit(start, end, half_extent, lower, upper):
    """Exact slab intersection for translating fixed AABB, inclusive contact."""
    a,b,h,lo,hi=(_xyz(start),_xyz(end),_xyz(half_extent,True),_xyz(lower),_xyz(upper))
    if np.any(lo>=hi): raise ValueError('invalid obstacle bounds')
    lo,hi=lo-h,hi+h
    enter,leave=0.,1.
    for i in range(3):
        delta=b[i]-a[i]
        if abs(delta)<1e-15:
            if a[i]<lo[i] or a[i]>hi[i]: return False
        else:
            t0,t1=sorted(((lo[i]-a[i])/delta,(hi[i]-a[i])/delta))
            enter,leave=max(enter,t0),min(leave,t1)
            if enter>leave: return False
    return True


def offline_pick_place(world_pick, world_place, tcp_block, *, clearance_m, half_extent_m, obstacles, scene_version):
    """Pick/place are block poses; clearance along caller's world +Z.

    Requires same orientation; no default dimensions, arm side or clearance.
    First approach starts above pick, not at an unknown current robot pose.
    obstacles: iterable of (name, lower_m, upper_m) in world target frame.
    """
    if not scene_version or not np.isfinite(clearance_m) or clearance_m<=0:
        raise ValueError('version and positive measured/configured clearance required')
    if world_pick.target_frame!=world_place.target_frame:
        raise ValueError('world frame mismatch')
    pick=tcp_target_for_block(world_pick,tcp_block)
    place=tcp_target_for_block(world_place,tcp_block)
    if not np.allclose(pick.matrix[:3,:3],place.matrix[:3,:3],atol=1e-8):
        raise ValueError('rotation changes unsupported by this collision model')
    h=_xyz(half_extent_m,True)
    p,q=pick.matrix[:3,3],place.matrix[:3,3]
    lift=np.array([0,0,clearance_m])
    points=[p+lift,p,p+lift,q+lift,q,q+lift]
    names=['approach','grasp','lift','transfer','release','retreat']
    hits=[]
    obstacles=tuple(obstacles)
    for i,(a,b) in enumerate(zip(points,points[1:])):
        for name,lo,hi in obstacles:
            if swept_aabb_hit(a,b,h,lo,hi): hits.append({'segment':i,'obstacle':name})
    return {'source':'synthetic_or_offline','scene_version':scene_version,
            'waypoints':[{'phase':n,'tcp_position_m':p.tolist()} for n,p in zip(names,points)],
            'ik':'UNKNOWN','joint_trajectory':'NOT_GENERATED',
            'collision_aabb':'FAIL' if hits else 'PASS', 'collisions':hits,
            'full_collision':'UNKNOWN','motion_enabled':False,
            'missing':['current-to-approach path','arm links','camera/cables unless supplied',
                       'contact exemptions','orientation sweep','hardware validation']}
