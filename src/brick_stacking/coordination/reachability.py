"""Pose/phase-specific reachability evidence. UNKNOWN is never inferred reachable."""
from dataclasses import dataclass
from itertools import product
import math
from brick_stacking.models.block_pose import BlockPose


@dataclass(frozen=True)
class MapContext:
    frame_id: str
    model_hash: str
    calibration_hash: str
    tcp_hash: str
    scene_version: str
    other_arm_state_hash: str

    def __post_init__(self):
        if not all(isinstance(v,str) and v.strip() for v in vars(self).values()):
            raise ValueError('explicit geometry/context versions required')


@dataclass(frozen=True)
class ReachabilityEvidence:
    arm: str
    pose_id: str
    phase: str
    status: str
    source: str
    full_path_checked: bool
    collision_checked: bool
    plan_ref: str | None
    reason: str

    def __post_init__(self):
        if self.arm not in {'left','right'} or self.status not in {'UNKNOWN','UNREACHABLE','CANDIDATE'}:
            raise ValueError('invalid role/status')
        if self.source not in {'mock','recorded','real'} or not self.pose_id or not self.phase or not self.reason:
            raise ValueError('provenance/phase/identity required')
        if type(self.full_path_checked) is not bool or type(self.collision_checked) is not bool:
            raise ValueError('explicit capability booleans required')
        if self.status=='CANDIDATE' and not (self.full_path_checked and self.collision_checked and self.plan_ref):
            raise ValueError('IK alone cannot establish a path candidate')


class ReachabilityMap:
    def __init__(self, context):
        self.context=context
        self._cells={}

    def record(self, evidence):
        self._cells[(evidence.arm,evidence.pose_id,evidence.phase)]=evidence

    def query(self, arm, pose_id, phase, current_context):
        if current_context!=self.context:
            return None
        return self._cells.get((arm,pose_id,phase))

    def snapshot(self):
        return dict(schema_version='dual-arm-map-1',context=dict(vars(self.context)),
                    cells=[dict(vars(v)) for v in self._cells.values()],motion_enabled=False,
                    notice='Discrete sampled poses/phases only; no interpolation or real-motion certification')


def pose_grid(x_values,y_values,z_values,orientations,*,frame_id,stamp_s,clock_source='synthetic'):
    """Explicit discretization. No workspace dimensions or preferred grasp inferred."""
    axes=[tuple(a) for a in (x_values,y_values,z_values)]
    quaternions=[tuple(q) for q in orientations]
    if not frame_id or not math.isfinite(stamp_s) or stamp_s<0 or not quaternions:
        raise ValueError('frame/time/orientations required')
    if any(not a or not all(math.isfinite(v) for v in a) or len(set(a))!=len(a) for a in axes):
        raise ValueError('explicit distinct finite sampling coordinates required')
    for q in quaternions:
        if len(q)!=4 or not all(math.isfinite(v) for v in q) or abs(sum(v*v for v in q)-1)>1e-6:
            raise ValueError('unit xyzw quaternion required')
    for i,(x,y,z,q) in enumerate(product(*axes,quaternions)):
        yield BlockPose(f'pose_{i:05}',frame_id,stamp_s,(x,y,z),q,None,clock_source,False)
