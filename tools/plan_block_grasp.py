"""Generate desired cube face-grasp frames, not executable robot targets."""
import argparse
import json
from pathlib import Path
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.block_grasps import cube_face_grasps


def plan(data):
    for key in ('world_frame','block_frame','geometry_version','edge_source','pose_source'):
        if not isinstance(data.get(key),str) or not data[key]:raise ValueError('explicit provenance required: '+key)
    if data.get('units')!='m' or data.get('source') not in ('synthetic','recorded','real'):
        raise ValueError('source and metre units required')
    block=RigidTransform(data['world_frame'],data['block_frame'],data['T_world_block'],data['pose_source'],
                         stamp_s=data.get('stamp_s'),clock_domain=data.get('clock_domain'))
    report=cube_face_grasps(block,edge_m=data['edge_m'],finger_side_clearance_m=data['finger_side_clearance_m'],
                approach_world=data['approach_world'],pregrasp_distance_m=data['pregrasp_distance_m'],geometry_version=data['geometry_version'])
    for row in report['candidates']:
        for name in ('target','pregrasp'):
            t=row[name];row[name]=dict(target_frame=t.target_frame,source_frame=t.source_frame,matrix=t.matrix.tolist(),approved=False)
    report.update(schema_version='c-cube-face-grasps-1',source=data['source'],edge_source=data['edge_source'],
                  pose_source=data['pose_source'],target_semantics='desired geometric grasp frame; not flange or measured TCP',motion_enabled=False)
    return report


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    r=plan(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
