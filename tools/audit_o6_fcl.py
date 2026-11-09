"""Hash-locked O6 candidate self-collision audit at synthetic radian poses.

Not a hand preset, raw control mapping, arm-hand installation or hardware test.
"""
import argparse,hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.hand_kinematics import hand_link_poses,resolve_hand_joints
from brick_stacking.planning.obj_geometry import obj_triangles
from brick_stacking.planning.fcl_mesh import FclMeshChecker
from brick_stacking.planning.vendor_exclusions import load_vendor_exclusions

MJCF_SHA='3d0ca932028277620c234b984d2dd570fc9d8d82311db988e53ab4618485b643'


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args();root=a.directory
    lock=json.loads((root/'asset_lock.json').read_text());raw=(root/'hand.urdf').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=lock['urdf_sha256']:raise ValueError('hand URDF lock mismatch')
    urdf=ET.fromstring(raw);meshes={};locked={m['link']:m for m in lock['meshes']}
    for link in urdf.findall('link'):
        name=link.get('name');collision=link.find('collision')
        if collision is None or len(link.findall('collision'))!=1:raise ValueError('expected one mesh per hand link')
        origin=collision.find('origin');mesh=collision.find('geometry/mesh')
        if mesh is None:raise ValueError('mesh required')
        if origin is not None and any(float(v)!=0 for k in ('xyz','rpy') for v in origin.get(k,'0 0 0').split()):raise ValueError('unhandled mesh placement')
        if any(float(v)!=1 for v in mesh.get('scale','1 1 1').split()):raise ValueError('unhandled scale')
        entry=locked[name];filename=entry['path']
        if filename!=mesh.get('filename') or '..' in Path(filename).parts or Path(filename).is_absolute():raise ValueError('mesh path mismatch')
        data=(root/filename).read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('mesh lock mismatch')
        meshes[name]=obj_triangles(data)
    if set(meshes)!=set(locked):raise ValueError('incomplete mesh coverage')
    adjacent=[(j.find('parent').get('link'),j.find('child').get('link')) for j in urdf.findall('joint')]
    # Additional palm-to-thumb-base seam explicitly declared in audited vendor XML.
    allowed=adjacent+[('lh_hand_base_link','lh_thumb_metacarpals')]
    exclusions=load_vendor_exclusions(root/'hand.xml',expected_sha256=MJCF_SHA,allowed_pairs=allowed)
    xml=ET.parse(root/'hand.xml').getroot();couplings={e.get('joint1'):e for e in xml.findall('.//equality/joint')}
    for j in urdf.findall('joint'):
        mimic=j.find('mimic')
        if mimic is not None:
            e=couplings[j.get('name')];coeff=[float(v) for v in e.get('polycoef').split()]
            if e.get('joint2')!=mimic.get('joint') or coeff!=[float(mimic.get('offset','0')),float(mimic.get('multiplier','1')),0,0,0]:raise ValueError('URDF/MJCF mimic discrepancy')
    active=[j.get('name') for j in urdf.findall('joint') if j.find('mimic') is None]
    checker=FclMeshChecker(meshes,model_version=lock['urdf_sha256']);results=[]
    for values in ([0.]*6,[.4,.2,.6,.6,.6,.6]):
        q=dict(zip(active,values));poses=hand_link_poses(root/'hand.urdf',q,base_frame='lh_hand_base_link')
        poses['lh_hand_base_link']=RigidTransform('lh_hand_base_link','lh_hand_base_link',np.eye(4),'synthetic_model_identity')
        row=checker.check_poses(poses,exclusions=exclusions,min_clearance_m=0.)
        row.update(actuated_rad=q,resolved_rad=resolve_hand_joints(root/'hand.urdf',q));results.append(row)
    report=dict(source='manufacturer_O6_candidate_at_synthetic_radian_poses_not_hardware',urdf_sha256=lock['urdf_sha256'],mjcf_sha256=MJCF_SHA,results=results,motion_enabled=False,missing=['raw-to-rad mapping','physical O6 version match','arm-hand mount','camera','payload','environment','continuous motion'])
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(poses=len(results),mesh_count=len(meshes),surface_intersections=[sum(p['surface_intersection'] for p in r['pairs']) for r in results])))


if __name__=='__main__':main()
