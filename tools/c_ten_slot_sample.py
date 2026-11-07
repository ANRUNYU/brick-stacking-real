"""Generate synthetic ten-slot release targets and trial-report input examples.

No hardware; no actual world/base calibration or grasp preset is asserted.
"""
import argparse,json
from dataclasses import asdict
from pathlib import Path
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.scene.stacking_slots import build_stacking_slots
from brick_stacking.planning.slot_release import slot_release_geometry


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('output',type=Path);a=p.parse_args()
    slots=build_stacking_slots(edge_m=.05,gap_m=0,layers=[4,3,2,1],colors_by_layer=['red','yellow','blue','green'],center_xy_m=[0,0],yaw_rad=0,frame_id='synthetic_table')
    table=RigidTransform('synthetic_world','synthetic_table',np.eye(4),'synthetic')
    m=np.eye(4);m[2,3]=-.1
    tcp_block=RigidTransform('synthetic_tcp','synthetic_block',m,'synthetic')
    plans=[]
    for slot in slots:
        r=slot_release_geometry(slot,table,tcp_block,yaw_rad=0,clearance_m=.03,scene_version='synthetic-scene-1')
        r['slot']=asdict(slot)
        for k in ('world_block','approach_tcp','release_tcp','retreat_tcp'):
            t=r[k];r[k]=dict(matrix=t.matrix.tolist(),target_frame=t.target_frame,source_frame=t.source_frame,source=t.source,approved=t.approved)
        plans.append(r)
    report=dict(source='synthetic',measured_dimensions_used=False,synthetic_edge_m=.05,targets=plans,motion_enabled=False,
                missing=['actual world/table/base chain','actual TCP/held offset','IK/complete collision/execution'])
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)


if __name__=='__main__':main()
