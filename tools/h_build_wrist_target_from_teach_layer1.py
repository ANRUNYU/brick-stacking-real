"""Build non-executable wrist-target from grasp_ready + place_ready_layer1 teaches.

Uses the same build_wrist_target() core as tools/h_build_wrist_target.py.
Official flange poses are locked-URDF FK (never SDK FK). No motion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.wrist_handoff.constants import LOCKED_URDF_SHA256
from brick_stacking.wrist_handoff.pose_math import pose_dict_from_matrix
from brick_stacking.wrist_handoff.wrist_target import build_wrist_target, canonical_sha256

J2_LOWER = -0.07
URDF = Path("config/models/p7_left/p7__left.urdf")


def _lf_urdf_bytes() -> bytes:
    return URDF.read_bytes().replace(b"\r\n", b"\n")


def locked_urdf_flange(q_rad: list[float]) -> tuple[dict, str]:
    payload = _lf_urdf_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    if sha != LOCKED_URDF_SHA256:
        raise SystemExit(f"Refuse: URDF sha mismatch {sha}")
    with tempfile.NamedTemporaryFile(suffix=".urdf", delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    try:
        named = {f"L{i}_Joint": float(q_rad[i - 1]) for i in range(1, 8)}
        tf, report = urdf_forward_kinematics(
            tmp_path, named, base_frame="L_arm_root", tip_frame="L8_Link"
        )
        if report.get("model_sha256") != LOCKED_URDF_SHA256:
            raise SystemExit(f"Refuse: FK model_sha256 mismatch {report.get('model_sha256')}")
    finally:
        tmp_path.unlink(missing_ok=True)
    return pose_dict_from_matrix(np.asarray(tf.matrix, float)), sha


def horizontal_xy_m(a: list[float], b: list[float]) -> float:
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("grasp_teach", type=Path)
    p.add_argument("place_teach", type=Path)
    p.add_argument("obstacles", type=Path, help="two_row_blocks localize JSON")
    p.add_argument("output", type=Path)
    p.add_argument("--table-board-hash", default=None)
    args = p.parse_args()

    grasp = json.loads(args.grasp_teach.read_text(encoding="utf-8-sig"))
    place = json.loads(args.place_teach.read_text(encoding="utf-8-sig"))
    obs = json.loads(args.obstacles.read_text(encoding="utf-8-sig"))

    if place.get("phase") != "place_ready_layer1":
        raise SystemExit(f"Refuse: place teach phase must be place_ready_layer1, got {place.get('phase')}")
    if "193108" in str(args.place_teach):
        raise SystemExit("Refuse: do not use far-end teach_place_ready_layer1_20261111_193108.json")

    g_q = [float(x) for x in grasp["q_rad"]]
    p_q = [float(x) for x in place["q_rad"]]
    if len(g_q) != 7 or len(p_q) != 7:
        raise SystemExit("Refuse: both teaches need 7-axis q_rad")
    if g_q[1] < J2_LOWER or p_q[1] < J2_LOWER:
        raise SystemExit(f"Refuse: J2 below {J2_LOWER}: grasp={g_q[1]} place={p_q[1]}")

    g_prov = list(grasp.get("seed_provenance") or [])
    p_prov = list(place.get("seed_provenance") or [])
    for name, prov in (("grasp", g_prov), ("place", p_prov)):
        if len(prov) != 7:
            raise SystemExit(f"Refuse: {name} seed_provenance must have 7 entries")
        if prov[5] == "sdk_audited" or prov[6] == "sdk_audited":
            raise SystemExit(f"Refuse: {name} J6/J7 must not be sdk_audited")

    g_pose, urdf_sha = locked_urdf_flange(g_q)
    p_pose, urdf_sha2 = locked_urdf_flange(p_q)
    if urdf_sha != urdf_sha2:
        raise SystemExit("Refuse: inconsistent URDF sha between FK calls")

    blocks = list(obs.get("blocks") or [])
    if len(blocks) != 10:
        raise SystemExit(f"Refuse: expected 10 obstacle blocks after split, got {len(blocks)}")

    place_t = [float(x) for x in p_pose["translation_m"]]
    ranked = []
    for i, b in enumerate(blocks):
        t = b.get("translation_m_L_arm_root")
        if t is None:
            continue
        d = horizontal_xy_m(place_t, [float(x) for x in t])
        ranked.append((d, i, b))
    ranked.sort(key=lambda x: x[0])
    if len(ranked) < 2:
        raise SystemExit("Refuse: need >=2 blocks with base translations for clearance note")
    nearest_two = [
        {
            "rank": 1,
            "color": ranked[0][2]["color"],
            "row_id": ranked[0][2].get("row_id"),
            "index_in_row": ranked[0][2].get("index_in_row"),
            "translation_m_L_arm_root": ranked[0][2]["translation_m_L_arm_root"],
            "horizontal_xy_clearance_m": ranked[0][0],
            "uncertain": bool(ranked[0][2].get("uncertain")),
        },
        {
            "rank": 2,
            "color": ranked[1][2]["color"],
            "row_id": ranked[1][2].get("row_id"),
            "index_in_row": ranked[1][2].get("index_in_row"),
            "translation_m_L_arm_root": ranked[1][2]["translation_m_L_arm_root"],
            "horizontal_xy_clearance_m": ranked[1][0],
            "uncertain": bool(ranked[1][2].get("uncertain")),
        },
    ]

    green = next((b for b in blocks if b.get("color") == "green"), None)
    if green is None:
        raise SystemExit("Refuse: green obstacle missing")

    # Obstacle payload is a copy; source localize JSON is not modified.
    obstacles = {
        "schema_version": "line-h-wrist-obstacles-two-row-0.1",
        "source_localize": str(args.obstacles).replace("\\", "/"),
        "source_capture": obs.get("source_capture"),
        "operator_confirmed": True,
        "operator_confirmed_note": "field visual confirm of overlay registration; source localize file left unchanged",
        "accuracy_claim": "FIT_ONLY",
        "edge_m": obs.get("edge_m", 0.05),
        "edge_m_note": obs.get("edge_m_note", "assumed_0.05_m_no_new_field_measurement"),
        "calibration": obs.get("calibration"),
        "counts": obs.get("counts"),
        "rows": obs.get("rows"),
        "blocks": blocks,
        "green_block": {
            "uncertain": bool(green.get("uncertain")),
            "uncertain_reasons": list(green.get("uncertain_reasons") or []),
            "plane_residual_p95_m": (green.get("detection") or {}).get("plane_residual_p95_m"),
            "translation_m_L_arm_root": green.get("translation_m_L_arm_root"),
            "note": "kept as obstacle with residual/uncertain; FIT_ONLY",
        },
        "place_to_nearest_blocks_horizontal_xy_m": nearest_two,
        "executable": False,
        "control_ready": False,
        "motion_enabled": False,
    }

    out = build_wrist_target(
        targets=[
            {
                "name": "grasp_ready",
                "translation_m": g_pose["translation_m"],
                "quaternion_xyzw": g_pose["quaternion_xyzw"],
                "rpy_extrinsic_zyx_rad": g_pose.get("rpy_extrinsic_zyx_rad"),
                "seed_q_rad": g_q,
                "seed_provenance": g_prov,
                "note": "locked-URDF FK of teach_grasp_ready_rerecord seed; not SDK FK",
            },
            {
                "name": "place_ready",
                "translation_m": p_pose["translation_m"],
                "quaternion_xyzw": p_pose["quaternion_xyzw"],
                "rpy_extrinsic_zyx_rad": p_pose.get("rpy_extrinsic_zyx_rad"),
                "seed_q_rad": p_q,
                "seed_provenance": p_prov,
                "note": "place_ready_layer1 near-end red-heavy row; locked-URDF FK; not mid/handoff",
            },
        ],
        table_board_hash=args.table_board_hash,
        relative_version=None,
        hand_preset_pack_version=None,
        source_evidence=[
            str(args.grasp_teach).replace("\\", "/"),
            str(args.place_teach).replace("\\", "/"),
            str(args.obstacles).replace("\\", "/"),
        ],
        status="PLANNED_OFFLINE",
        notes=[
            "grasp_ready -> place_ready_layer1 only; not full 10-pyramid places",
            "flange poses are locked-URDF FK of taught seeds",
            "obstacles: two-row blocks after near-row red split (10 blocks)",
            "C35 FIT_ONLY; not a live motion permit",
            f"place_xy_to_nearest_block_m={nearest_two[0]['horizontal_xy_clearance_m']:.6f}",
            f"place_xy_to_second_nearest_block_m={nearest_two[1]['horizontal_xy_clearance_m']:.6f}",
            f"created_utc={datetime.now(timezone.utc).isoformat()}",
        ],
    )
    out["motion_enabled"] = False
    out["place_phase"] = "place_ready_layer1"
    out["obstacles"] = obstacles
    out["place_clearance_horizontal_xy_m"] = {
        "nearest": nearest_two[0],
        "second_nearest": nearest_two[1],
        "frame": "L_arm_root",
        "method": "hypot(dx,dy) using block model centers",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    print("canonical_sha256", canonical_sha256(out))
    print("targets", [t["name"] for t in out["targets"]])
    print("obstacles", len(blocks))
    print("nearest_m", nearest_two[0]["horizontal_xy_clearance_m"])
    print("second_m", nearest_two[1]["horizontal_xy_clearance_m"])
    print("green_uncertain", green.get("uncertain"), green.get("uncertain_reasons"))


if __name__ == "__main__":
    main()
