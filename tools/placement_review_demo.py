"""Synthetic shadow demo only. Does not import ROS/SDK or grant motion permits."""
import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from brick_stacking.planning.placement_review import (
    Band, Context, ErrorBound, Inspection, PushEligibility, ReviewPolicy, TimeBudget, review,
)
from brick_stacking.execution.correction_session import CorrectionSession


def run_demo():
    # All values below are synthetic fixtures, never installed as a field profile.
    policy = ReviewPolicy('SYNTHETIC_ONLY', Band(.002,.004,.015), Band(.002,.004,.008),
                          Band(.02,.04,.08), .002,.004,2,20.,.0005,1.,2)
    context = Context('demo-block','block','demo-table','demo-scene','mock-cal',
                      'mock-profile','demo-epoch','synthetic-monotonic')
    initial = Inspection(context,'demo-1',10.,ErrorBound(.010,.0002),
                         ErrorBound(.0005,.0001),ErrorBound(.005,.001),
                         True,True,True,True,True,True)
    budget = TimeBudget(100.,40.,10.,2.,5.,10.)
    eligibility = PushEligibility('MOCK_RESPONSE','MOCK_CONTACT',True,True,True,True,True,True)
    def choose(i, t=budget, **kwargs):
        return review(i,policy,t,now_s=10.1,expected_context=context,
                      push=eligibility,**kwargs)
    cases = {
        'within_band': choose(replace(initial,xy_m=ErrorBound(.003,.0001))),
        'uncertain': choose(replace(initial,xy_m=ErrorBound(.004,.001))),
        'push_candidate': choose(initial,regrasp_validated=True),
        'no_time_but_acceptable': choose(initial,replace(budget,remaining_s=54.)),
        'no_time_and_unacceptable': choose(replace(initial,xy_m=ErrorBound(.020,.0001)),
                                          replace(budget,remaining_s=54.)),
        'unstable': choose(replace(initial,stable=False)),
    }
    session = CorrectionSession(context,policy,started_s=10.)
    session.stage(cases['push_candidate'],initial,now_s=10.1)
    after = replace(initial,observation_id='demo-2',stamp_s=11.,xy_m=ErrorBound(.0099,.0002))
    session.finish(after,now_s=11.1,execution_succeeded=True,actual_push_m=.001,
                   settled_and_retracted=True)
    return dict(schema_version='placement-review-shadow-demo-1',synthetic=True,
                platform_tested=False,motion_enabled=False,commands_sent=0,permit=None,
                policy=asdict(policy),cases={k:asdict(v) for k,v in cases.items()},
                no_progress_session=dict(state=session.state,events=session.events),
                notice='Mock facts and thresholds only; not a physical push model or motion plan.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='new report file; never overwrite')
    args=parser.parse_args()
    report=run_demo()
    report['created_utc']=datetime.now(timezone.utc).isoformat()
    report['source_sha256']={
        name:hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
        for name in ('src/brick_stacking/planning/placement_review.py',
                     'src/brick_stacking/execution/correction_session.py')}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(output=str(args.output.resolve()),synthetic=True,commands_sent=0,
                         cases={k:v['action'] for k,v in report['cases'].items()},
                         no_progress_state=report['no_progress_session']['state'])))


if __name__=='__main__':
    main()
