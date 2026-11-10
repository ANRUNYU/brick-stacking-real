"""Discrete map prefilter; whole-route planning remains C's responsibility."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RelaySite:
    site_id: str
    zone_id: str
    object_pose_id: str
    donor_place_pose_id: str
    receiver_pick_pose_id: str


def relay_candidates(reach_map,sites,*,donor,receiver,current_context):
    if {donor,receiver}!={'left','right'}:raise ValueError('distinct arms required')
    result=[]
    for site in sites:
        if not all(isinstance(x,str) and x for x in vars(site).values()):raise ValueError('explicit site bindings required')
        checks=[reach_map.query(donor,site.donor_place_pose_id,'place_and_retreat',current_context),
                reach_map.query(receiver,site.receiver_pick_pose_id,'pick_and_retreat',current_context)]
        if all(e is not None and e.status=='CANDIDATE' for e in checks):
            result.append(dict(site=dict(vars(site)),donor=donor,receiver=receiver,
                               evidence_refs=[e.plan_ref for e in checks],sources=[e.source for e in checks],
                               full_source_to_relay_to_target_plan='NOT_CHECKED',motion_enabled=False))
    return result
