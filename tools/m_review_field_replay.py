"""Replay V field exports through M source audit. No device connection or commands."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from brick_stacking.planning.placement_bridge import BundleBinding,audit_bundle
from brick_stacking.localization.ruler_reference import audit_ruler


def replay(root):
    field=root/'docs/team/B/evidence/field_20261110'
    cases={};hashes={}
    for name in ('verify_pre_grasp','verify_empty','verify_green'):
        path=field/(name+'_observation_bundles.jsonl')
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        first=rows[0];t=first['timing'];r=first['rgbd']
        # Freeze source binding per recording, not from each incoming frame.
        binding=BundleBinding(r['device_id'],r['frame_id'],r['epoch'],t['host_boot_epoch'],
                              first['profile_hash'],t['error_bound_evidence_ref'],2.656)
        reports=[audit_bundle(row,binding,now_s=row['timing']['output_monotonic_s'],
                              expected_color='red') for row in rows]
        cases[name]=dict(frames=len(rows),binding=asdict(binding),
                         color_counts=dict(Counter(x['observed_candidate_color_check'] for x in reports)),
                         source_checks_passed=sum(x['source_checks_passed'] for x in reports),
                         problem_counts=dict(Counter(p for x in reports for p in x['problems'])),
                         placement_verdicts=dict(Counter(x['placement_verdict'] for x in reports)),
                         reports=reports)
        hashes[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    ref=field/'independent_ruler_reference_v0.1.json'
    hashes[ref.relative_to(root).as_posix()]=hashlib.sha256(ref.read_bytes()).hexdigest()
    return dict(schema_version='m-placement-field-replay-1',source='recorded_field_exports',
                live_freshness_checked=False,age_evaluated_at='recorded output; not current wall time',
                cases=cases,ruler=audit_ruler(json.loads(ref.read_text(encoding='utf-8'))),
                input_sha256=hashes,control_ready=False,motion_enabled=False,commands_sent=0,
                remaining=['independent frame bridge','target/region association',
                           'localized bounded errors','support/stability/retraction evidence',
                           'approved execution context and full Gate'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=replay(Path(__file__).resolve().parents[1])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(cases={k:{n:v[n] for n in ('frames','color_counts','source_checks_passed','placement_verdicts')} for k,v in report['cases'].items()},ruler_status=report['ruler']['status'],commands_sent=0)))


if __name__=='__main__':main()
