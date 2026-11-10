"""Compose legacy relay FSM with shared-zone fencing for offline state transitions."""
from brick_stacking.coordination.shared_zone import ClearanceEvidence


class RelayCoordinator:
    def __init__(self,relay,zones):
        if relay.zone_id not in zones.zones or relay.fsm.clock_domain!=zones.epoch:
            raise ValueError('relay zone and same-clock epoch binding required')
        self.relay=relay;self.zones=zones;self.active=None

    def _clearance(self,e,scene_version):
        if scene_version!=self.zones.scene:raise ValueError("scene version mismatch")
        return ClearanceEvidence(e.observation_id,e.stamp_s,e.left_clear and e.right_clear,
                                 e.clock_domain,self.zones.scene)

    def reconcile(self,evidence,*,now_s,observed_object_id,scene_version):
        # Separate scene/version provenance must be supplied by the caller.
        self.relay.reconcile(evidence,now_s=now_s,observed_object_id=observed_object_id)
        try:self.zones.observe_clear(self.relay.zone_id,self._clearance(evidence,scene_version))
        except Exception:
            self.relay.fault();raise
        self.active=None

    def reserve(self,side,evidence,*,now_s,ttl_s,observed_object_id=None):
        lease=self.zones.acquire(self.relay.zone_id,side,ttl_s=ttl_s)
        try:token=self.relay.reserve(side,evidence,now_s=now_s,observed_object_id=observed_object_id)
        except Exception:
            self.relay.fault();self.zones.fault();raise
        self.active=(side,lease,token)
        return self.active

    def _check(self,handle):
        if handle is None or handle!=self.active or not self.zones.validate(self.relay.zone_id,handle[0],handle[1]):
            self.relay.fault()
            raise ValueError('missing, expired or superseded zone fencing token')

    def enter(self,handle):
        self._check(handle);self.relay.enter(handle[2])

    def complete(self,handle,evidence,*,now_s,observed_object_id,scene_version):
        self._check(handle)
        try:
            self.relay.complete(handle[2],evidence,now_s=now_s,observed_object_id=observed_object_id)
            self.zones.exit(self.relay.zone_id,handle[0],handle[1],self._clearance(evidence,scene_version))
        except Exception:
            self.relay.fault();self.zones.fault();raise
        self.active=None

    def fault(self):
        self.relay.fault();self.zones.fault()
