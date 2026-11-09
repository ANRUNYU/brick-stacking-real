"""Optional FCL triangle-surface collision and distance queries.

No hardware imports. Exact for supplied triangle surfaces at supplied poses;
not continuous articulated motion, solid containment, or physical model coverage.
"""
import numpy as np


class FclMeshChecker:
    def __init__(self,meshes,*,model_version):
        import fcl
        if not model_version or not meshes: raise ValueError('versioned named meshes required')
        self.fcl=fcl;self.version=model_version;self.geometry={}
        for name,(vertices,triangles) in meshes.items():
            v=np.asarray(vertices,float);t=np.asarray(triangles)
            if not name or v.ndim!=2 or v.shape[1]!=3 or not len(v) or not np.isfinite(v).all():
                raise ValueError('finite named vertices required')
            if t.ndim!=2 or t.shape[1]!=3 or not len(t) or t.dtype.kind not in 'iu' or np.any(t<0) or np.any(t>=len(v)):
                raise ValueError('valid triangle indices required')
            model=fcl.BVHModel();model.beginModel();model.addSubModel(v,t.astype(np.int32));model.endModel()
            self.geometry[name]=model

    def check_poses(self,poses,*,exclusions,min_clearance_m):
        if set(poses)!=set(self.geometry): raise ValueError('exact named pose coverage required')
        if not np.isfinite(min_clearance_m) or min_clearance_m<0: raise ValueError('explicit nonnegative clearance required')
        for pair,reason in exclusions.items():
            if not isinstance(pair,tuple) or len(pair)!=2 or pair[0]>=pair[1] or not reason or any(n not in poses for n in pair):
                raise ValueError('explicit known pair exclusions with reasons required')
        frames={p.target_frame for p in poses.values()}
        if len(frames)!=1: raise ValueError('pose target frames differ')
        objects={}
        for name,geometry in self.geometry.items():
            p=poses[name]
            if p.source_frame!=name: raise ValueError('mesh local frame mismatch')
            objects[name]=self.fcl.CollisionObject(geometry,self.fcl.Transform(p.matrix[:3,:3],p.matrix[:3,3]))
        names=sorted(objects);pairs=[]
        for i,a in enumerate(names):
            for b in names[i+1:]:
                if (a,b) in exclusions: continue
                collision=self.fcl.CollisionResult()
                self.fcl.collide(objects[a],objects[b],self.fcl.CollisionRequest(),collision)
                distance=None
                if not collision.is_collision:
                    distance=float(self.fcl.distance(objects[a],objects[b],self.fcl.DistanceRequest(),self.fcl.DistanceResult()))
                    if not np.isfinite(distance): raise ValueError('nonfinite FCL distance')
                pairs.append(dict(first=a,second=b,surface_intersection=bool(collision.is_collision),
                                  distance_m=distance,clearance_violation=bool(collision.is_collision or distance<min_clearance_m)))
        failed=any(p['clearance_violation'] for p in pairs)
        return dict(status='FAIL' if failed else 'UNKNOWN',sampled_status='FAIL' if failed else 'PASS',
                    scope='FCL triangle surfaces at supplied poses only',model_version=self.version,
                    missing=['solid containment without intersecting surfaces','continuous joint-space motion','physical/unmodeled geometry'],
                    pairs=pairs,full_collision='UNKNOWN',motion_enabled=False,
                    exclusions=[dict(pair=list(p),reason=r) for p,r in exclusions.items()])

    def check_trajectory(self,trajectory,poses_at_q,*,source_model_version,scene_version,
                         exclusions,min_clearance_m,sample_dt_s,missing_coverage):
        """Finite checks of actual quintic joint interpolation, not Cartesian CCD.

        A generic FCL rigid-transform sweep is not substituted for articulated
        joint interpolation. Clear samples remain UNKNOWN for complete motion.
        """
        import math
        from brick_stacking.planning.joint_trajectory import sample_segment
        if trajectory.get('model_version')!=source_model_version or trajectory.get('scene_version')!=scene_version:
            raise ValueError('stale trajectory model/scene')
        if trajectory.get('interpolation')!='quintic_stop_at_each_waypoint': raise ValueError('unsupported interpolation')
        if not np.isfinite(sample_dt_s) or sample_dt_s<=0 or not isinstance(missing_coverage,list):
            raise ValueError('explicit sampling interval and coverage required')
        segments=trajectory.get('segments',[])
        if not segments: raise ValueError('nonempty trajectory required')
        total=0
        for segment in segments:
            d=segment['duration_s']
            if not np.isfinite(d) or d<=0: raise ValueError('positive finite segment durations required')
            total+=math.ceil(d/sample_dt_s)+1
        if total>10000: raise ValueError('FCL sample budget exceeded')
        checks=[];contacts=[];minimum=float('inf')
        for i,segment in enumerate(segments):
            duration=segment['duration_s']
            for t in np.linspace(0,duration,math.ceil(duration/sample_dt_s)+1):
                q,_,_=sample_segment(segment,float(t))
                row=self.check_poses(poses_at_q(q),exclusions=exclusions,min_clearance_m=min_clearance_m)
                distances=[p['distance_m'] for p in row['pairs'] if p['distance_m'] is not None]
                if distances: minimum=min(minimum,min(distances))
                checks.append(dict(segment=i,time_from_segment_start_s=float(t),sampled_status=row['sampled_status']))
                if row['sampled_status']=='FAIL':
                    contacts=[dict(p,segment=i,time_from_segment_start_s=float(t)) for p in row['pairs'] if p['clearance_violation']]
                    break
            if contacts: break
        return dict(status='FAIL' if contacts else 'UNKNOWN',sampled_status='FAIL' if contacts else 'PASS',
                    scope='FCL triangle surfaces sampled along declared quintic joint path',model_version=self.version,
                    source_model_version=source_model_version,scene_version=scene_version,samples_checked=len(checks),
                    sample_dt_s=sample_dt_s,min_sampled_distance_m=minimum if np.isfinite(minimum) else None,
                    coverage_names=sorted(self.geometry),checks=checks,contacts=contacts,missing=list(missing_coverage)+['continuous articulated motion','solid containment'],
                    full_collision='UNKNOWN',motion_enabled=False,
                    exclusions=[dict(pair=list(p),reason=r) for p,r in exclusions.items()])
