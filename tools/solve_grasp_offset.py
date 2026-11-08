"""Candidate T_flange_block from recorded, synchronized common-frame poses.

Reuses held_offset; does not require a pen TCP and does not solve camera extrinsics.
"""
import argparse
import json
from pathlib import Path

from brick_stacking.localization.held_offset import estimate_held_offset
from brick_stacking.localization.rigid_transforms import RigidTransform


def solve(data):
    required = ('dataset_id', 'arm_device_id', 'model_version', 'joint_mapping_version',
                'grasp_version', 'hand_binding_version', 'block_id', 'world_frame',
                'flange_frame', 'block_frame', 'clock_domain', 'epoch', 'pose_basis_version')
    for key in required:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError('explicit grasp dataset metadata required: '+key)
    if data.get('source') not in ('synthetic', 'recorded', 'real') or data.get('arm_role') != 'left' or data.get('units') != 'm':
        raise ValueError('selected-left provenance and metre units required')
    if len({data[k] for k in ('world_frame', 'flange_frame', 'block_frame')}) != 3:
        raise ValueError('three distinct frames required')
    if data.get('trial_kind') not in ('continuous_hold', 'regrasp_repeatability'):
        raise ValueError('explicit trial kind required; do not mix hold drift and regrasp error')
    rows = []
    for group in ('training', 'validation'):
        parsed = []
        for row in data[group]:
            for key in ('clock_domain', 'epoch', 'grasp_version', 'block_id', 'pose_basis_version'):
                if row.get(key) != data[key]:
                    raise ValueError('row context mismatch: '+key)
            if row.get('block_orientation_observed') is not True:
                raise ValueError('observed unambiguous block orientation required, not cube-center only')
            # RigidTransform.compose checks the two independently recorded times.
            clock = json.dumps([data['clock_domain'], data['epoch']], separators=(',', ':'))
            flange = RigidTransform(data['world_frame'], data['flange_frame'], row['T_world_flange'],
                                    data['source'], stamp_s=row['flange_stamp_s'], clock_domain=clock)
            block = RigidTransform(data['world_frame'], data['block_frame'], row['T_world_block'],
                                   data['source'], stamp_s=row['block_stamp_s'], clock_domain=clock)
            if flange.stamp_s is None or block.stamp_s is None:
                raise ValueError('capture timestamps required')
            parsed.append((row['sample_id'], flange, block))
        rows.append(parsed)
    candidate, report = estimate_held_offset(*rows, candidate_id=data['dataset_id'],
                grasp_version=data['grasp_version'],
                max_translation_residual_m=data['max_translation_residual_m'],
                max_rotation_residual_rad=data['max_rotation_residual_rad'])
    return dict(schema_version='c-flange-grasp-candidate-1', source=data['source'],
                target_frame=candidate.target_frame, source_frame=candidate.source_frame,
                T_flange_block=candidate.matrix.tolist(), units='m',
                context={k: data[k] for k in required}, trial_kind=data['trial_kind'],
                report=report, approved=False, motion_enabled=False,
                notice='relative pose consistency only; upstream camera/FK accuracy, stable grasp and collision not established')


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('input', type=Path);p.add_argument('output', type=Path)
    a = p.parse_args()
    r = solve(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x', encoding='utf-8') as f:
        json.dump(r, f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
