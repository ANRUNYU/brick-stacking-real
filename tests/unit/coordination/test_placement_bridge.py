import copy
from dataclasses import replace
import json
from pathlib import Path
import runpy
import pytest
from brick_stacking.planning.placement_bridge import (
    BundleBinding, LocalizedReviewEvidence, audit_bundle, to_shadow_inspection)
from brick_stacking.planning.placement_review import Context,ErrorBound
from brick_stacking.localization.ruler_reference import audit_ruler,reference_for_c35

ROOT=Path(__file__).resolve().parents[3]
FIELD=ROOT/'docs/team/B/evidence/field_20261110'


def rows(name):
    return [json.loads(x) for x in (FIELD/(name+'_observation_bundles.jsonl')).read_text(encoding='utf-8').splitlines() if x.strip()]


def source():
    b=next(x for x in rows('verify_pre_grasp') if x['timing']['scene_consistency']['scene_consistent'])
    r=b['rgbd'];t=b['timing']
    binding=BundleBinding(r['device_id'],r['frame_id'],r['epoch'],t['host_boot_epoch'],
                          b['profile_hash'],t['error_bound_evidence_ref'],2.656)
    return b,binding


def test_real_recorded_three_cases_never_become_placement_pass():
    report=runpy.run_path(str(ROOT/'tools/m_review_field_replay.py'))['replay'](ROOT)
    cases=report['cases']
    assert cases['verify_pre_grasp']['color_counts']=={'MATCH':15}
    assert cases['verify_green']['color_counts']=={'MISMATCH':11}
    assert cases['verify_empty']['color_counts']=={'UNKNOWN':12}
    assert cases['verify_empty']['source_checks_passed']==0
    for case in cases.values():
        assert case['placement_verdicts']=={'UNKNOWN':case['frames']}
    assert report['ruler']['status']=='FRAME_BRIDGE_REQUIRED'
    assert report['commands_sent']==0 and not report['live_freshness_checked']


@pytest.mark.parametrize('fault',['boot','epoch','profile','clock','stale','future','block'])
def test_source_faults_rejected(fault):
    b,binding=source();now=b['timing']['output_monotonic_s']
    if fault=='boot':b['timing']['host_boot_epoch']='other'
    if fault=='epoch':b['rgbd']['epoch']='other'
    if fault=='profile':b['profile_hash']='other'
    if fault=='clock':b['timing']['clock_error_bound_s']=None
    if fault=='stale':now+=5
    if fault=='future':now=b['timing']['exposure_host_stamp_s']-.1
    if fault=='block':b['blocks'][0]['sample_id']='other'
    assert not audit_bundle(b,binding,now_s=now,expected_color='red')['source_checks_passed']


def evidence(b,binding):
    # Synthetic localization to test interface binding, not field accuracy.
    c=Context('test','block','table','scene','synthetic-cal',b['profile_hash'],
              binding.camera_epoch,'process_monotonic')
    return LocalizedReviewEvidence(c,b['rgbd']['sample_id'],b['blocks'][0]['observation_id'],
                                   'SYNTHETIC_REFERENCE','visible_top_center',True,
                                   ErrorBound(.001,.0001),ErrorBound(.001,.0001),
                                   ErrorBound(.01,.001),None,None,False,None)


def test_null_calibration_not_filled_and_unknown_support_not_inferred():
    b,binding=source();e=evidence(b,binding);now=b['timing']['output_monotonic_s']
    with pytest.raises(ValueError):to_shadow_inspection(b,binding,e,now_s=now,expected_color='red')
    b['calibration_hash']='synthetic-cal'
    result=to_shadow_inspection(b,binding,e,now_s=now,expected_color='red')
    assert result.support_ok is None and result.stable is None
    assert result.neighbors_unchanged is None and result.hand_clear is False
    assert result.stamp_s==b['timing']['exposure_host_stamp_s']


@pytest.mark.parametrize('fault',['association','sample','point','profile'])
def test_localization_binding_rejected(fault):
    b,binding=source();b['calibration_hash']='synthetic-cal';e=evidence(b,binding)
    if fault=='association':e=replace(e,target_association_confirmed=False)
    if fault=='sample':e=replace(e,sample_id='other')
    if fault=='point':e=replace(e,point_kind='model_center')
    if fault=='profile':e=replace(e,context=replace(e.context,profile_hash='other'))
    with pytest.raises(ValueError):to_shadow_inspection(b,binding,e,
                                    now_s=b['timing']['output_monotonic_s'],expected_color='red')


def ruler():
    return json.loads((FIELD/'independent_ruler_reference_v0.1.json').read_text(encoding='utf-8'))


def bridge():
    return dict(independent=True,verified=True,evidence_ref='SYNTHETIC_TEST_ONLY',version='mock',
                source_frame='table_black_cross_20mm',target_frame='L_arm_root',point_error_bound_m=.001,
                matrix=[[0,-1,0,1],[1,0,0,2],[0,0,1,3],[0,0,0,1]])


def test_cross_reference_not_equated_with_base_and_bridge_arithmetic():
    r=ruler();report=audit_ruler(r)
    assert report['reference_available'] and report['base_reference'] is None
    assert report['cross_column_horizontal_closure_residual_mm']<.1
    result=reference_for_c35(r,bridge(),base_frame='L_arm_root')
    assert result['point_m']==pytest.approx([.921,2.172,3.05])
    assert result['measurement_error_bound_m']==.003
    assert result['table_normal_base']==[0,0,1]
    assert not audit_ruler(r,bridge=bridge())['control_ready']


@pytest.mark.parametrize('fault',['independent','verified','frame','bound','matrix'])
def test_invalid_reference_bridge_rejected(fault):
    b=bridge()
    if fault in ('independent','verified'):b[fault]=False
    if fault=='frame':b['source_frame']='J1'
    if fault=='bound':b['point_error_bound_m']=None
    if fault=='matrix':b['matrix'][0][0]=2
    with pytest.raises(ValueError):reference_for_c35(ruler(),b,base_frame='L_arm_root')


def test_actual_ruler_handoff_does_not_fit_away_missing_orientation():
    report=runpy.run_path(str(ROOT/'tools/m_ruler_validation.py'))['validate'](ROOT)
    assert report['source_frames_count']==5
    assert report['ruler_audit']['reference_available']
    assert report['ruler_audit']['base_reference'] is None
    assert report['localize'] is None
    assert report['source_frame_check']['status']=='FRAME_CONVENTION_UNCONFIRMED'
    assert report['conditional_radius_check']['acceptance']=='NOT_AN_XY_OR_HEIGHT_ACCEPTANCE'
    assert not report['control_ready'] and report['commands_sent']==0


def test_camera_frame_bridge_is_explicit_and_original_recording_unchanged():
    validate=runpy.run_path(str(ROOT/'tools/m_ruler_validation.py'))['validate']
    path=FIELD/'ruler_bind_observation_bundles.jsonl';original=path.read_bytes()
    cb=dict(verified=True,evidence_ref='SYNTHETIC_FRAME_TEST_ONLY',version='test',
            source_frame='head',target_frame='camera_CP2L863000KL_color_optical_frame',
            matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
    report=validate(ROOT,camera_bridge=cb)
    assert report['localize']['frames']==5 and report['localize']['reference_comparison'] is None
    assert report['localize']['clock_error_bound_s'] is None
    assert path.read_bytes()==original and not report['control_ready']
    cb['verified']=False
    with pytest.raises(ValueError):validate(ROOT,camera_bridge=cb)
