from pathlib import Path
import json,runpy,copy
import pytest
ROOT=Path(__file__).resolve().parents[3]
diagnose=runpy.run_path(str(ROOT/'tools/h0_c35_diagnostic.py'))['diagnose']


def data():
    c=json.loads((ROOT/'calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json').read_text(encoding='utf-8'))
    b=[json.loads(x) for x in (ROOT/'docs/team/B/evidence/field_20261110/single_red_observation_bundles.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    return b,c


def test_actual_bundles_stay_diagnostic_without_reference_or_clock_bound():
    b,c=data();r=diagnose(b,c,calibration_hash='fixture')
    assert r['frames']==12 and r['max_deviation_from_median_m']<.002
    assert r['reference_comparison'] is None and not r['control_ready'] and not r['motion_enabled']
    assert r['clock_error_bound_s'] is None and r['exposure_to_output_s'] is None


@pytest.mark.parametrize('fault',['camera','frame','duplicate','session'])
def test_reject_mismatched_or_replayed_inputs(fault):
    b,c=data()
    if fault=='camera':b[0]['rgbd']['device_id']='different'
    if fault=='frame':b[0]['blocks'][0]['frame_id']='different'
    if fault=='duplicate':b[1]=copy.deepcopy(b[0])
    if fault=='session':b[1]['rgbd']['epoch']='different'
    with pytest.raises(ValueError):diagnose(b,c,calibration_hash='fixture')


def test_reference_comparison_does_not_enable_execution():
    b,c=data();r=diagnose(b,c,calibration_hash='fixture')
    # Synthetic reference tests arithmetic only, not an independent field measurement.
    reference=dict(frame_id=c['base_frame'],point_kind='visible_top_center',
                   point_m=r['median_top_center_base_m'],table_normal_base=[0.,0.,1.],
                   measurement_error_bound_m=.001,independent=True)
    out=diagnose(b,c,calibration_hash='fixture',reference=reference)
    assert out['reference_comparison']['diagnostic_budget_met'] and not out['control_ready']
    reference['point_kind']='grasp_tcp'
    with pytest.raises(ValueError):diagnose(b,c,calibration_hash='fixture',reference=reference)


def test_new_recorded_timing_is_reported_without_becoming_execution_bound():
    _,c=data()
    b=[json.loads(x) for x in (ROOT/'docs/team/B/evidence/field_20261110/ruler_bind_observation_bundles.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    # Ruler-bound capture predates the later accepted timing exports: never fill it
    # from H0's newer timing statistics if the per-frame fields remain unknown.
    # Legacy export calls the coordinate frame 'head'; never silently rename it.
    with pytest.raises(ValueError,match='camera identity/frame mismatch'):
        diagnose(b,c,calibration_hash='fixture')
    field=[json.loads(x) for x in (ROOT/'docs/team/B/evidence/field_20261110/verify_pre_grasp_observation_bundles.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    current=diagnose(field,c,calibration_hash='fixture')
    assert current['clock_error_bound_s']>0 and current['exposure_to_output_s']>0
    assert 'not a future runtime bound' in current['exposure_latency_scope']
