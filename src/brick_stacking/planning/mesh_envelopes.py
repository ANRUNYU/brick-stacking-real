"""Binary STL parsing and conservative capsule envelopes, numpy only.

The convex capsule contains all input vertices and therefore their triangles.
This is an enclosing proxy, not mesh contact or measured physical coverage.
"""
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import numpy as np
from brick_stacking.planning.capsule_collision import Capsule


def stl_vertices(data):
    if len(data)<84: raise ValueError('binary STL header missing')
    n=struct.unpack_from('<I',data,80)[0]
    if n<1 or n>1_000_000 or len(data)!=84+50*n: raise ValueError('invalid or unsupported binary STL length')
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    vertices=np.frombuffer(data,dtype=dtype,count=n,offset=84)['vertices'].reshape(-1,3).astype(float)
    if not np.isfinite(vertices).all(): raise ValueError('nonfinite mesh')
    return vertices


def capsule_envelope(name,vertices,*,frame_id,padding_m):
    points=np.asarray(vertices,float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<3 or not np.isfinite(points).all():
        raise ValueError('finite mesh vertices required')
    if not np.isfinite(padding_m) or padding_m<0: raise ValueError('explicit nonnegative padding required')
    center=points.mean(0);x=points-center
    _,axes=np.linalg.eigh(x.T@x);axis=axes[:,-1]
    projection=x@axis
    radial=x-projection[:,None]*axis
    radius=float(np.max(np.linalg.norm(radial,axis=1)))+padding_m
    if radius<=0: raise ValueError('degenerate zero-radius mesh')
    return Capsule(name,tuple(center+axis*projection.min()),tuple(center+axis*projection.max()),radius,frame_id)


def load_p7_capsule_envelopes(directory,*,padding_m):
    directory=Path(directory);lock=json.loads((directory/'asset_lock.json').read_text(encoding='utf-8'))
    raw=(directory/'arm.urdf').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=lock['urdf_sha256']: raise ValueError('URDF checksum mismatch')
    expected={m['path']:m for m in lock['meshes']}
    proxies=[];details=[];used=set()
    for link in ET.fromstring(raw).findall('link'):
        vertices=[]
        for collision in link.findall('collision'):
            origin=collision.find('origin')
            # This bounded adapter supports the audited identity mesh placements.
            if origin is not None and any(float(v)!=0 for k in ('xyz','rpy') for v in origin.get(k,'0 0 0').split()):
                raise ValueError('nonidentity collision origin requires an explicit transform adapter')
            geometry=collision.find('geometry')
            if geometry is None or len(geometry)!=1 or geometry[0].tag!='mesh': raise ValueError('unsupported collision geometry')
            mesh=geometry[0];name=mesh.get('filename')
            if name not in expected or Path(name).is_absolute() or '..' in Path(name).parts: raise ValueError('unlocked mesh path')
            if any(float(v)!=1 for v in mesh.get('scale','1 1 1').split()): raise ValueError('non-unit mesh scale')
            data=(directory/name).read_bytes();entry=expected[name]
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']: raise ValueError('mesh checksum mismatch')
            vertices.append(stl_vertices(data));used.add(name)
        if vertices:
            p=np.vstack(vertices);proxy=capsule_envelope(link.get('name'),p,frame_id=link.get('name'),padding_m=padding_m)
            proxies.append(proxy);details.append(dict(link=link.get('name'),vertices=len(p),radius_m=proxy.radius_m,start_m=proxy.start_m,end_m=proxy.end_m))
    if used!=set(expected) or not proxies: raise ValueError('incomplete mesh/model coverage')
    return proxies,dict(source='hashed_manufacturer_collision_mesh_envelope',urdf_sha256=lock['urdf_sha256'],links=details,
                        padding_m=padding_m,approved_for_motion=False,missing=['hand','camera','torso','payload','environment','continuous collision'])
