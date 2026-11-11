from dataclasses import replace, asdict
import json
import pytest

from brick_stacking.planning.placement_review import (
    Action, Band, Context, ErrorBound, Inspection, PushEligibility,
    ReviewPolicy, TimeBudget, review, compare_effect,
)
from brick_stacking.execution.correction_session import CorrectionSession


@pytest.fixture
def inputs():
    # Synthetic thresholds, not a field recommendation or frozen H0 budget.
    p = ReviewPolicy('synthetic-v1', Band(.002,.004,.015), Band(.002,.004,.008),
                     Band(.02,.04,.08), .002,.004,2,20.,.0005,1.,2)
    c = Context('b1','block','table','s1','cal1','profile1','e1','mock-monotonic')
    i = Inspection(c,'o1',10.,ErrorBound(.010,.0002),ErrorBound(.0005,.0001),
                   ErrorBound(.005,.001),True,True,True,True,True,True)
    t = TimeBudget(100.,40.,10.,2.,5.,10.)
    push = PushEligibility('response1','contact1',True,True,True,True,True,True)
    return p,c,i,t,push


def decide(data, **kwargs):
    p,c,i,t,push = data
    return review(i,p,t,now_s=10.1,expected_context=c,push=push,**kwargs)


def test_inside_band_does_not_refine(inputs):
    p,c,i,t,push=inputs
    i=replace(i,xy_m=ErrorBound(.003,.0001))
    assert decide((p,c,i,t,push)).action == Action.ACCEPT


def test_uncertain_threshold_needs_observation(inputs):
    p,c,i,t,push=inputs
    i=replace(i,xy_m=ErrorBound(.004,.001))
    r=decide((p,c,i,t,push))
    assert (r.action,r.view_number)==(Action.OBSERVE,1)
    assert decide((p,c,i,t,push),extra_views=2).action == Action.HALT


def test_fastest_valid_strategy_and_no_permit(inputs):
    r=decide(inputs,regrasp_validated=True)
    assert r.action == Action.PUSH and 0 < r.max_push_m <= inputs[0].max_push_step_m
    assert not r.motion_enabled and r.permit is None
    p,c,i,t,push=inputs
    assert decide((p,c,i,replace(t,push_cycle_s=11.),push),regrasp_validated=True).action == Action.REGRASP


@pytest.mark.parametrize('field', ['bottom_layer','isolated','side_access_clear',
                                  'contact_control_validated','collision_checked','translation_only'])
def test_missing_push_validation_never_selects_push(inputs,field):
    p,c,i,t,push=inputs
    r=decide((p,c,i,t,replace(push,**{field:False})))
    assert r.action == Action.ACCEPT  # optional refinement may be skipped within acceptance
    r=decide((p,c,replace(i,xy_m=ErrorBound(.020,.0001)),t,replace(push,**{field:False})))
    assert r.action == Action.HALT


def test_deadline_preserves_mandatory_work_and_never_passes_bad_block(inputs):
    p,c,i,t,push=inputs
    short=replace(t,remaining_s=54.)
    assert decide((p,c,i,short,push)).action == Action.ACCEPT
    bad=replace(i,xy_m=ErrorBound(.020,.0001))
    assert decide((p,c,bad,short,push)).action == Action.HALT


@pytest.mark.parametrize('field,value',[('support_ok',False),('stable',False),
                                      ('neighbors_unchanged',False)])
def test_unsafe_never_corrects(inputs,field,value):
    p,c,i,t,push=inputs
    assert decide((p,c,replace(i,**{field:value}),t,push),regrasp_validated=True).action == Action.HALT


def test_unknown_and_occlusion_require_evidence(inputs):
    p,c,i,t,push=inputs
    for change in ({'support_ok':None},{'visible':False},{'hand_clear':False}):
        assert decide((p,c,replace(i,**change),t,push)).action == Action.OBSERVE


def test_color_rotation_height_and_layer_not_single_finger_translation(inputs):
    p,c,i,t,push=inputs
    for change in ({'color_ok':False},{'yaw_rad':ErrorBound(.05,.001)},
                   {'height_m':ErrorBound(.005,.0001)}):
        assert decide((p,c,replace(i,**change),t,push),regrasp_validated=True).action == Action.REGRASP
    c=replace(c,scope='layer')
    assert decide((p,c,replace(i,context=c),t,push)).action != Action.PUSH


def test_hysteresis_does_not_accept_trigger_band_while_correcting(inputs):
    p,c,i,t,push=inputs
    i=replace(i,xy_m=ErrorBound(.003,.0001))
    assert decide((p,c,i,t,push)).action == Action.ACCEPT
    assert decide((p,c,i,t,push),correcting=True).action == Action.PUSH


def test_stale_future_and_context_rejected(inputs):
    p,c,i,t,push=inputs
    for stamp in (8.,11.):
        assert decide((p,c,replace(i,stamp_s=stamp),t,push)).action == Action.HALT
    wrong=replace(c,calibration_hash='different')
    assert review(i,p,t,now_s=10.1,expected_context=wrong).action == Action.HALT


