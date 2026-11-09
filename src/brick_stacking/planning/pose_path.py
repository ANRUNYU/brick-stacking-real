"""Ordered TCP pose targets -> bounded IK -> timed joint path, no execution.

Starts at the supplied joint state; every target is solved using the previous
solution as seed. Collision checking remains a separate required provider.
"""
from brick_stacking.planning.numerical_ik import solve_pose_ik
from brick_stacking.planning.joint_trajectory import build_offline_trajectory


def plan_pose_path(fk, targets, seed_rad, limits, *, ik_settings, trajectory_context):
    targets=tuple(targets)
    if not targets: raise ValueError('explicit ordered TCP targets required')
    solutions=[];points=[list(seed_rad)]
    result=dict(schema_version='c-pose-path-1',ik='UNKNOWN',trajectory_limits='NOT_GENERATED',
                full_collision='UNKNOWN',motion_enabled=False,trajectory=None,ik_results=solutions,
                model_version=limits.model_version if limits else None,
                scene_version=trajectory_context.get('scene_version'),
                calibration_version=trajectory_context.get('calibration_version'))
    for index,target in enumerate(targets):
        solved=solve_pose_ik(fk,target,points[-1],limits,**ik_settings)
        solutions.append(solved)
        if solved['ik']!='PASS':
            result.update(ik='FAIL',failed_target_index=index,reason=solved['reason'])
            return result
        points.append(solved['positions_rad'])
    result['ik']='PASS'
    try:
        trajectory=build_offline_trajectory(points,limits,**trajectory_context)
    except ValueError as exc:
        result.update(trajectory_limits='FAIL',reason=str(exc))
        return result
    trajectory['ik']='PASS'
    result.update(trajectory_limits='PASS',trajectory=trajectory,
                  reason='COLLISION_NOT_CHECKED',joint_waypoints_rad=points)
    return result
