"""Bidirectional serial tabletop staging; no hand-to-hand simultaneous transfer."""
from brick_stacking.execution.handoff_fsm import HandoffFsm


class TableRelay:
    def __init__(self,*,donor,receiver,zone_id,object_id,clock_domain,max_age_s):
        if {donor,receiver}!={'left','right'} or not zone_id or not object_id:
            raise ValueError('two distinct arms and explicit object/zone required')
        self.donor=donor;self.receiver=receiver;self.zone_id=zone_id;self.object_id=object_id
        self.fsm=HandoffFsm(clock_domain=clock_domain,max_age_s=max_age_s)
        self._token=None
        # Startup occupancy is untrusted, even though legacy FSM starts EMPTY.
        self.fsm.fault()

    def reconcile(self,evidence,*,now_s,observed_object_id):
        if evidence.occupied is True and observed_object_id!=self.object_id:
            raise ValueError('occupied relay has wrong/unknown object')
        self.fsm.recover_after_observation(evidence,now_s=now_s)

    def reserve(self,side,evidence,*,now_s,observed_object_id=None):
        if side==self.receiver and observed_object_id!=self.object_id:
            raise ValueError('receiver requires identified staged object')
        logical='left' if side==self.donor else 'right' if side==self.receiver else None
        if logical is None:raise ValueError('unknown participant')
        self._token=self.fsm.reserve(logical,evidence,now_s=now_s)
        return self._token

    def enter(self,token):self.fsm.enter(token)

    def complete(self,token,evidence,*,now_s,observed_object_id):
        if self.fsm.owner=='left' and observed_object_id!=self.object_id:
            raise ValueError('donor completion requires identified staged object')
        if self.fsm.owner=='right' and observed_object_id is not None:
            raise ValueError('receiver completion requires observed empty relay')
        self.fsm.complete(token,evidence,now_s=now_s)

    def fault(self):self.fsm.fault()

    def snapshot(self):
        logical=self.fsm.owner
        return dict(state=self.fsm.state,donor=self.donor,receiver=self.receiver,
                    owner=self.donor if logical=='left' else self.receiver if logical=='right' else None,
                    zone_id=self.zone_id,object_id=self.object_id,motion_enabled=False,
                    shared_zone_lease_required=True)
