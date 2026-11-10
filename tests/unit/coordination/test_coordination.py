import pytest
from dataclasses import replace
from brick_stacking.coordination.reachability import MapContext,ReachabilityMap,ReachabilityEvidence,pose_grid
from brick_stacking.coordination.route_candidates import RelaySite,relay_candidates
from brick_stacking.coordination.shared_zone import SharedZone,SharedZoneManager,ClearanceEvidence
from brick_stacking.coordination.table_relay import TableRelay
from brick_stacking.coordination.relay_coordinator import RelayCoordinator
from brick_stacking.execution.handoff_fsm import ZoneEvidence


def context():return MapContext('table','model','cal','tcp','scene','other-arm')

def evidence(arm,pose,phase):return ReachabilityEvidence(arm,pose,phase,'CANDIDATE','mock',True,True,'mock-plan','synthetic test')


def test_pose_grid_retains_orientation_and_no_motion():
    cells=list(pose_grid([0,.1],[0],[.05],[(0,0,0,1)],frame_id='table',stamp_s=1))
    assert len(cells)==2 and all(not c.control_ready for c in cells)


def test_ik_only_not_reachable():
    with pytest.raises(ValueError): ReachabilityEvidence('left','p','pick','CANDIDATE','mock',False,False,None,'IK only')


def test_map_unknown_and_changed_context_do_not_interpolate():
    m=ReachabilityMap(context());m.record(evidence('left','p','pick'))
    assert m.query('right','p','pick',context()) is None
    assert m.query('left','p','place',context()) is None
    assert m.query('left','p','pick',replace(context(),tcp_hash='new')) is None


def test_relay_prefilter_requires_both_roles_and_stays_candidate():
    m=ReachabilityMap(context());site=RelaySite('site','zone','object-pose','donor-pose','receiver-pose')
    m.record(evidence('right','donor-pose','place_and_retreat'))
    assert not relay_candidates(m,[site],donor='right',receiver='left',current_context=context())
    m.record(evidence('left','receiver-pose','pick_and_retreat'))
    c=relay_candidates(m,[site],donor='right',receiver='left',current_context=context())[0]
    assert not c['motion_enabled'] and c['full_source_to_relay_to_target_plan']=='NOT_CHECKED'


def manager(overlap=False):
    t=[1.];zones=[SharedZone('zone','table',(0.,0.,0.),(1.,1.,1.))]
    if overlap:zones.append(SharedZone('adjacent','table',(.5,0.,0.),(2.,1.,1.)))
    m=SharedZoneManager(zones,clock=lambda:t[0],clock_epoch='epoch',scene_version='scene',max_evidence_age_s=.5)
    return m,t


def clear(t,scene='scene'):return ClearanceEvidence('clear'+str(t),t,True,'epoch',scene)


def test_startup_unknown_and_duplicate_reservation():
    m,t=manager()
    with pytest.raises(ValueError):m.acquire('zone','left',ttl_s=1)
    m.observe_clear('zone',clear(1));token=m.acquire('zone','left',ttl_s=1)
    with pytest.raises(ValueError):m.acquire('zone','right',ttl_s=1)
    assert m.validate('zone','left',token)


def test_overlapping_zones_share_exclusion():
    m,t=manager(True)
    for z in m.zones:m.observe_clear(z,clear(1))
    m.acquire('zone','left',ttl_s=1)
    with pytest.raises(ValueError):m.acquire('adjacent','right',ttl_s=1)


def test_expiry_retains_owner_until_new_clearance():
    m,t=manager();m.observe_clear('zone',clear(1));token=m.acquire('zone','left',ttl_s=.1)
    t[0]=1.2
    assert not m.validate('zone','left',token)
    assert m.snapshot()['zone']['owner']=='left'
    with pytest.raises(ValueError):m.observe_clear('zone',clear(1.1))
    t[0]=1.3;m.observe_clear('zone',clear(1.3))
    new=m.acquire('zone','right',ttl_s=1)
    assert new!=token and not m.validate('zone','left',token)


