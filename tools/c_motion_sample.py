"""C→A offline seven-axis sample. Never connects to a device.

Run after editable install or with PYTHONPATH=src.
"""
import argparse
import json
from pathlib import Path
from brick_stacking.planning.joint_trajectory import JointLimits, build_offline_trajectory


def sample():
    names = tuple(f'J{i}' for i in range(1, 8))
    # Invented limits ONLY for synthetic tests, not manufacturer values.
    limits = JointLimits(names, (-1.,)*7, (1.,)*7, (.1,)*7, (.2,)*7,
                         'SYNTHETIC-NOT-A-ROBOT', 'synthetic')
    return build_offline_trajectory(
        [[0.]*7, [.05,-.03,.02,0.,0.,.01,-.01], [0.]*7], limits,
        scene_version='synthetic-scene-1', calibration_version='synthetic-calibration-1',
        clock_domain='synthetic_monotonic', epoch='synthetic-epoch-1',
        state_stamp_s=1., now_s=1.01, max_age_s=.1, start_tolerance_rad=.001,
        expected_start_rad=[0.]*7)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(sample(), f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
