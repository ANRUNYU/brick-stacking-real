"""Read-only URDF FK adapter. Declared model geometry is never measured calibration."""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from brick_stacking.hardware.urdf_inspection import inspect_urdf
from brick_stacking.localization.forward_kinematics import RevoluteJoint, forward_kinematics
from brick_stacking.localization.rigid_transforms import RigidTransform


def _triple(text):
    a=np.asarray([float(v) for v in text.split()])
    if a.shape!=(3,) or not np.isfinite(a).all(): raise ValueError('finite URDF xyz/rpy required')
    return a


def urdf_forward_kinematics(path, positions_rad, *, base_frame, tip_frame, resolved_mimic=False):
    """Inputs use URDF joint names, without guessing J1/SDK/CAN correspondence.

    Supports explicit base-to-tip fixed/revolute paths only. Fixed joints need
    no q entry; exactly the revolute names are required. RPY = Rz(yaw)Ry(pitch)Rx(roll).
    """
    path=Path(path)
    version=hashlib.sha256(path.read_bytes()).hexdigest()
    audit=inspect_urdf(path)
    root=ET.fromstring(path.read_text(encoding='utf-8'))
    children={}
    for joint in root.findall('joint'):
        child=joint.find('child');parent=joint.find('parent')
        if child is None or parent is None: raise ValueError('missing link relationship')
        name=child.get('link')
        if name in children: raise ValueError('multiple parents')
        children[name]=joint
    chain=[];node=tip_frame;visited=set()
    while node!=base_frame:
        if node in visited or node not in children: raise ValueError('no acyclic base-to-tip chain')
        visited.add(node);joint=children[node];chain.append(joint)
        node=joint.find('parent').get('link')
    chain.reverse()
    names=[j.get('name') for j in chain if j.get('type')=='revolute']
    if len(names)!=len(set(names)) or set(positions_rad)!=set(names): raise ValueError('exact URDF joint mapping required')
    if not chain: raise ValueError('nonempty chain required')
    result=None
    for j in chain:
        kind=j.get('type')
        if kind not in ('fixed','revolute'): raise ValueError('unsupported joint type')
        mimic=j.find('mimic')
        if mimic is not None:
            if not resolved_mimic: raise ValueError('unresolved mimic joint')
            master=mimic.get('joint')
            if master not in positions_rad: raise ValueError('mimic master not in chain')
            expected=float(mimic.get('multiplier','1'))*positions_rad[master]+float(mimic.get('offset','0'))
            if not np.isfinite(expected) or not np.isclose(positions_rad[j.get('name')],expected,atol=1e-10,rtol=0):
                raise ValueError('resolved mimic value inconsistent')
        origin=j.find('origin')
        xyz=_triple(origin.get('xyz','0 0 0') if origin is not None else '0 0 0')
        r,p,y=_triple(origin.get('rpy','0 0 0') if origin is not None else '0 0 0')
        cr,sr,cp,sp,cy,sy=np.cos(r),np.sin(r),np.cos(p),np.sin(p),np.cos(y),np.sin(y)
        rx=np.array([[1,0,0],[0,cr,-sr],[0,sr,cr]])
        ry=np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]])
        rz=np.array([[cy,-sy,0],[sy,cy,0],[0,0,1]])
        m=np.eye(4);m[:3,:3]=rz@ry@rx;m[:3,3]=xyz
        t=RigidTransform(j.find('parent').get('link'),j.find('child').get('link'),m,'urdf_declared',version)
        if kind=='revolute':
            axis=j.find('axis')
            if axis is None: raise ValueError('explicit axis required for this adapter')
            single=RevoluteJoint(j.get('name'),t,tuple(_triple(axis.get('xyz',''))))
            t=forward_kinematics([single],{single.name:positions_rad[single.name]},model_version=version)
        result=t if result is None else result.compose(t)
    return result, {'model_sha256':version,'inspection':audit,'base_frame':base_frame,
                    'tip_frame':tip_frame,'joint_names':names,'hardware_match_verified':False,
                    'collision_geometry_count':len(root.findall('link/collision')),
                    'motion_enabled':False}