def test_wrong_scene_and_clock_regression_fail_closed():
    m,t=manager()
    with pytest.raises(ValueError):m.observe_clear('zone',clear(1,'other'))
    m.observe_clear('zone',clear(1));token=m.acquire('zone','left',ttl_s=1)
    t[0]=.9
    with pytest.raises(ValueError):m.validate('zone','left',token)


def test_restart_does_not_restore_lease():
    m,t=manager();m.observe_clear('zone',clear(1));token=m.acquire('zone','left',ttl_s=1)
    replacement,_=manager()
    assert not replacement.validate('zone','left',token)
    with pytest.raises(ValueError):replacement.acquire('zone','right',ttl_s=1)


def ze(stamp,occupied):return ZoneEvidence('obs'+str(stamp),stamp,'epoch',occupied,True,True)


@pytest.mark.parametrize('donor,receiver',[('left','right'),('right','left')])
def test_complete_serial_relay_with_shared_zone(donor,receiver):
    zones,t=manager();relay=TableRelay(donor=donor,receiver=receiver,zone_id='zone',object_id='brick',clock_domain='epoch',max_age_s=.5)
    c=RelayCoordinator(relay,zones)
    c.reconcile(ze(1,False),now_s=1,observed_object_id=None,scene_version='scene')
    handle=c.reserve(donor,ze(1.01,False),now_s=1.01,ttl_s=.5);c.enter(handle)
    t[0]=1.1;c.complete(handle,ze(1.1,True),now_s=1.1,observed_object_id='brick',scene_version='scene')
    assert relay.snapshot()['state']=='OCCUPIED'
    handle=c.reserve(receiver,ze(1.11,True),now_s=1.11,ttl_s=.5,observed_object_id='brick');c.enter(handle)
    t[0]=1.2;c.complete(handle,ze(1.2,False),now_s=1.2,observed_object_id=None,scene_version='scene')
    assert relay.snapshot()['state']=='EMPTY' and zones.snapshot()['zone']['status']=='CLEAR'


def test_unknown_object_and_fault_do_not_release_zone():
    zones,t=manager();r=TableRelay(donor='left',receiver='right',zone_id='zone',object_id='brick',clock_domain='epoch',max_age_s=.5);c=RelayCoordinator(r,zones)
    c.reconcile(ze(1,False),now_s=1,observed_object_id=None,scene_version='scene')
    h=c.reserve('left',ze(1.01,False),now_s=1.01,ttl_s=.1);c.enter(h);t[0]=1.2
    with pytest.raises(ValueError):c.complete(h,ze(1.2,True),now_s=1.2,observed_object_id='brick',scene_version='scene')
    assert r.snapshot()['state']=='RECOVERY' and zones.snapshot()['zone']['owner']=='left'


def test_concurrent_contenders_only_one_wins():
    from concurrent.futures import ThreadPoolExecutor
    m,t=manager();m.observe_clear('zone',clear(1))
    def attempt(side):
        try:return m.acquire('zone',side,ttl_s=.5)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,['left','right']))
    assert sum(x is not None for x in results)==1


def test_failed_exit_keeps_owner_and_blocks_reentry():
    m,t=manager();m.observe_clear('zone',clear(1));token=m.acquire('zone','left',ttl_s=1)
    t[0]=1.1
    with pytest.raises(ValueError):m.exit('zone','left',token,replace(clear(1.1),both_arms_clear=False))
    assert m.snapshot()['zone']['owner']=='left' and m.snapshot()['zone']['status']=='BLOCKED'
    with pytest.raises(ValueError):m.acquire('zone','right',ttl_s=1)


def test_scene_mismatch_during_completion_blocks_both_layers():
    zones,t=manager();r=TableRelay(donor='left',receiver='right',zone_id='zone',object_id='brick',clock_domain='epoch',max_age_s=.5);c=RelayCoordinator(r,zones)
    c.reconcile(ze(1,False),now_s=1,observed_object_id=None,scene_version='scene')
    h=c.reserve('left',ze(1.01,False),now_s=1.01,ttl_s=.5);c.enter(h);t[0]=1.1
    with pytest.raises(ValueError):c.complete(h,ze(1.1,True),now_s=1.1,observed_object_id='brick',scene_version='changed')
    assert r.snapshot()['state']=='RECOVERY' and zones.snapshot()['zone']['status']=='BLOCKED'
