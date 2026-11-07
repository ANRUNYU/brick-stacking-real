import pytest
from brick_stacking.planning.candidate_evaluation import evaluate_candidates
from brick_stacking.planning.joint_trajectory import JointLimits


def run(status='PASS',version='mock-envelope',**ctx):
    context=dict(scene_version='mock-1',calibration_version='synthetic-1',clock_domain='mock',epoch='1',state_stamp_s=1,now_s=1,max_age_s=.1,start_tolerance_rad=.01,expected_start_rad=[0])
    context.update(ctx)
    candidates=[dict(candidate_id='unreachable',q=None),dict(candidate_id='limit',q=[[0],[3]]),dict(candidate_id='long',q=[[0],[.8]]),dict(candidate_id='short',q=[[0],[.2]])]
    return evaluate_candidates(candidates,solve_ik=lambda c:c['q'],check_collision=lambda t:dict(status=status,scope='synthetic envelope only',missing=['arm','camera'],model_version=version),limits=JointLimits(('J1',),(-1,),(1,),(.2,),(.3,),'mock','synthetic'),trajectory_context=context,collision_model_version='mock-envelope')


def test_independent_results_and_shortest_valid_selection():
    result=run()
    assert result['selected_candidate_id']=='short'
    rows=result['candidates']
    assert rows[0]['ik']=='FAIL' and rows[0]['trajectory_limits']=='NOT_GENERATED'
    assert rows[1]['ik']=='PASS' and rows[1]['trajectory_limits']=='FAIL'
    assert rows[3]['collision']=='PASS' and rows[3]['full_collision']=='UNKNOWN'
    assert not result['motion_enabled'] and not rows[3]['trajectory']['motion_enabled']


@pytest.mark.parametrize('status',['FAIL','UNKNOWN'])
def test_collision_hard_rejection(status):
    assert run(status=status)['selected_candidate_id'] is None


def test_stale_version_and_state_rejected():
    assert run(version='stale')['selected_candidate_id'] is None
    assert run(now_s=2)['selected_candidate_id'] is None
    assert run(calibration_version=None)['selected_candidate_id'] is None
