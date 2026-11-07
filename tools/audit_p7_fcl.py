"""Read-only FCL audit of hash-locked P7 meshes at synthetic model poses.

No SDK imports or devices. No exclusions; report mesh intersections as model data.
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
    results=[]
    for q in ([0.]*7,[.2,.3,-.1,.2,.1,-.2,.15]):
        mapped=mapping.map_positions(dict(zip(mapping.joint_names,q)),source_model_version=c['source_model_sha256'],target_model_version=c['target_model_sha256'])
        poses={}
        for i in range(1,9):
            names=mapping.joint_names[:min(i,7)]
            tf,_=urdf_forward_kinematics(root/'arm.urdf',{n:mapped[n] for n in names},base_frame='L_arm_root',tip_frame=f'L{i}_Link')
            poses[f'L{i}_Link']=tf
        row=checker.check_poses(poses,exclusions={},min_clearance_m=0.)
        row['q_sdk_rad']=q;results.append(row)
    import importlib.metadata as meta
    report=dict(source='FCL_on_manufacturer_meshes_at_synthetic_model_poses',python_fcl=meta.version('python-fcl'),
                model_sha256=lock['urdf_sha256'],results=results,motion_enabled=False,
                missing=['hand','camera','torso','payload','environment','continuous articulated path','solid containment'])
    with args.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(python_fcl=report['python_fcl'],poses=len(results),surface_intersections=[sum(p['surface_intersection'] for p in r['pairs']) for r in results],motion_enabled=False)))


if __name__=='__main__':main()
