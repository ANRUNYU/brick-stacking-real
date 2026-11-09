"""Read-only FCL audit of hash-locked P7 meshes at synthetic model poses.

No SDK imports or devices. Optional hash-locked vendor installation exclusions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from brick_stacking.localization.joint_conventions import JointConventionMap
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.mesh_envelopes import stl_vertices
from brick_stacking.planning.fcl_mesh import FclMeshChecker


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('directory',type=Path);p.add_argument('mapping',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--vendor-exclusions',type=Path)
    p.add_argument('--exclusions-sha256')
    p.add_argument('--sample-dt-s',type=float,default=.05)
    p.add_argument('--path',action='store_true',help='also sample a synthetic joint path')
    args=p.parse_args();root=args.directory
    lock=json.loads((root/'asset_lock.json').read_text());c=json.loads(args.mapping.read_text(encoding='utf-8-sig'))
    if hashlib.sha256((root/'arm.urdf').read_bytes()).hexdigest()!=lock['urdf_sha256'] or lock['urdf_sha256']!=c['target_model_sha256']:
        raise ValueError('model lock mismatch')
    mapping=JointConventionMap(tuple(c['joint_names']),tuple(c['signs']),tuple(c['offsets_rad']),c['source_model_sha256'],c['target_model_sha256'])
    meshes={}
    for index,entry in enumerate(lock['meshes'],1):
        # Audited P7 layout only, reject any renamed/reordered reference.
        if entry['path']!=f'meshes/L{index}_Link.STL': raise ValueError('unexpected locked mesh ordering')
        raw=(root/entry['path']).read_bytes()
        if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']: raise ValueError('mesh lock mismatch')
        v=stl_vertices(raw);meshes[f'L{index}_Link']=(v,np.arange(len(v),dtype=np.int32).reshape(-1,3))
    checker=FclMeshChecker(meshes,model_version=lock['urdf_sha256'])
    exclusions={}
    if args.vendor_exclusions:
        from brick_stacking.planning.vendor_exclusions import load_vendor_exclusions
        exclusions=load_vendor_exclusions(args.vendor_exclusions,expected_sha256=args.exclusions_sha256,allowed_pairs=[(f'L{i}_Link',f'L{i+1}_Link') for i in range(1,8)])
    def poses_at_q(q):
        mapped=mapping.map_positions(dict(zip(mapping.joint_names,q)),source_model_version=c['source_model_sha256'],target_model_version=c['target_model_sha256'])
        poses={}
        for i in range(1,9):
            names=mapping.joint_names[:min(i,7)]
            tf,_=urdf_forward_kinematics(root/'arm.urdf',{n:mapped[n] for n in names},base_frame='L_arm_root',tip_frame=f'L{i}_Link')
            poses[f'L{i}_Link']=tf
        return poses
    results=[]
    for q in ([0.]*7,[.2,.3,-.1,.2,.1,-.2,.15]):
        row=checker.check_poses(poses_at_q(q),exclusions=exclusions,min_clearance_m=0.)
        row['q_sdk_rad']=q;results.append(row)
    import importlib.metadata as meta
    report=dict(source='FCL_on_manufacturer_meshes_at_synthetic_model_poses',python_fcl=meta.version('python-fcl'),
                model_sha256=lock['urdf_sha256'],results=results,motion_enabled=False,
                missing=['hand','camera','torso','payload','environment','continuous articulated path','solid containment'])
    if args.path:
        from brick_stacking.planning.joint_trajectory import JointLimits,build_offline_trajectory
        # Explicit synthetic diagnostic limits/rates, NOT measured control limits.
        limits=JointLimits(mapping.joint_names,(-1.,)*7,(1.,)*7,(.2,)*7,(.3,)*7,c['source_model_sha256'],'synthetic')
        trajectory=build_offline_trajectory([[0.]*7,[.2,.3,-.1,.2,.1,-.2,.15]],limits,
            scene_version='synthetic-arm-only',calibration_version='synthetic',clock_domain='mock',epoch='1',
            state_stamp_s=1,now_s=1,max_age_s=.1,start_tolerance_rad=.001,expected_start_rad=[0.]*7)
        report['path_check']=checker.check_trajectory(trajectory,poses_at_q,source_model_version=limits.model_version,
            scene_version=trajectory['scene_version'],exclusions=exclusions,min_clearance_m=0.,sample_dt_s=args.sample_dt_s,
            missing_coverage=report['missing'])
        from brick_stacking.planning.surface_clearance import surface_speed_bounds,certify_surface_intervals
        speed_bounds=surface_speed_bounds(root/'arm.urdf',{n:v for n,(v,t) in meshes.items()},trajectory)
        report['surface_speed_bounds']=speed_bounds
        report['continuous_surface_certificate']=certify_surface_intervals(report['path_check'],speed_bounds,clearance_margin_m=0.)
    with args.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(python_fcl=report['python_fcl'],poses=len(results),surface_intersections=[sum(p['surface_intersection'] for p in r['pairs']) for r in results],motion_enabled=False)))


if __name__=='__main__':main()
