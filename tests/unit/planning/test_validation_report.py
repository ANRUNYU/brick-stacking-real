import pytest
from brick_stacking.planning.validation_report import summarize_trials


def trial(i,**change):
    r=dict(run_id=str(i),stage='M3',source='mock',assisted=False,hardware_actions=False,configuration_version='mock',calibration_version='mock',scene_version='mock',clock_domain='mock',epoch='1',execution_status='SUCCEEDED',pick_verdict='PASS',placement_verdict='PASS',stability_verdict='PASS',start_stamp_s=1,end_stamp_s=2,placement_error_xyz_m=[.001,0,0])
    r.update(change);return r


def test_mock_unknown_and_missing_errors_keep_denominators():
    report=summarize_trials([trial(1),trial(2,placement_verdict='UNKNOWN',placement_error_xyz_m=None),trial(3,execution_status='FAILED')])
    g=report['groups'][0]
    assert g['n_total']==3 and g['n_verified_execution_success']==1
    assert g['n_real_unassisted_verified_success']==0 and g['n_error_missing']==1
    assert report['acceptance']=='INCONCLUSIVE'


def test_sources_assistance_and_versions_are_separate():
    r=summarize_trials([trial(1,source='real',hardware_actions=True),trial(2,source='real',hardware_actions=True,assisted=True),trial(3,calibration_version='new')])
    assert len(r['groups'])==3
    assert sum(g['n_real_unassisted_verified_success'] for g in r['groups'])==1


def test_duplicate_run_and_ack_do_not_become_success():
    with pytest.raises(ValueError):summarize_trials([trial(1),trial(1)])
    with pytest.raises(ValueError):summarize_trials([trial(1,execution_status='ACK')])
