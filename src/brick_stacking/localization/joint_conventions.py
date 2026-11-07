"""Explicit signed joint-coordinate mapping between versioned model files.

This mathematical map is not a physical motor zero/direction calibration.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class JointConventionMap:
    joint_names: tuple
    signs: tuple
    offsets_rad: tuple
    source_model_version: str
    target_model_version: str

    def __post_init__(self):
        names=tuple(self.joint_names);signs=tuple(self.signs);offsets=tuple(self.offsets_rad)
        if not names or len(set(names))!=len(names) or any(not isinstance(n,str) or not n for n in names):
            raise ValueError('explicit unique joint names required')
        if len(signs)!=len(names) or any(s not in (-1,1) for s in signs):
            raise ValueError('one explicit signed axis per joint required')
        if len(offsets)!=len(names) or not np.isfinite(np.asarray(offsets,float)).all():
            raise ValueError('finite explicit rad offsets required')
        if not self.source_model_version or not self.target_model_version:
            raise ValueError('both model versions required')
        object.__setattr__(self,'joint_names',names);object.__setattr__(self,'signs',signs);object.__setattr__(self,'offsets_rad',offsets)

    def map_positions(self,positions,*,source_model_version,target_model_version):
        if source_model_version!=self.source_model_version or target_model_version!=self.target_model_version:
            raise ValueError('mapping model version mismatch')
        if set(positions)!=set(self.joint_names): raise ValueError('exact joint names required')
        q=np.array([positions[n] for n in self.joint_names],float)
        if q.shape!=(len(self.joint_names),) or not np.isfinite(q).all(): raise ValueError('finite joint radians required')
        return dict(zip(self.joint_names,(q*np.array(self.signs)+self.offsets_rad).tolist()))

    def map_bounds(self,lower_rad,upper_rad):
        lo,hi=np.asarray(lower_rad,float),np.asarray(upper_rad,float)
        if lo.shape!=(len(self.joint_names),) or hi.shape!=lo.shape or not np.isfinite([lo,hi]).all() or np.any(lo>=hi):
            raise ValueError('finite ordered bounds required')
        a=lo*np.array(self.signs)+self.offsets_rad;b=hi*np.array(self.signs)+self.offsets_rad
        return np.minimum(a,b),np.maximum(a,b)
