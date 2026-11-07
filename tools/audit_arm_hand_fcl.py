"""Single-left-arm + O6 fixed-preset mesh audit. No device access.

All hand angles, arm path and clearance are synthetic diagnostic inputs.
The mechanical mount is sourced from a pinned vendor assembly, not a TCP.
"""
import argparse,hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.joint_conventions import JointConventionMap
from brick_stacking.localization.hand_kinematics import hand_link_poses
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.fcl_mesh import FclMeshChecker
from brick_stacking.planning.mesh_envelopes import stl_vertices
from brick_stacking.planning.obj_geometry import obj_triangles
from brick_stacking.planning.tool_assembly import attach_tool_poses
from brick_stacking.planning.vendor_exclusions import load_vendor_exclusions
from brick_stacking.planning.joint_trajectory import JointLimits,build_offline_trajectory


def load_meshes(root,urdf_file,expected):
    lock=json.loads((root/'asset_lock.json').read_text())
    if lock['urdf_sha256']!=expected or hashlib.sha256((root/urdf_file).read_bytes()).hexdigest()!=expected:raise ValueError('component version mismatch')
    meshes={}
    for item in lock['meshes']:
        name=item['path']
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe mesh path')
        raw=(root/name).read_bytes()
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('mesh lock mismatch')
        if name.endswith('.STL'):
            v=stl_vertices(raw);mesh=(v,np.arange(len(v),dtype=np.int32).reshape(-1,3));link=Path(name).stem
        else:mesh=obj_triangles(raw);link=item['link']
        meshes[link]=mesh
    return meshes


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('arm_directory','hand_directory','mapping','mount','output'):p.add_argument(name,type=Path)
    p.add_argument('--path',action='store_true');a=p.parse_args()
    c=json.loads(a.mapping.read_text(encoding='utf-8-sig'));mount=json.loads(a.mount.read_text())
    versions={item['path']:item['sha256'] for item in mount['verified_components']}
    arm_version=versions['arms/p7/variants/left/arm.urdf'];hand_version=versions['hands/linkerhand_o6/linkerhand_o6_left.urdf']
    if c['target_model_sha256']!=arm_version:raise ValueError('mapping/mount versions differ')
    meshes=load_meshes(a.arm_directory,'arm.urdf',arm_version)|load_meshes(a.hand_directory,'hand.urdf',hand_version)
    if len(meshes)!=20:raise ValueError('expected 20 left arm/hand meshes')
    convention=JointConventionMap(tuple(c['joint_names']),tuple(c['signs']),tuple(c['offsets_rad']),c['source_model_sha256'],arm_version)
    fixed=RigidTransform('L8_Link','lh_hand_base_link',mount['T_L8_hand_root'],'vendor_declared',mount['assembly_sha256'])
    arm_exclusions=load_vendor_exclusions(a.arm_directory/'arm.mjcf',expected_sha256='7e50f11c0dd488f557e95743163824a821f4522cf8403e99e8da6d284239c2e3',allowed_pairs=[(f'L{i}_Link',f'L{i+1}_Link') for i in range(1,8)])
    hand_root=ET.parse(a.hand_directory/'hand.urdf').getroot();adjacent=[(j.find('parent').get('link'),j.find('child').get('link')) for j in hand_root.findall('joint')]
    hand_exclusions=load_vendor_exclusions(a.hand_directory/'hand.xml',expected_sha256='3d0ca932028277620c234b984d2dd570fc9d8d82311db988e53ab4618485b643',allowed_pairs=adjacent+[('lh_hand_base_link','lh_thumb_metacarpals')])
    exclusions=arm_exclusions|hand_exclusions
    exclusions[('L8_Link','lh_hand_base_link')]='pinned vendor recipe installation seam; recipe sha256='+mount['recipe_sha256']
    active=[j.get('name') for j in hand_root.findall('joint') if j.find('mimic') is None]
    checker=FclMeshChecker(meshes,model_version=mount['assembly_sha256']);rows=[]
    def arm_poses(q):
        mapped=convention.map_positions(dict(zip(convention.joint_names,q)),source_model_version=c['source_model_sha256'],target_model_version=arm_version)
        return {f'L{i}_Link':urdf_forward_kinematics(a.arm_directory/'arm.urdf',{n:mapped[n] for n in convention.joint_names[:min(i,7)]},base_frame='L_arm_root',tip_frame=f'L{i}_Link')[0] for i in range(1,9)}
    for values in ([0.]*6,[.4,.2,.6,.6,.6,.6]):
        hand=hand_link_poses(a.hand_directory/'hand.urdf',dict(zip(active,values)),base_frame='lh_hand_base_link')
        hand['lh_hand_base_link']=RigidTransform('lh_hand_base_link','lh_hand_base_link',np.eye(4),'synthetic')
        def poses_at_q(q):
            poses=arm_poses(q);poses.update(attach_tool_poses(poses['L8_Link'],fixed,hand));return poses
        row=checker.check_poses(poses_at_q([0.]*7),exclusions=exclusions,min_clearance_m=0.)
        row['synthetic_hand_rad']=dict(zip(active,values))
        if a.path:
            limits=JointLimits(convention.joint_names,(-1.,)*7,(1.,)*7,(.2,)*7,(.3,)*7,c['source_model_sha256'],'synthetic')
            trajectory=build_offline_trajectory([[0.]*7,[.2,.3,-.1,.2,.1,-.2,.15]],limits,scene_version='synthetic-left-arm-hand-only',calibration_version='synthetic',clock_domain='mock',epoch='1',state_stamp_s=1,now_s=1,max_age_s=.1,start_tolerance_rad=.001,expected_start_rad=[0.]*7)
            row['path']=checker.check_trajectory(trajectory,poses_at_q,source_model_version=limits.model_version,scene_version=trajectory['scene_version'],exclusions=exclusions,min_clearance_m=0.,sample_dt_s=.05,missing_coverage=['torso','camera','payload','environment','physical preset mapping'])
        rows.append(row)
    result=dict(source='manufacturer_left_arm_hand_at_synthetic_joint_poses_not_hardware',mount_commit=mount['commit'],assembly_sha256=mount['assembly_sha256'],mesh_count=len(meshes),results=rows,motion_enabled=False)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(mesh_count=20,surface_intersections=[sum(p['surface_intersection'] for p in r['pairs']) for r in rows],path_status=[r.get('path',{}).get('sampled_status') for r in rows])))


if __name__=='__main__':main()
