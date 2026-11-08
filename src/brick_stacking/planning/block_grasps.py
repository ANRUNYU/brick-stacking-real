"""Opposed cube-face grasp geometry, independent of a hand actuator preset.

Grasp frame: origin at cube center, +X between contacts, +Z outward approach.
It is a desired geometric frame, never an assumed/calibrated robot TCP.
"""
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


def cube_face_grasps(world_block, *, edge_m, finger_side_clearance_m,
                     approach_world, pregrasp_distance_m, geometry_version):
    values = (edge_m, finger_side_clearance_m, pregrasp_distance_m)
    if any(not np.isscalar(x) or not np.isfinite(x) for x in values) or edge_m <= 0 or finger_side_clearance_m < 0 or pregrasp_distance_m <= 0:
        raise ValueError('explicit positive dimensions/distances and nonnegative side clearance required')
    if not isinstance(geometry_version, str) or not geometry_version:
        raise ValueError('versioned block geometry required')
    z = np.asarray(approach_world, float)
    if z.shape != (3,) or not np.isfinite(z).all() or not np.isclose(np.linalg.norm(z), 1, atol=1e-8, rtol=0):
        raise ValueError('explicit world unit approach direction required')
    candidates, rejected = [], []
    r = world_block.matrix[:3,:3]
    for axis in (0, 1, 2):
        normal = r[:,axis]
        if abs(np.dot(normal, z)) > 1e-7:
            rejected.append(dict(block_axis=axis, reason='closing faces not perpendicular to supplied approach'))
            continue
        grasp_frame = world_block.source_frame + f'_face_grasp_{axis}'
        pose = np.eye(4)
        pose[:3,:3] = np.column_stack((normal, np.cross(z, normal), z))
        pose[:3,3] = world_block.matrix[:3,3]
        target = RigidTransform(world_block.target_frame, grasp_frame, pose, 'geometric_grasp_candidate', geometry_version)
        pre = pose.copy();pre[:3,3] += z*pregrasp_distance_m
        pregrasp = RigidTransform(world_block.target_frame, grasp_frame, pre, 'geometric_grasp_candidate', geometry_version)
        contacts = []
        for sign in (-1, 1):
            p = np.zeros(3);p[axis] = sign*edge_m/2
            contacts.append(dict(point_block_m=p.tolist(), point_world_m=world_block.apply(p).tolist(),
                                 outward_normal_world=(sign*normal).tolist()))
        candidates.append(dict(candidate_id=grasp_frame, target=target, pregrasp=pregrasp,
                face_axis_block=axis, contacts=contacts, object_width_m=edge_m,
                required_opening_m=edge_m+2*finger_side_clearance_m,
                approach_world=z.tolist(), travel_direction_world=(-z).tolist(),
                input_capture_stamp_s=world_block.stamp_s,
                flange_goal=None, hand_preset=None, ik='NOT_CHECKED',
                trajectory='NOT_GENERATED', full_collision='UNKNOWN', motion_enabled=False))
    return dict(candidates=candidates, rejected=rejected, geometry_version=geometry_version,
                scope='opposed face-center geometry only; contact/friction, opening capability, reachability and hand/environment collision not established')
