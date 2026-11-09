"""Current-frame scene consistency, never pose prediction or robot readiness.

Confirmation only means consecutive observations agree. A plain table cannot
prove camera stationarity or establish a world frame. Every reported position
must still come from the current frame, including after a reset.
"""
from collections import defaultdict
import cv2
import numpy as np


def static_sequence_acceptance(states,required_frames):
    """A final confirmed frame cannot erase an earlier post-warmup failure."""
    if len(states)<required_frames:
        return {'result':'INCONCLUSIVE','unstable_frame_indices':[],
                'reason':'insufficient_confirmation_frames'}
    bad=[i for i,s in enumerate(states) if i>=required_frames-1 and
         (s['state']!='CONFIRMED' or not s['scene_consistent'])]
    return {'result':'FAIL' if bad else 'PASS','unstable_frame_indices':bad,
            'reason':'post_warmup_instability' if bad else 'all_post_warmup_frames_confirmed'}


class SceneConsistencyMonitor:
    def __init__(self, *, required_frames=3, max_gap_s=1., max_shift_m=.008,
                 max_plane_angle_deg=2., max_plane_offset_m=.01):
        if type(required_frames) is not int or required_frames<2:
            raise ValueError('at least two confirmation frames required')
        values=[max_gap_s,max_shift_m,max_plane_angle_deg,max_plane_offset_m]
        if not np.isfinite(values).all() or min(values)<=0:
            raise ValueError('finite positive consistency limits required')
        self.required_frames=required_frames
        self.max_gap_s=max_gap_s
        self.max_shift_m=max_shift_m
        self.angle_deg=max_plane_angle_deg
        self.offset_m=max_plane_offset_m
        self.previous=None
        self.identity=None
        self.stamp=None
        self.retired=set()
        self.consecutive=0

    def invalidate(self, reason='observation_failed'):
        self.previous=None
        self.consecutive=0
        return self._verdict('REJECTED',reason)

    def _verdict(self,state,reason):
        return {'state':state,'reason':reason,'consecutive_frames':self.consecutive,
            'scene_consistent':state=='CONFIRMED','control_ready':False,
            'reference_stationarity_verified':False,'positions_predicted':False}

    def update(self,frame,observation):
        identity=(frame.camera_id,frame.frame_id,frame.clock_domain)
        if identity in self.retired:
            return self.invalidate('retired_source_epoch')
        reason='initial_observation'
        if self.identity is not None and identity!=self.identity:
            self.retired.add(self.identity)
            self.previous=None
            self.consecutive=0
            self.stamp=None
            reason='source_reference_changed'
        if self.stamp is not None and frame.stamp_s<=self.stamp:
            return self.invalidate('non_increasing_timestamp')
        if self.stamp is not None and frame.stamp_s-self.stamp>self.max_gap_s:
            self.previous=None
            self.consecutive=0
            reason='source_gap'
        self.identity=identity
        self.stamp=frame.stamp_s
        candidates=observation.candidates
        if not candidates or any(c['status']!='SINGLE_CUBE_CANDIDATE' for c in candidates):
            return self.invalidate('empty_or_ambiguous_scene')
        if any(c.get('center_camera_m') is None or np.shape(c['center_camera_m'])!=(3,) or
               not np.isfinite(c['center_camera_m']).all() for c in candidates):
            return self.invalidate('missing_current_position')
        gray=cv2.cvtColor(frame.rgb,cv2.COLOR_RGB2GRAY)
        snapshot=[{'color':c['color'],'center_camera_m':list(c['center_camera_m']),
                   'bbox_xywh':list(c['bbox_xywh'])} for c in candidates]
        current={'plane':observation.plane,'candidates':snapshot,'gray':gray,
                 'roi':observation.roi_mask.copy(),'k':frame.k.copy()}
        if self.previous is not None:
            reason=self._change_reason(self.previous,current)
            if reason:
                self.consecutive=0
        self.consecutive+=1
        self.previous=current
        state='CONFIRMED' if self.consecutive>=self.required_frames else 'WARMING_UP'
        return self._verdict(state,reason or 'consecutive_current_observations_agree')

    def _change_reason(self,old,new):
        if old['gray'].shape!=new['gray'].shape or not np.allclose(old['k'],new['k'],rtol=0,atol=1e-6):
            return 'camera_geometry_changed'
        a,b=old['plane'],new['plane']
        angle=np.degrees(np.arccos(np.clip(np.dot(a.normal,b.normal),-1.,1.)))
        if angle>self.angle_deg or abs(a.offset_m-b.offset_m)>self.offset_m:
            return 'support_plane_changed'
        previous,current=defaultdict(list),defaultdict(list)
        for c in old['candidates']:previous[c['color']].append(c['center_camera_m'])
        for c in new['candidates']:current[c['color']].append(c['center_camera_m'])
        if {k:len(v) for k,v in previous.items()}!={k:len(v) for k,v in current.items()}:
            return 'observed_instances_changed'
        for color,points in current.items():
            distance=np.linalg.norm(np.asarray(points)[:,None]-np.asarray(previous[color])[None],axis=2)
            nearest=distance.argmin(axis=1)
            if len(set(nearest.tolist()))!=len(points) or np.any(distance[np.arange(len(points)),nearest]>self.max_shift_m):
                return 'observed_positions_changed'
        # Exclude the observed objects, not their whole row or a fixed work area.
        background=(old['roi']>0)|(new['roi']>0)
        for c in old['candidates']+new['candidates']:
            x,y,w,h=c['bbox_xywh'];pad=max(1,int(min(w,h)*.25))
            background[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]=False
        if background.sum()>=100:
            difference=np.abs(old['gray'].astype(float)-new['gray'].astype(float))
            if np.mean(difference[background]>20)>.2:
                return 'background_appearance_changed'
        return ''
