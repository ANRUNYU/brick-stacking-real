"""Offline eye-in-hand wrist camera extrinsic candidate solver (Mode H & Mode R).

Supports:
- observation_kind = "fixed_board_corners": Fixed-board multi-corner solver
  (`solve_wrist_camera_from_fixed_board_corners`), no head camera dependency.
- observation_kind = "head_bridge": Multi-corner registration bridged via head camera
  (`solve_wrist_camera_from_head_bridge`), automatically resolving 180-deg symmetry.
- observation_kind = "fixed_board_center": Fixed-board point solver (`solve_wrist_camera`).
No hardware access; outputs never grant execution approval.
"""
import argparse
import json
from pathlib import Path
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.wrist_camera_calibration import (
    solve_wrist_camera,
    solve_wrist_camera_from_fixed_board_corners,
    solve_wrist_camera_from_head_bridge,
)


def solve(data):
    kind = data.get('observation_kind', 'fixed_board_corners')
    if kind not in ('fixed_board_corners', 'head_bridge', 'fixed_board_center'):
        raise ValueError('observation_kind must be fixed_board_corners, head_bridge or fixed_board_center')
    fit_only = data.get('diagnostic_fit_only', False)
    if type(fit_only) is not bool:
        raise ValueError('explicit boolean diagnostic_fit_only required')
    if data.get('source') not in ('synthetic', 'recorded', 'real') or data.get('units') != 'm' or data.get('arm_role') != 'left':
        raise ValueError('left-arm source and metre units required')
    base_frame = data.get('base_frame', 'L_arm_root')
    reference_frame = data.get('reference_frame', 'L8_Link')
    camera_frame = data.get('camera_frame')
    dataset_id = data.get('dataset_id')
    if not all(isinstance(s, str) and s.strip() for s in (base_frame, reference_frame, camera_frame, dataset_id)):
        raise ValueError('explicit base_frame, reference_frame, camera_frame and dataset_id required')
    clock = json.dumps([data.get('clock_domain', 'host_monotonic'), data.get('epoch', 'unknown')], separators=(',', ':'))

    def parse_group(rows):
        parsed = []
        for row in rows:
            sid = row['sample_id']
            stamp = float(row['stamp_s'])
            a = RigidTransform(base_frame, reference_frame, row['T_base_reference'], data['source'],
                               stamp_s=stamp, clock_domain=clock)
            if kind == 'head_bridge':
                parsed.append((sid, a, row['corners_base_m'], row['corners_wrist_m'], stamp, clock))
            elif kind == 'fixed_board_corners':
                parsed.append((sid, a, row['corners_wrist_m'], stamp, clock))
            else:
                parsed.append((sid, a, row['center_wrist_m'], stamp, clock))
        return parsed

    train = parse_group(data['training'])
    val = parse_group(data.get('validation', []))

    if kind == 'head_bridge':
        tf, report = solve_wrist_camera_from_head_bridge(
            train, val,
            camera_frame=camera_frame,
            candidate_id=dataset_id,
            max_residual_m=float(data.get('max_translation_residual_m', 0.01)),
            min_center_span_m=float(data.get('min_center_span_m', 0.04)),
            diagnostic_fit_only=fit_only,
        )
    elif kind == 'fixed_board_corners':
        tf, report = solve_wrist_camera_from_fixed_board_corners(
            train, val,
            board_object_points_m=data['board_object_points_m'],
            camera_frame=camera_frame,
            candidate_id=dataset_id,
            max_residual_m=float(data.get('max_translation_residual_m', 0.01)),
            diagnostic_fit_only=fit_only,
        )
    else:
        tf, report = solve_wrist_camera(
            train, val,
            camera_frame=camera_frame,
            candidate_id=dataset_id,
            max_residual_m=float(data.get('max_translation_residual_m', 0.01)),
            max_condition_number=float(data.get('max_condition_number', 1e5)),
            diagnostic_fit_only=fit_only,
        )

    return dict(
        schema_version=report['schema_version'],
        source=data['source'],
        dataset_id=dataset_id,
        observation_kind=kind,
        base_frame=base_frame,
        reference_frame=tf.target_frame,
        camera_frame=tf.source_frame,
        T_reference_camera=tf.matrix.tolist(),
        report=report,
        approved=False,
        motion_enabled=False,
        units=dict(length='m', angle='rad', quaternion='xyzw'),
    )


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    result = solve(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
