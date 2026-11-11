"""Host helper: record one Line H teach sample (NO motion command).

Intended for robot host with linkerbot SDK. Default: read-only angles after
operator has hand-taught the pose. Does not enable motors or send moves.

Operator must physically place the arm/hand first, then confirm before running.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--phase", required=True, choices=(
        "hang", "preshape_at_block", "close_at_block", "place_ready_at_cross", "open"
    ))
    p.add_argument("--sample-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--side", default="left")
    p.add_argument("--interface", default="can2")
    p.add_argument("--operator-confirmed", action="store_true",
                   help="required: operator already placed arm/hand and confirmed")
    p.add_argument("--hand-percent", type=float, nargs=6, default=None,
                   help="optional override six percent channels; else read O6")
    p.add_argument("--block-xyz", type=float, nargs=3, default=None,
                   help="optional block translation in L_arm_root metres")
    p.add_argument("--cross-xyz", type=float, nargs=3, default=None,
                   help="optional cross translation in L_arm_root metres")
    args = p.parse_args()
    if not args.operator_confirmed:
        raise SystemExit(
            "Refuse: pass --operator-confirmed only after physically placing the arm/hand."
        )

    # Late import so unit hosts without SDK can still collect this file.
    from linkerbot import P7, O6  # type: ignore

    from brick_stacking.wrist_handoff.pose_math import (
        quat_xyzw_from_matrix,
        extrinsic_zyx_from_matrix,
    )
    from brick_stacking.wrist_handoff.teach_record import build_teach_sample

    arm = P7(side=args.side, interface_name=args.interface)
    try:
        # Rest once may be required by SDK to populate wrist raw; this changes
        # holding state. Operator must support the wrist before confirming.
        angles = arm.get_angles()
        pose = arm.forward_kinematics(list(angles))
        # Expect pose attributes x,y,z,rx,ry,rz in metres/radians extrinsic ZYX.
        import math
        from brick_stacking.wrist_handoff.pose_math import matrix_from_extrinsic_zyx

        r = matrix_from_extrinsic_zyx(float(pose.rz), float(pose.ry), float(pose.rx))
        quat = quat_xyzw_from_matrix(r)
        flange = {
            "translation_m": [float(pose.x), float(pose.y), float(pose.z)],
            "quaternion_xyzw": list(quat),
            "rpy_extrinsic_zyx_rad": [float(pose.rz), float(pose.ry), float(pose.rx)],
        }
    finally:
        try:
            arm.close()
        except Exception:
            pass

    if args.hand_percent is not None:
        hand = list(args.hand_percent)
    else:
        hand_side = "left" if args.side == "left" else "right"
        hand_iface = "can1" if args.side == "left" else "can0"
        hand = O6(side=hand_side, interface_name=hand_iface)
        try:
            hand.stop_polling()
            data = hand.angle.get_blocking(timeout_ms=500)
            hand_vals = data.angles.to_list()
        finally:
            hand.close()
        hand = [float(v) for v in hand_vals]

    block_pose = None
    if args.block_xyz is not None:
        block_pose = {
            "translation_m": [float(v) for v in args.block_xyz],
            "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
        }
    cross_pose = None
    if args.cross_xyz is not None:
        cross_pose = {
            "translation_m": [float(v) for v in args.cross_xyz],
            "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
        }

    sample = build_teach_sample(
        sample_id=args.sample_id,
        phase=args.phase,
        q_rad=[float(v) for v in angles],
        flange_pose=flange,
        hand_percent=hand,
        block_pose_base=block_pose,
        cross_pose_base=cross_pose,
        enabled_during_record=False,
        motion_commanded=False,
        notes=[
            f"recorded_at_host_monotonic={time.monotonic()}",
            "operator_hand_taught; no move commanded by this tool",
        ],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
