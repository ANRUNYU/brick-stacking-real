"""Synthetic coordination demonstration. No ROS/CAN/SDK imports or motion."""
import argparse
from pathlib import Path
import json
from brick_stacking.coordination.reachability import MapContext,ReachabilityMap,ReachabilityEvidence,pose_grid
from brick_stacking.coordination.route_candidates import RelaySite,relay_candidates
from brick_stacking.coordination.shared_zone import SharedZone,SharedZoneManager
from brick_stacking.coordination.table_relay import TableRelay
from brick_stacking.coordination.relay_coordinator import RelayCoordinator
from brick_stacking.execution.handoff_fsm import ZoneEvidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    context=MapContext('mock_table','mock-model','mock-cal','mock-tcp','mock-scene','mock-other-arm')
    cells=list(pose_grid([0.,.1],[0.],[.05],[(0.,0.,0.,1.)],frame_id='mock_table',stamp_s=1.))
    reach=ReachabilityMap(context)
    for arm in ('left','right'):
        for cell in cells:
            for phase in ('place_and_retreat','pick_and_retreat'):
                reach.record(ReachabilityEvidence(arm,cell.candidate_id,phase,'CANDIDATE','mock',True,True,
                              'mock-plan-'+arm+'-'+cell.candidate_id+'-'+phase,'Fixture only; no IK/collision solver ran'))
    candidates=relay_candidates(reach,[RelaySite('mock_site','mock_zone','mock_object_pose',cells[0].candidate_id,cells[1].candidate_id)],
                                donor='right',receiver='left',current_context=context)
    now=[1.]
    zones=SharedZoneManager([SharedZone('mock_zone','mock_table',(-.1,-.1,0.),(.2,.2,.2))],
                            clock=lambda:now[0],clock_epoch='mock-epoch',scene_version='mock-scene',max_evidence_age_s=.5)
    relay=TableRelay(donor='right',receiver='left',zone_id='mock_zone',object_id='mock-brick',clock_domain='mock-epoch',max_age_s=.5)
    coordinator=RelayCoordinator(relay,zones)
    def e(occupied):return ZoneEvidence('mock-observation-'+str(now[0]),now[0],'mock-epoch',occupied,True,True)
    events=[]
    coordinator.reconcile(e(False),now_s=now[0],observed_object_id=None,scene_version='mock-scene')
    for side,occupied,object_id in [('right',True,'mock-brick'),('left',False,None)]:
        now[0]+=.01
        handle=coordinator.reserve(side,e(not occupied),now_s=now[0],ttl_s=.5,
                                    observed_object_id='mock-brick' if side=='left' else None)
        coordinator.enter(handle)
        events.append(dict(event='enter',side=side,state=relay.snapshot()))
        now[0]+=.1
        coordinator.complete(handle,e(occupied),now_s=now[0],observed_object_id=object_id,scene_version='mock-scene')
        events.append(dict(event='complete',side=side,state=relay.snapshot()))
    report=dict(source='mock',upstream_main='d296447456c7461a01842fe140dd28e19339ff19',
                motion_enabled=False,hardware_accessed=False,actual_reachability_verified=False,
                reachability=reach.snapshot(),relay_candidates=candidates,events=events,zones=zones.snapshot(),
                notice='Synthetic capability fixtures, not computed IK, validated workspace or safe-motion permit')
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(args.output),final_state=relay.snapshot()['state'],motion_enabled=False)))


if __name__=='__main__':main()
