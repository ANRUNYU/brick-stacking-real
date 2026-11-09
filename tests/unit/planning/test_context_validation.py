import pytest
from brick_stacking.planning.context_validation import CONTEXT_KEYS,validate_plan_context


def check(a,b,**kw):
    args=dict(created_stamp_s=1,expires_stamp_s=2,now_s=1.5);args.update(kw)
    return validate_plan_context(a,b,**args)


def test_matching_context_is_not_motion_permission():
    a={k:'synthetic' for k in CONTEXT_KEYS}
    r=check(a,a)
    assert r['context_consistency']=='PASS' and not r['motion_enabled']


@pytest.mark.parametrize('key',CONTEXT_KEYS)
def test_every_changed_or_unknown_dependency_invalidates(key):
    a={k:'synthetic' for k in CONTEXT_KEYS};b=dict(a);b[key]='new'
    assert check(a,b)['context_consistency']=='FAIL'
    b[key]=None
    assert 'UNKNOWN:'+key in check(a,b)['reasons']


@pytest.mark.parametrize('time',[0,2,3,float('nan')])
def test_expiry_future_and_nan(time):
    a={k:'synthetic' for k in CONTEXT_KEYS}
    assert check(a,a,now_s=time)['context_consistency']=='FAIL'
