"""Provisional exposure-time / upstream joint association; no device access.

Uses measured SDK global timestamps plus explicit host clock bridges. Never
substitutes camera arrival or device time for exposure time. No approval or FK.
"""
import argparse
import bisect
import json
import math
from pathlib import Path
import struct


def associate(cycles,camera,*,max_bracket_gap_s,max_bracket_step_rad,max_rgb_depth_skew_s):
    for value in (max_bracket_gap_s,max_bracket_step_rad,max_rgb_depth_skew_s):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError('explicit positive association quality thresholds required')
    if camera.get('result')!='CAPTURED' or not camera.get('frames') or camera.get('errors') or camera.get('cleanup_errors'):
        raise ValueError('complete camera recording required')
    axes={i:[] for i in range(61,66)};epochs=set();sources=set()
    for cycle in cycles:
        if cycle.get('arm_role')!='left' or cycle.get('interface')!='can2' or cycle.get('clock_domain')!='host_monotonic' or cycle.get('schema_version')!='c-left-readonly-probe-1':
            raise ValueError('identified left five-axis host-monotonic READ recording required')
        epoch=cycle.get('epoch','')
        if not epoch.startswith('linux_boot:') or cycle.get('source') not in ('real','recorded','synthetic'):
            raise ValueError('explicit boot epoch and source required')
        epochs.add(epoch);sources.add(cycle['source']);seen=set()
        for row in cycle['received']:
            mid=row['motor_id']
            if mid not in axes:continue
            if mid in seen:raise ValueError('duplicate joint within cycle')
            seen.add(mid);raw=bytes.fromhex(row['raw_hex'])
            if not 5<=len(raw)<=8 or raw[0]!=6:raise ValueError('position READ06 evidence required')
            q=struct.unpack('<f',raw[1:5])[0];stamp=row['host_receive_monotonic_s']
            if not math.isfinite(q) or q!=row['position_sdk_rad'] or not math.isfinite(stamp) or stamp<0:
                raise ValueError('raw/state/time mismatch')
            if axes[mid] and stamp<=axes[mid][-1][0]:raise ValueError('joint samples not strictly increasing')
            axes[mid].append((stamp,q))
    if len(epochs)!=1 or len(sources)!=1 or any(len(v)<2 for v in axes.values()):
        raise ValueError('one source/boot epoch and bracketing states for all five joints required')
    rows=[]
    for frame in camera['frames']:
        obs=frame.get('clock_observation',{})
        if obs.get('schema_version')!='c-orbbec-clock-observation-1':raise ValueError('measured SDK clock observation required')
        clock=obs.get('sdk_host_clock_type');anchor=obs['host_bridge']
        origin=anchor['realtime_s'] if clock=='REALTIME' else anchor['monotonic_raw_s'] if clock=='MONOTONIC' else None
        before,after=anchor['monotonic_before_s'],anchor['monotonic_after_s']
        if origin is None or not all(math.isfinite(v) for v in (origin,before,after)) or after<before:raise ValueError('explicit valid host clock bridge required')
        stamps=[]
        for label in ('color','depth'):
            f=obs['frames'][label];global_us=f['global_timestamp_us']
            if isinstance(global_us,bool) or not isinstance(global_us,int) or global_us<=0 or f.get('global_available') is not True:
                raise ValueError('global exposure timestamp unavailable; no arrival/device fallback')
            stamp=global_us/1e6-origin+(before+after)/2
            if abs(stamp-f['global_host_monotonic_candidate_s'])>1e-8:raise ValueError('clock bridge result mismatch')
            stamps.append(stamp)
        if abs(stamps[0]-stamps[1])>max_rgb_depth_skew_s:raise ValueError('RGB/depth exposure mismatch')
        target=stamps[1];positions={};brackets={}
        for mid,values in axes.items():
            times=[v[0] for v in values];index=bisect.bisect_right(times,target)
            if index==0 or index==len(values):raise ValueError('exposure outside joint coverage; no extrapolation')
            (a,qa),(b,qb)=values[index-1:index+1]
            if b-a>max_bracket_gap_s or abs(qb-qa)>max_bracket_step_rad:
                raise ValueError('joint bracket gap/step exceeds predeclared association threshold')
            name=f'L{mid-60}_Joint';positions[name]=qa+(qb-qa)*(target-a)/(b-a)
            brackets[name]=dict(receive_interval_s=[a,b],positions_sdk_rad=[qa,qb],linear_speed_rad_s=(qb-qa)/(b-a))
        rows.append(dict(image_file=frame['file'],association_host_monotonic_s=target,
                         joint_positions_sdk_rad=positions,joint_brackets=brackets,
                         clock_observation=obs,quality='PROVISIONAL',
                         notice='linear joint interpolation at SDK mapped depth exposure; SDK fit error and interpolation model error not independently bounded'))
    return dict(schema_version='c-camera-upstream-association-1',source=next(iter(sources)),
                clock_domain='host_monotonic',epoch=next(iter(epochs)),reference_frame='L5_Link',
                samples=rows,approved=False,motion_enabled=False,calibration_sample_valid=False,
                timing_acceptance='NOT_VALIDATED',
                scope='candidate association diagnostics, not a calibration matrix, complete seven-axis state or motion permission')


def associate_qualified_frames(cycles,camera,**thresholds):
    """Keep independently qualified images; retain every rejected frame reason."""
    results=[];rejections=[]
    for frame in camera.get('frames',[]):
        one=dict(camera,frames=[frame])
        try:results.append(associate(cycles,one,**thresholds))
        except ValueError as exc:rejections.append(dict(image_file=frame.get('file'),reason=str(exc)))
    if not results:raise ValueError('no exposure-qualified image: '+str(rejections))
    combined=dict(results[0]);combined['samples']=[row for r in results for row in r['samples']]
    combined['frame_rejections']=rejections
    combined['frame_qualification']='independent per-image brackets; unchanged thresholds; all rejections retained'
    return combined


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('capture_directory',type=Path);p.add_argument('output',type=Path)
    for key in ('max-bracket-gap-s','max-bracket-step-rad','max-rgb-depth-skew-s'):p.add_argument('--'+key,type=float,required=True)
    p.add_argument('--keep-qualified-frames',action='store_true')
    a=p.parse_args();root=a.capture_directory
    qualify=associate_qualified_frames if a.keep_qualified_frames else associate
    r=qualify(json.loads((root/'joint_cycles.json').read_text()),json.loads((root/'camera/camera_report.json').read_text()),
                max_bracket_gap_s=a.max_bracket_gap_s,max_bracket_step_rad=a.max_bracket_step_rad,max_rgb_depth_skew_s=a.max_rgb_depth_skew_s)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
