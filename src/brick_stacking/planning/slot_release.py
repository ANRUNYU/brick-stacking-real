"""D-owned Slot -> C TCP release geometry. No IK or motion authorization."""
import math
import numpy as np
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.calibration import tcp_target_for_block


def slot_release_geometry(slot, world_table, tcp_block, *, yaw_rad, clearance_m, scene_version):
    """Slot centers use measured dimensions via existing build_stacking_slots.

    Approach/retract follow table +Z, which need not equal world +Z. Tool shape,
    neighbors/support contact exemptions and trajectory feasibility are separate.
    """
    if slot.frame_id!=world_table.source_frame:
        raise ValueError('slot/table frame mismatch')
    if not scene_version or not math.isfinite(yaw_rad) or not math.isfinite(clearance_m) or clearance_m<=0:
        raise ValueError('scene, heading and positive clearance required')
    p=np.asarray(slot.center_m,float)
    if p.shape!=(3,) or not np.isfinite(p).all(): raise ValueError('finite slot center required')
    c,s=math.cos(yaw_rad),math.sin(yaw_rad)
    m=np.eye(4);m[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]];m[:3,3]=p
    table_block=RigidTransform(slot.frame_id,tcp_block.source_frame,m,'offline_slot_geometry',scene_version)
    world_block=world_table.compose(table_block)
    release=tcp_target_for_block(world_block,tcp_block)
    lifted=release.matrix.copy()
    lifted[:3,3]+=world_table.matrix[:3,2]*clearance_m
    above=RigidTransform(release.target_frame,release.source_frame,lifted,'offline_slot_geometry',scene_version)
    return {'slot_id':slot.slot_id,'supports':slot.supports,'scene_version':scene_version,
            'world_block':world_block,'approach_tcp':above,'release_tcp':release,'retreat_tcp':above,
            'ik':'UNKNOWN','full_collision':'UNKNOWN','motion_enabled':False}
