"""Place local mesh envelopes with explicit model-convention mapping.

No robot communication and no implicit installation/collision exclusions.
"""
import hashlib
from pathlib import Path
from brick_stacking.hardware.urdf_inspection import inspect_urdf
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.capsule_collision import Capsule


class MappedUrdfCapsules:
    def __init__(self,urdf_path,local_capsules,convention,*,base_frame,source_model_version):
        self.path=Path(urdf_path);self.digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        if convention.target_model_version!=self.digest or convention.source_model_version!=source_model_version:
            raise ValueError('source/target model hash mismatch')
        self.convention=convention;self.source_version=source_model_version;self.base=base_frame
        self.local=tuple(local_capsules)
        if not self.local or len({c.name for c in self.local})!=len(self.local): raise ValueError('named mesh envelopes required')
        audit=inspect_urdf(self.path);parents={j['child']:j for j in audit['joints']}
        self.subsets={}
        for c in self.local:
            node=c.frame_id;visited=set();names=[]
            while node!=base_frame:
                if node in visited or node not in parents: raise ValueError('missing or cyclic link path')
                visited.add(node);j=parents[node]
                if j['type']=='revolute': names.append(j['name'])
                elif j['type']!='fixed': raise ValueError('unsupported joint')
                node=j['parent']
            self.subsets[c.name]=tuple(names)

    def at_source_q(self,q):
        if len(q)!=len(self.convention.joint_names): raise ValueError('joint count mismatch')
        mapped=self.convention.map_positions(dict(zip(self.convention.joint_names,q)),
                    source_model_version=self.source_version,target_model_version=self.digest)
        placed=[]
        for c in self.local:
            tf,report=urdf_forward_kinematics(self.path,{n:mapped[n] for n in self.subsets[c.name]},
                                            base_frame=self.base,tip_frame=c.frame_id)
            if report['model_sha256']!=self.digest: raise ValueError('model changed during planning')
            placed.append(Capsule(c.name,tuple(tf.apply(c.start_m)),tuple(tf.apply(c.end_m)),c.radius_m,self.base))
        return tuple(placed)