def test_effect_checks_all_metrics_and_bounds(inputs):
    p,c,b,t,push=inputs
    after=replace(b,observation_id='o2',stamp_s=11.,xy_m=ErrorBound(.007,.0002))
    assert compare_effect(b,after,min_progress_m=p.min_progress_m)=='IMPROVED'
    assert compare_effect(b,replace(after,xy_m=ErrorBound(.0098,.0002)),min_progress_m=p.min_progress_m)=='NO_CLEAR_PROGRESS'
    assert compare_effect(b,replace(after,yaw_rad=ErrorBound(.05,.001)),min_progress_m=p.min_progress_m)=='WORSENED'
    assert compare_effect(b,replace(after,neighbors_unchanged=False),min_progress_m=p.min_progress_m)=='UNSAFE_OR_UNKNOWN'


def test_session_no_replay_no_parallel_attempt(inputs):
    p,c,b,t,push=inputs
    s=CorrectionSession(c,p,started_s=10.)
    proposal=decide(inputs)
    s.stage(proposal,b,now_s=10.1)
    with pytest.raises(ValueError):s.stage(proposal,b,now_s=10.2)
    after=replace(b,observation_id='o2',stamp_s=11.,xy_m=ErrorBound(.007,.0002))
    assert s.finish(after,now_s=11.1,execution_succeeded=True,actual_push_m=.001,settled_and_retracted=True)=='IMPROVED'
    with pytest.raises(ValueError):s.stage(proposal,b,now_s=11.2)
    assert s.state=='HALTED'


@pytest.mark.parametrize('mode',['no_progress','overpush','no_retract','worse','failed'])
def test_session_stops_failed_or_unhelpful_attempt(inputs,mode):
    p,c,b,t,push=inputs
    s=CorrectionSession(c,p,started_s=10.)
    s.stage(decide(inputs),b,now_s=10.1)
    after=replace(b,observation_id='o2',stamp_s=11.,xy_m=ErrorBound(.007,.0002))
    if mode=='no_progress':after=replace(after,xy_m=b.xy_m)
    if mode=='worse':after=replace(after,xy_m=ErrorBound(.012,.0001))
    s.finish(after,now_s=11.1,execution_succeeded=mode!='failed',
             actual_push_m=.003 if mode=='overpush' else .001,
             settled_and_retracted=mode!='no_retract')
    assert s.state=='HALTED'


def test_session_success_and_expiry(inputs):
    p,c,b,t,push=inputs
    s=CorrectionSession(c,p,started_s=10.)
    s.stage(decide(inputs),b,now_s=10.1)
    after=replace(b,observation_id='o2',stamp_s=11.,xy_m=ErrorBound(.001,.0001))
    assert s.finish(after,now_s=11.1,execution_succeeded=True,actual_push_m=.001,settled_and_retracted=True)=='TARGET_REACHED'
    assert s.state=='COMPLETE'
    late=CorrectionSession(c,p,started_s=0.)
    with pytest.raises(ValueError):late.stage(decide(inputs),b,now_s=30.)


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1.])
def test_invalid_numeric_inputs_rejected(inputs,bad):
    with pytest.raises(ValueError):ErrorBound(bad,0.)
    with pytest.raises(ValueError):replace(inputs[0],max_push_step_m=bad)


def test_unconfigured_template_has_no_field_defaults():
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    template=json.loads((root/'config/planning/placement_review.template.json').read_text())
    assert template['motion_enabled'] is False
    assert template['xy_m']['trigger'] is None and template['push_response_model_id'] is None


def test_cumulative_budget_and_attempt_limit(inputs):
    p,c,b,t,push=inputs
    for policy in (replace(p,max_attempts=1),replace(p,max_total_push_m=.002)):
        s=CorrectionSession(c,policy,started_s=10.)
        proposal=review(b,policy,t,now_s=10.1,expected_context=c,push=push)
        s.stage(proposal,b,now_s=10.1)
        after=replace(b,observation_id='o2',stamp_s=11.,xy_m=ErrorBound(.007,.0002))
        assert s.finish(after,now_s=11.1,execution_succeeded=True,actual_push_m=.001,
                        settled_and_retracted=True)=='IMPROVED'
        next_proposal=review(after,policy,t,now_s=11.1,expected_context=c,push=push,correcting=True)
        with pytest.raises(ValueError):s.stage(next_proposal,after,now_s=11.2)
        assert s.state=='HALTED'


def test_invalid_capability_and_time_rollback(inputs):
    with pytest.raises(ValueError):PushEligibility(bottom_layer='yes')
    p,c,b,t,push=inputs
    s=CorrectionSession(c,p,started_s=10.)
    with pytest.raises(ValueError):s.stage(decide(inputs),b,now_s=9.)
    assert s.state=='HALTED'


def test_shadow_demo_has_no_hardware_and_stops_no_progress():
    import runpy
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    report=runpy.run_path(str(root/'tools/placement_review_demo.py'))['run_demo']()
    assert report['synthetic'] and report['commands_sent']==0 and report['permit'] is None
    assert report['no_progress_session']['state']=='HALTED'
    assert report['cases']['no_time_and_unacceptable']['action']==Action.HALT
