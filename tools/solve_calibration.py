"""Read-only point-pair dataset solver: python tools/solve_calibration.py input.json output.json."""
import argparse
import json
from pathlib import Path
from brick_stacking.localization.calibration import solve_point_pairs, error_report


def solve(data):
    required = ('dataset_id', 'source_frame', 'target_frame', 'device_serial',
                'profile', 'clock_domain', 'epoch', 'source')
    if any(not data.get(k) for k in required) or data.get('units') != 'm':
        raise ValueError('metadata and explicit metre units required')
    if data['source'] not in ('synthetic', 'recorded', 'real'):
        raise ValueError('invalid source')
    profile = data['profile']
    if not isinstance(profile, dict) or any(type(profile.get(k)) is not int or profile[k] <= 0 for k in ('width', 'height')):
        raise ValueError('explicit image dimensions required')
    train, check = data['train'], data['validation']
    all_rows = train + check
    ids = [r['sample_id'] for r in all_rows]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('training and validation sample IDs must be distinct')
    import math
    for row in all_rows:
        if row.get('profile') != profile or row.get('epoch') != data['epoch'] or row.get('clock_domain') != data['clock_domain']:
            raise ValueError('profile/clock/epoch mismatch')
        if not isinstance(row.get('host_stamp_s'), (float, int)) or not math.isfinite(row['host_stamp_s']) or row['host_stamp_s'] < 0:
            raise ValueError('finite host timestamp required')
    tf = solve_point_pairs([r['source_m'] for r in train], [r['target_m'] for r in train],
                          source_frame=data['source_frame'], target_frame=data['target_frame'],
                          candidate_id=data['dataset_id'])
    return {"schema_version": "c-candidate-1", "dataset_id": data['dataset_id'],
            "source": data['source'], "matrix": tf.matrix.tolist(),
            "target_frame": tf.target_frame, "source_frame": tf.source_frame,
            "approved": False, "motion_enabled": False,
            "validation": error_report(tf, [r['source_m'] for r in check], [r['target_m'] for r in check])}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = solve(json.loads(args.input.read_text(encoding='utf-8-sig')))
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
