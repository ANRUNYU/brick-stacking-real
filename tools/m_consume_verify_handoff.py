"""Consume indexed V handoffs offline without filling missing M references."""
import argparse,json,hashlib
from collections import Counter
from pathlib import Path
from brick_stacking.planning.placement_bridge import BundleBinding
from brick_stacking.planning.verify_handoff_consumer import consume_handoff


def consume(root):
    index=root/'docs/team/B/evidence/field_20261110/verify_handoff_index_v0.1.json'
    spec=json.loads(index.read_text(encoding='utf-8'));reports={};hashes={}
    for session in spec['sessions']:
        bp=root/session['bundles'];hp=root/session['handoff']
        bundles=[json.loads(x) for x in bp.read_text(encoding='utf-8').splitlines() if x.strip()]
        handoff=json.loads(hp.read_text(encoding='utf-8'))
        sidecars=handoff['localized_review_handoffs']
        if len(bundles)!=len(sidecars):raise ValueError('handoff/frame count mismatch')
        b=bundles[0];t=b['timing'];r=b['rgbd']
        binding=BundleBinding(r['device_id'],r['frame_id'],r['epoch'],t['host_boot_epoch'],
                              b['profile_hash'],t['error_bound_evidence_ref'],2.656)
        results=[]
        for row,bundle in zip(sidecars,bundles):
            _,diagnostic=consume_handoff(row,bundle,binding,context=None,
                        now_s=bundle['timing']['output_monotonic_s'],expected_color=session['expected_color'])
            results.append(diagnostic)
        reports[session['name']]=dict(frames=len(results),
                    status_counts=dict(Counter(x['status'] for x in results)),
                    color_counts=dict(Counter(x['color_diagnostic'] for x in results)),
                    reason_counts=dict(Counter(reason for x in results for reason in x['reasons'])),rows=results)
        for path in (bp,hp):hashes[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(schema_version='m-v-handoff-consumption-1',v_commit='aed8a0b',sessions=reports,
                input_sha256=hashes,age_checked_at='recorded output only',live_tested=False,
                control_ready=False,motion_enabled=False,commands_sent=0)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();report=consume(Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:{name:v[name] for name in ('frames','status_counts','color_counts')} for k,v in report['sessions'].items()}))


if __name__=='__main__':main()
