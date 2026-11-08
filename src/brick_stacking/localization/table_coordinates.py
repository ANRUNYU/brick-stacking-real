"""Observed table coordinates and a resting-cube geometric representative.

An unmarked cube has equivalent face-axis choices. No robot-base transform is
inferred from a table plane, a known edge length or an arbitrary pixel origin.
"""
import numpy as np
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.rigid_transforms import RigidTransform


def table_coordinates(plane,origin_ray,*,camera_frame,table_frame,version):
    n=np.asarray(plane.normal,float);ray=np.asarray(origin_ray,float)
    if n.shape!=(3,) or ray.shape!=(3,) or not np.isfinite(np.r_[n,ray,plane.offset_m]).all() or not np.isclose(n@n,1.,atol=1e-8) or ray[2]<=0:
        raise ValueError('finite unit table normal and explicit optical ray required')
    denominator=n@ray
    if abs(denominator)<1e-8:raise ValueError('table origin ray is grazing')
    origin=-plane.offset_m/denominator*ray
    if origin[2]<=0:raise ValueError('table origin behind camera')
    x=np.array([1.,0.,0.])-n*n[0]
    if np.linalg.norm(x)<1e-8:raise ValueError('camera X projection degenerate; choose another explicit convention')
    x/=np.linalg.norm(x);y=np.cross(n,x)
    matrix=np.eye(4);matrix[:3,:3]=np.column_stack((x,y,n));matrix[:3,3]=origin
    return RigidTransform(camera_frame,table_frame,matrix,'observed_table_geometry',version)


def resting_cube_geometry(plane,corners_uv,k,*,edge_m,camera_frame,block_frame,version,rests_on_table):
    corners=np.asarray(corners_uv,float)
    if rests_on_table is not True or corners.shape!=(4,2) or not np.isfinite(corners).all() or not np.isfinite(edge_m) or edge_m<=0:
        raise ValueError('explicit resting-cube hypothesis, four ordered top corners and positive measured edge required')
    n=np.asarray(plane.normal,float)
    if not np.isclose(n@n,1.,atol=1e-8):raise ValueError('unit table normal required')
    rays=backproject(corners,np.ones(4),k);denominator=rays@n
    if np.any(np.abs(denominator)<1e-8):raise ValueError('grazing top rays')
    vertices=rays*((edge_m-plane.offset_m)/denominator)[:,None]
    if np.any(vertices[:,2]<=0):raise ValueError('top intersections behind camera')
    edges=np.roll(vertices,-1,axis=0)-vertices;lengths=np.linalg.norm(edges,axis=1)
    if np.any(lengths<1e-8):raise ValueError('degenerate top corners')
    turn=np.cross(edges,np.roll(edges,-1,axis=0))@n
    if not (np.all(turn>1e-12) or np.all(turn< -1e-12)):raise ValueError('ordered convex top corners required')
    x=edges[0]-edges[2];x-=n*(x@n);x/=np.linalg.norm(x)
    y=np.cross(n,x);matrix=np.eye(4);matrix[:3,:3]=np.column_stack((x,y,n))
    surface=vertices.mean(0);matrix[:3,3]=surface-n*edge_m/2
    transform=RigidTransform(camera_frame,block_frame,matrix,'resting_cube_geometry_candidate',version)
    return transform,dict(top_center_camera_m=surface.tolist(),top_vertices_camera_m=vertices.tolist(),
                           observed_corner_edges_m=lengths.tolist(),edge_errors_m=(lengths-edge_m).tolist(),
                           adjacent_edge_abs_cos=float(np.max(np.abs(np.sum(edges*np.roll(edges,-1,axis=0),axis=1)/(lengths*np.roll(lengths,-1))))),
                           orientation_semantics='one geometric representative; unmarked resting cube yaw is equivalent modulo pi/2',
                           assumptions=['cube rests flat on fitted table','edge is measured','manual RGB corners identify top boundary'],
                           base_transform=None,approved=False,motion_enabled=False)
