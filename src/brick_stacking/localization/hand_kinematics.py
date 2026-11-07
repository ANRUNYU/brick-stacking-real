"""Explicit hand mimic expansion. No raw_u8/percent-to-rad assumptions."""
import xml.etree.ElementTree as ET
import numpy as np
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics


def resolve_hand_joints(path,actuated_rad):
    root=ET.parse(path).getroot()
    joints={j.get('name'):j for j in root.findall('joint') if j.get('type')=='revolute'}
    active={n for n,j in joints.items() if j.find('mimic') is None}
    if set(actuated_rad)!=active: raise ValueError('exact named actuated rad values required')
    resolved={};visiting=set()
    def resolve(name):
        if name in resolved:return resolved[name]
        if name not in joints or name in visiting: raise ValueError('unknown/cyclic mimic reference')
        visiting.add(name);j=joints[name];m=j.find('mimic')
        value=actuated_rad[name] if m is None else float(m.get('multiplier','1'))*resolve(m.get('joint'))+float(m.get('offset','0'))
        limit=j.find('limit')
        if not np.isscalar(value) or not np.isfinite(value) or limit is None: raise ValueError('finite angle and declared limits required')
        lo,hi=float(limit.get('lower')),float(limit.get('upper'))
        if not np.isfinite([lo,hi]).all() or lo>hi or not lo<=value<=hi: raise ValueError('hand joint limit: '+name)
        visiting.remove(name);resolved[name]=float(value);return float(value)
    for name in joints:resolve(name)
    return resolved


def hand_link_poses(path,actuated_rad,*,base_frame):
    """All child-link transforms, including coupled distal fingers; unapproved."""
    resolved=resolve_hand_joints(path,actuated_rad);root=ET.parse(path).getroot()
    parents={j.find('child').get('link'):j for j in root.findall('joint')}
    poses={}
    for tip in parents:
        node=tip;seen=set();names=[]
        while node!=base_frame:
            if node not in parents or node in seen: raise ValueError('hand link tree disconnected/cyclic')
            seen.add(node);j=parents[node]
            if j.get('type')=='revolute':names.append(j.get('name'))
            elif j.get('type')!='fixed':raise ValueError('unsupported hand joint')
            node=j.find('parent').get('link')
        poses[tip]=urdf_forward_kinematics(path,{n:resolved[n] for n in names},base_frame=base_frame,tip_frame=tip,resolved_mimic=True)[0]
    return poses
