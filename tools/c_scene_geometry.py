"""Use observed table geometry + accepted-fit extrinsic for C's handoff.

Produces frame-local block/grasp/slot geometry only. Actual grasp-to-flange TF,
fresh seven-axis start, IK, joint paths and full collisions remain separate.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import cv2
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.camera_projection import backproject
from brick_stacking.localization.table_plane import TablePlane
from brick_stacking.localization.table_coordinates import table_coordinates,resting_cube_geometry
from brick_stacking.models.block_pose import BlockPose
from brick_stacking.planning.block_grasps import cube_face_grasps
from brick_stacking.scene.stacking_slots import build_stacking_slots


def pose(t):return dict(target_frame=t.target_frame,source_frame=t.source_frame,matrix=t.matrix.tolist(),source=t.source,approved=False)


def plan(calibration,observation,frame,design):
    if calibration.get('operator_acceptance',{}).get('accepted') is not True:
        raise ValueError('operator-accepted fitting context required; not a motion approval')
    if calibration['context']['camera_serial']!=observation['camera_serial']:
        raise ValueError('camera binding mismatch')
    with np.load(frame,allow_pickle=False) as data:
        meta=json.loads(str(data['metadata'].item()));k=data['k'];depth=data['depth_m']
    if meta['camera_id']!=observation['camera_serial'] or meta['frame_id']!=calibration['camera_frame']:
        raise ValueError('observed optical frame mismatch')
    if not meta['registered'] or not meta['rectified']:raise ValueError('registered rectified geometry required')
    base_camera=RigidTransform(calibration['base_frame'],calibration['camera_frame'],calibration['T_base_camera'],'operator_accepted_fit_only',calibration['report']['candidate_id'])
    plane=TablePlane(**observation['table_plane'])
    camera_table=table_coordinates(plane,backproject(design['placement_anchor_xy'],1.,k),camera_frame=base_camera.source_frame,table_frame=design['table_frame'],version=design['scene_version'])
    base_table=base_camera.compose(camera_table)
    blocks=[]
    for item in design['objects']:
        camera_block,geometry=resting_cube_geometry(plane,item['top_corners_xy'],k,edge_m=design['edge_m'],camera_frame=base_camera.source_frame,
                        block_frame=item['candidate_id'],version=design['scene_version'],rests_on_table=True)
        base_block=base_camera.compose(camera_block)
        localized=BlockPose(item['candidate_id'],base_block.target_frame,observation['stamp_s'],tuple(base_block.matrix[:3,3]),None,
                            calibration['report']['candidate_id'],'recorded_geometry_with_accepted_fit',False)
        mask=np.zeros(depth.shape,np.uint8);cv2.fillConvexPoly(mask,np.asarray(item['top_corners_xy'],np.int32),1)
        mask=cv2.erode(mask,np.ones((7,7),np.uint8)).astype(bool)&np.isfinite(depth)&(depth>0)
        yy,xx=np.nonzero(mask)
        if len(xx)<20:raise ValueError('insufficient visible top interior')
        height_error=np.abs(plane.heights(backproject(np.c_[xx,yy],depth[mask],k))-design['edge_m'])
        grasp=cube_face_grasps(base_block,edge_m=design['edge_m'],finger_side_clearance_m=design['mock_grasp_design']['finger_side_clearance_m'],
                              approach_world=base_table.matrix[:3,2],pregrasp_distance_m=design['mock_grasp_design']['pregrasp_distance_m'],geometry_version=design['geometry_version'])
        for row in grasp['candidates']:
            for key in ('target','pregrasp'):row[key]=pose(row[key])
        blocks.append(dict(color=item['color'],block_pose=asdict(localized),T_base_block_representative=pose(base_block),geometry=geometry,
                           top_depth_p95_error_m=float(np.percentile(height_error,95)),top_depth_max_error_m=float(height_error.max()),
                           base_origin_distance_m=float(np.linalg.norm(base_block.matrix[:3,3])),grasp_geometry=grasp))
    slots=build_stacking_slots(edge_m=design['edge_m'],gap_m=0.,layers=[4,3,2,1],colors_by_layer=['red','yellow','blue','green'],
                               center_xy_m=[0.,0.],yaw_rad=0.,frame_id=design['table_frame'])
    targets=[]
    for slot in slots:
        matrix=np.eye(4);matrix[:3,3]=slot.center_m
        target=base_table.compose(RigidTransform(slot.frame_id,'desired_'+slot.slot_id,matrix,'desired_slot_geometry',design['scene_version']))
        targets.append(dict(slot=asdict(slot),T_base_block_desired=pose(target),tool_release_goal=None,reason='actual held-block/TCP offset not yet available'))
    ranking=sorted((dict(candidate_id=b['block_pose']['candidate_id'],distance_m=b['base_origin_distance_m']) for b in blocks),key=lambda r:r['distance_m'])
    return dict(schema_version='c-observed-scene-geometry-1',source='real_recorded_with_mock_grasp_design',scene_version=design['scene_version'],
                calibration_id=calibration['report']['candidate_id'],operator_fit_acceptance=calibration['operator_acceptance'],
                independent_validation=calibration['independent_validation'],input_device_stamp_s=observation['stamp_s'],input_clock_domain=observation['clock_domain'],
                T_base_table_candidate=pose(base_table),blocks=blocks,proximity_ranking=ranking,
                proximity_scope='distance ranking only; not IK reachability',ten_layer_targets=targets,measured_edge_m=design['edge_m'],
                measured_edge_source=design['edge_source'],grasp_design=design['mock_grasp_design'],sensor_diagnostics=observation['checks'],
                ik='NOT_CHECKED',joint_trajectory='NOT_GENERATED',full_collision='UNKNOWN',motion_enabled=False,
                plan_result=dict(feasible=False,rejection_reason='Need actual grasp-to-flange transform, fresh seven-axis start and complete scene collision check',
                                 segments=[],valid_until_host_monotonic_s=None),
                missing=['actual stable hand preset and grasp offset','fresh seven-axis state','IK and timed joint route','complete arm/hand/payload/environment collision coverage'],
                notice='desired grasp frames are not robot TCP/flange commands; slots are proposed geometry, not D-owned committed scene state')


def main():
    p=argparse.ArgumentParser(__doc__)
    for key in ('calibration','observation','frame','design','output'):p.add_argument(key,type=Path)
    a=p.parse_args();r=plan(json.loads(a.calibration.read_text()),json.loads(a.observation.read_text()),a.frame,json.loads(a.design.read_text()))
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps(dict(blocks=[dict(color=b['color'],center_base_m=b['block_pose']['center_m'],grasp_candidates=len(b['grasp_geometry']['candidates'])) for b in r['blocks']],slots=len(r['ten_layer_targets']),ik=r['ik'],motion_enabled=False)))


if __name__=='__main__':main()
