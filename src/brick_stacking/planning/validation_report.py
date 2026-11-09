"""Aggregate immutable trial evidence without promoting mock/ACK to real success."""
import math
import numpy as np

STATUSES={'PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED','UNKNOWN'}
VERDICTS={'PASS','FAIL','UNKNOWN'}


def summarize_trials(rows):
    rows=tuple(rows);ids=[];groups={}
    for r in rows:
        required=('run_id','stage','configuration_version','calibration_version','scene_version','clock_domain','epoch')
        if any(not isinstance(r.get(k),str) or not r[k] for k in required):raise ValueError('identified versioned trial required')
        if r['run_id'] in ids:raise ValueError('duplicate run_id')
        ids.append(r['run_id'])
        if r.get('source') not in ('mock','recorded','real') or type(r.get('assisted')) is not bool or type(r.get('hardware_actions')) is not bool:
            raise ValueError('explicit source, assistance and hardware action provenance required')
        if r['source']=='mock' and r['hardware_actions']:raise ValueError('mock cannot claim hardware actions')
        if r.get('execution_status') not in STATUSES:raise ValueError('execution ACK is not a completion status')
        for k in ('pick_verdict','placement_verdict','stability_verdict'):
            if r.get(k) not in VERDICTS:raise ValueError('explicit verification verdicts required')
        start,end=r.get('start_stamp_s'),r.get('end_stamp_s')
        if any(not isinstance(t,(int,float)) or not math.isfinite(t) or t<0 for t in (start,end)) or end<start:
            raise ValueError('ordered same-domain timestamps required')
        if r.get('placement_error_xyz_m') is not None:
            e=np.asarray(r['placement_error_xyz_m'],float)
            if e.shape!=(3,) or not np.isfinite(e).all():raise ValueError('finite xyz errors in metres required')
        key=tuple(r[k] for k in ('stage','source','assisted','configuration_version','calibration_version','scene_version','clock_domain','epoch'))
        groups.setdefault(key,[]).append(r)
    output=[]
    for key,items in groups.items():
        evidence_success=[r for r in items if r['execution_status']=='SUCCEEDED' and all(r[k]=='PASS' for k in ('pick_verdict','placement_verdict','stability_verdict'))]
        real_success=[r for r in evidence_success if r['source']=='real' and not r['assisted'] and r['hardware_actions']]
        known=[r['placement_error_xyz_m'] for r in items if r.get('placement_error_xyz_m') is not None]
        stats=None
        if known:
            errors=np.abs(np.asarray(known));norm=np.linalg.norm(errors,axis=1)
            stats=dict(n=len(known),p50_abs_xyz_m=np.median(errors,axis=0).tolist(),p95_abs_xyz_m=np.percentile(errors,95,axis=0).tolist(),max_abs_xyz_m=errors.max(axis=0).tolist(),p95_norm_m=float(np.percentile(norm,95)))
        output.append(dict(stage=key[0],source=key[1],assisted=key[2],configuration_version=key[3],calibration_version=key[4],scene_version=key[5],clock_domain=key[6],epoch=key[7],n_total=len(items),n_verified_execution_success=len(evidence_success),n_real_unassisted_verified_success=len(real_success),n_unknown_placement=sum(r['placement_verdict']=='UNKNOWN' for r in items),n_error_missing=len(items)-len(known),error_statistics=stats,run_ids=[r['run_id'] for r in items]))
    return dict(schema_version='c-trial-report-1',groups=output,n_total=len(rows),acceptance='INCONCLUSIVE',
                reason='descriptive evidence only; frozen physical acceptance criteria must be evaluated separately',motion_enabled=False)
