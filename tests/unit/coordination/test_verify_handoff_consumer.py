from copy import deepcopy
from dataclasses import asdict
import hashlib,json,runpy
from pathlib import Path
import pytest
from brick_stacking.vision.verify_export import localized_review_handoff
from brick_stacking.planning.placement_bridge import BundleBinding
from brick_stacking.planning.placement_review import Context
from brick_stacking.planning.verify_handoff_consumer import consume_handoff

ROOT=Path(__file__).resolve().parents[3]
FIELD=ROOT/'docs/team/B/evidence/field_20261110'


def sample():
    rows=[json.loads(x) for x in (FIELD/'verify_pre_grasp_observation_bundles.jsonl').read_text().splitlines()]
    b=next(x for x in rows if x['timing']['scene_consistency']['scene_consistent'])
    t=b['timing'];r=b['rgbd']
    bind=BundleBinding(r['device_id'],r['frame_id'],r['epoch'],t['host_boot_epoch'],
                       b['profile_hash'],t['error_bound_evidence_ref'],2.656)
    return b,bind,asdict(localized_review_handoff(b,expected_color='red'))


def test_actual_sidecars_all_block_without_reference_and_association():
    report=runpy.run_path(str(ROOT/'tools/m_consume_verify_handoff.py'))['consume'](ROOT)
    assert sum(s['frames'] for s in report['sessions'].values())==38
    for s in report['sessions'].values():
        assert s['status_counts']=={'BLOCKED':s['frames']}
        assert s['reason_counts']['TARGET_ASSOCIATION_UNCONFIRMED']==s['frames']
        assert 'HANDOFF_SCHEMA_MISMATCH' not in s['reason_counts']
    assert not report['control_ready'] and report['commands_sent']==0


def complete():
    b,bind,row=sample()
    # Synthetic binding and metric fixtures exercise the interface, not field truth.
    b['calibration_hash']='synthetic-cal';row['calibration_hash']='synthetic-cal'
    row.update(target_id='synthetic-target',region_id='synthetic-slot',reference_id='synthetic-ref',
               target_association_confirmed=True,hand_clear=True)
    for key in ('xy_m','height_m','yaw_rad'):row[key]=dict(value=.001,bound=.0001,status='MEASURED')
    ctx=Context('synthetic-target','block','synthetic-table','synthetic-scene',
                'synthetic-cal',b['profile_hash'],bind.camera_epoch,'process_monotonic')
    return b,bind,row,ctx


def test_complete_shadow_input_preserves_unknown_support_and_never_grants_pass():
    b,bind,row,ctx=complete()
    inspection,result=consume_handoff(row,b,bind,context=ctx,
                              now_s=b['timing']['output_monotonic_s'],expected_color='red')
    assert result['status']=='SHADOW_INSPECTION_READY' and inspection.support_ok is None
    assert inspection.stable is None and inspection.neighbors_unchanged is None
    assert result['formal_placement_verdict']=='UNKNOWN' and result['permit'] is None


@pytest.mark.parametrize('fault',['sample','calibration','metric','clock','color','point','target','hand','schema','formal_point'])
def test_sidecar_tampering_or_missing_evidence_is_rejected(fault):
    b,bind,row,ctx=complete()
    if fault=='sample':row['sample_id']='other'
    if fault=='calibration':row['calibration_hash']='other'
    if fault=='metric':row['xy_m']=dict(status='MEASURED',value=float('nan'),bound=0.)
    if fault=='clock':row['clock_error_bound_s']=0.
    if fault=='color':row['color_check']='MISMATCH'
    if fault=='point':row['point_kind']='model_center'
    if fault=='target':row['target_id']='other'
    if fault=='hand':row['hand_clear']=None
    if fault=='schema':row['schema_version']='unknown'
    if fault=='formal_point':row['formal_verify_point_kind']='visible_top_center'
    inspection,result=consume_handoff(row,b,bind,context=ctx,
                              now_s=b['timing']['output_monotonic_s'],expected_color='red')
    assert inspection is None and result['status']=='BLOCKED'


def test_target_request_never_uses_candidate_hash_as_approval_or_observed_pose_as_goal():
    target=json.loads((ROOT/'config/planning/first_placement_review_request.template.json').read_text())
    assert target['calibration_hash'] is None and not target['target_association_confirmed']
    assert target['formal_verify_reference']['expected_center_camera_m'] is None
    assert target['placement_review_reference']['expected_point_camera_m'] is None
    assert target['formal_verify_reference']['point_kind']!='visible_top_center'
    candidate=target['calibration_candidate']
    assert candidate['file_sha256']==hashlib.sha256((ROOT/candidate['path']).read_bytes()).hexdigest()
