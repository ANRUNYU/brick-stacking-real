"""Versioned offline revolute-chain FK using existing frame-aware transforms.

Joint origin is T_parent_joint at q=0; axis is expressed in that joint frame.
No implicit robot dimensions, zero offsets, arm selection or TCP.
"""
from dataclasses import dataclass
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform


@dataclass(frozen=True)
class RevoluteJoint:
    name: str
    origin: RigidTransform
    axis_xyz: tuple[float, float, float]

    def __post_init__(self):
        axis = np.asarray(self.axis_xyz, float)
        if not self.name or axis.shape != (3,) or not np.isfinite(axis).all() or not np.isclose(np.linalg.norm(axis), 1, atol=1e-8):
            raise ValueError('named joint and explicit unit axis required')
        if self.origin.stamp_s is not None:
            raise ValueError('joint origin must be static')
        object.__setattr__(self, 'axis_xyz', tuple(axis))


def forward_kinematics(joints, positions_rad, *, model_version):
    """Return T_base_last_joint. Caller composes explicit flange/TCP afterward.

    Dict keys must exactly match joint names. Output always unapproved.
    """
    joints = tuple(joints)
    names = [j.name for j in joints]
    if not joints or not model_version or len(set(names)) != len(names) or set(positions_rad) != set(names):
        raise ValueError('versioned chain and exactly matching joint names required')
    frames = [joints[0].origin.target_frame] + [j.origin.source_frame for j in joints]
    if len(set(frames)) != len(frames):
        raise ValueError('cyclic/repeated chain frames')
    result = None
    for joint in joints:
        q = positions_rad[joint.name]
        if not np.isscalar(q) or not np.isfinite(q):
            raise ValueError('finite joint radians required')
        x, y, z = joint.axis_xyz
        k = np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
        rotation = np.eye(4)
        rotation[:3,:3] = np.eye(3) + np.sin(q)*k + (1-np.cos(q))*(k@k)
        # Rotation acts after the static origin, in the child joint frame.
        local = RigidTransform(joint.origin.target_frame, joint.origin.source_frame,
                               joint.origin.matrix @ rotation, 'offline_fk', model_version)
        result = local if result is None else result.compose(local)
    return result
