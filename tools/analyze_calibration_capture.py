"""Real/recorded RGB-D precheck: diagnostics only, no external TF approval.

python tools/analyze_calibration_capture.py capture_dir output.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def analyze(directory):
    report = json.loads((directory/'camera_report.json').read_text(encoding='utf-8'))
    if report.get('result') != 'CAPTURED' or report.get('cleanup_errors'):
        raise ValueError('successful bounded capture and clean shutdown required')
    depths, stamps, hashes = [], [], {}
    common = None
    for entry in report['frames']:
        name = entry['file']
        if Path(name).name != name:
            raise ValueError('capture file must be a basename')
        path = directory/name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with np.load(path, allow_pickle=False) as f:
            meta = json.loads(str(f['metadata'].item()))
            d, rgb, k = f['depth_m'], f['rgb'], f['k']
            identity = (meta['camera_id'], meta['frame_id'], meta['clock_domain'], d.shape)
            if common is not None and identity != common:
                raise ValueError('camera/frame/epoch/profile changed')
            common = identity
            if meta['camera_id'] != report['selected']['serial'] or meta['depth_unit'] != 'm':
                raise ValueError('identity or units mismatch')
            if rgb.shape != (*d.shape,3) or not np.isfinite(k).all():
                raise ValueError('invalid dimensions or intrinsics')
            stamps.append(meta['stamp_s'])
            depths.append(np.where(np.isfinite(d)&(d>0),d,np.nan))
    if len(depths)<2 or np.any(np.diff(stamps)<=0):
        raise ValueError('multiple strictly ordered frames required')
    stack=np.stack(depths)
    # Only pixels valid in every frame; avoids filling holes or comparing masks.
    stable=np.isfinite(stack).all(axis=0)
    deviations=np.std(stack[:,stable],axis=0)
    return {'source':'real_recorded','camera_id':common[0], 'clock_domain':common[2],
            'n_frames':len(depths),'shape':list(common[3]),
            'device_capture_span_s':float(stamps[-1]-stamps[0]),
            'all_frames_valid_pixel_ratio':float(stable.mean()),
            'temporal_std_p50_m':float(np.median(deviations)) if deviations.size else None,
            'temporal_std_p95_m':float(np.percentile(deviations,95)) if deviations.size else None,
            'max_rgb_depth_skew_ms':max(e['skew_ms'] for e in report['frames']),
            'sha256':hashes, 'approved':False, 'motion_enabled':False,
            'limitations':['whole-image temporal variation includes scene motion',
                          'not absolute depth accuracy or spatial registration acceptance',
                          'no host/device clock mapping, arm/world extrinsic or TCP']}


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('directory',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    result=analyze(args.directory)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2))


if __name__=='__main__': main()
