"""Single-coordinator process-local leases, not distributed or hardware safety."""
from dataclasses import dataclass
from threading import RLock
import math
import uuid


@dataclass(frozen=True)
class SharedZone:
    zone_id: str
    frame_id: str
    lower_m: tuple
    upper_m: tuple

    def __post_init__(self):
        if not self.zone_id or not self.frame_id or len(self.lower_m)!=3 or len(self.upper_m)!=3:
            raise ValueError('zone identity/frame and 3D bounds required')
        if not all(math.isfinite(v) for v in self.lower_m+self.upper_m) or not all(a<b for a,b in zip(self.lower_m,self.upper_m)):
            raise ValueError('finite increasing zone bounds required')

    def conflicts(self, other):
        if self.frame_id!=other.frame_id:
            raise ValueError('zones must share a verified reference frame')
        return all(a<=d and c<=b for a,b,c,d in zip(self.lower_m,self.upper_m,other.lower_m,other.upper_m))


@dataclass(frozen=True)
class ClearanceEvidence:
    evidence_id: str
    stamp_s: float
    both_arms_clear: bool
    clock_epoch: str
    scene_version: str


class SharedZoneManager:
    def __init__(self,zones,*,clock,clock_epoch,scene_version,max_evidence_age_s):
        if not clock_epoch or not scene_version or not math.isfinite(max_evidence_age_s) or max_evidence_age_s<=0:
            raise ValueError('clock epoch, scene and evidence policy required')
        self.zones={z.zone_id:z for z in zones}
        if not self.zones or len(self.zones)!=len(zones) or len({z.frame_id for z in zones})!=1:
            raise ValueError('unique zones in one frame required')
        self.clock=clock;self.epoch=clock_epoch;self.scene=scene_version;self.max_age=max_evidence_age_s
        self.state={k:dict(status='UNKNOWN',token=None,owner=None,expires=None,last_stamp=-1.,barrier=-1.) for k in self.zones}
        self._lock=RLock();self._last_now=None

    def _now(self):
        now=self.clock()
        if not math.isfinite(now) or now<0: raise ValueError('valid monotonic clock required')
        if self._last_now is not None and now<self._last_now:
            for s in self.state.values():s.update(status='BLOCKED',barrier=self._last_now)
            raise ValueError('clock regressed; new epoch/reconciliation required')
        self._last_now=now
        return now

    def _expire(self,now):
        for s in self.state.values():
            if s['status']=='LEASED' and now>=s['expires']:
                s.update(status='BLOCKED',barrier=now)  # ownership retained, never auto-unlock

    def observe_clear(self,zone_id,evidence):
        with self._lock:
            now=self._now();self._expire(now);s=self.state[zone_id]
            if s['status']=='LEASED':raise ValueError('active lease requires explicit exit')
            if (not evidence.evidence_id or evidence.both_arms_clear is not True or evidence.clock_epoch!=self.epoch or
                evidence.scene_version!=self.scene or not math.isfinite(evidence.stamp_s) or
                not 0<=now-evidence.stamp_s<=self.max_age or evidence.stamp_s<=max(s['last_stamp'],s['barrier'])):
                raise ValueError('fresh post-fault same-context clearance required')
            s.update(status='CLEAR',token=None,owner=None,expires=None,last_stamp=evidence.stamp_s)

    def acquire(self,zone_id,owner,*,ttl_s):
        with self._lock:
            now=self._now();self._expire(now);s=self.state[zone_id]
            if owner not in {'left','right'} or not math.isfinite(ttl_s) or ttl_s<=0:
                raise ValueError('explicit arm and bounded lease duration required')
            if s['status']!='CLEAR' or not 0<=now-s['last_stamp']<=self.max_age:
                raise ValueError('zone unknown, blocked, owned or stale')
            for k,other in self.state.items():
                if k!=zone_id and self.zones[zone_id].conflicts(self.zones[k]) and other['status']!='CLEAR':
                    raise ValueError('overlapping zone not clear')
            token=uuid.uuid4().hex;s.update(status='LEASED',token=token,owner=owner,expires=now+ttl_s,barrier=now)
            return token

    def validate(self,zone_id,owner,token):
        with self._lock:
            self._expire(self._now());s=self.state[zone_id]
            return s['status']=='LEASED' and s['owner']==owner and s['token']==token

    def exit(self,zone_id,owner,token,evidence):
        with self._lock:
            if not self.validate(zone_id,owner,token):raise ValueError('invalid/expired lease')
            s=self.state[zone_id];s.update(status='BLOCKED')
            # A failed evidence check retains owner/token and BLOCKED state.
            self.observe_clear(zone_id,evidence)

    def fault(self):
        with self._lock:
            now=self._now()
            for s in self.state.values():s.update(status='BLOCKED',barrier=now)

    def snapshot(self):
        with self._lock:
            self._expire(self._now())
            return {k:dict(v) for k,v in self.state.items()}
