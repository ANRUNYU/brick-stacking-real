"""First rejected lift substep: which arm/palm link is closest to robot-side table edge.

Uses:
  - config/planning/p7_sdk_to_vendor_collision_candidate.json (SDK→vendor joint map)
  - config/planning/p7_o6_left_mount_candidate.json (L8→lh_hand_base_link)
  - robot_side_table_edge report (near-edge estimate)
  - independent footprint audit flange samples (same 9 q)

Link origins only (L1..L8 + lh_hand_base_link). Fingertips stay UNKNOWN unless a
bound hand pose is supplied; can0/can1 teach remapping is not resolved here.

Offline. approved_for_motion=false. Does not change REJECT_TABLE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from brick_stacking.localization.joint_conventions import JointConventionMap
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.tool_assembly import attach_tool_poses

ARM_URDF_HASH = "b898b9597d7d075cc5e7114d76a90d0ec514c387a5fd59411555455a6d722daa"
HAND_URDF_HASH = "e1e42ccd1ff55a28153acb025046f42d810ac97367f7bbfdaebe042d01cd75ba"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--mapping",
        type=Path,
        default=ROOT / "config/planning/p7_sdk_to_vendor_collision_candidate.json",
    )
    p.add_argument(
        "--mount",
        type=Path,
        default=ROOT / "config/planning/p7_o6_left_mount_candidate.json",
    )
    p.add_argument(
        "--arm-urdf",
        type=Path,
        default=ROOT / "artifacts/vendor_p7_left/arm.urdf",
    )
    p.add_argument(
        "--hand-urdf",
        type=Path,
        default=ROOT / "artifacts/vendor_o6_left/hand.urdf",
    )
    p.add_argument(
        "--edge-report",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/robot_side_table_edge/robot_side_edge_report.json",
    )
    p.add_argument(
        "--samples",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/independent_footprint_audit/samples.json",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/lift_part_proximity",
    )
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    mapping_doc = load(args.mapping)
    mount = load(args.mount)
    edge = load(args.edge_report)
    samples_doc = load(args.samples)

    if _sha(args.arm_urdf) != ARM_URDF_HASH:
        raise ValueError("arm.urdf hash mismatch vs mount candidate")
    if _sha(args.hand_urdf) != HAND_URDF_HASH:
        raise ValueError("hand.urdf hash mismatch vs mount candidate")
    if mapping_doc["target_model_sha256"] != ARM_URDF_HASH:
        raise ValueError("mapping target hash mismatch")
    if mapping_doc.get("approved_for_motion") or mount.get("approved_for_motion"):
        raise ValueError("refusing approved_for_motion=true inputs in this diagnostic")

    convention = JointConventionMap(
        tuple(mapping_doc["joint_names"]),
        tuple(mapping_doc["signs"]),
        tuple(mapping_doc["offsets_rad"]),
        mapping_doc["source_model_sha256"],
        mapping_doc["target_model_sha256"],
    )
    fixed = RigidTransform(
        "L8_Link",
        "lh_hand_base_link",
        mount["T_L8_hand_root"],
        "vendor_declared",
        mount["assembly_sha256"],
    )

    edge_mean = np.asarray(edge["edge_mean_base_m"], float)
    edge_dir = np.asarray(edge["edge_dir_base"], float)
    inward = np.asarray(edge["inward_base"], float)
    n_base = np.asarray(edge["table_normal_base"], float)
    edge_dir = edge_dir / np.linalg.norm(edge_dir)
    inward = inward / np.linalg.norm(inward)
    n_base = n_base / np.linalg.norm(n_base)

    def metrics(xyz: np.ndarray) -> dict:
        foot = xyz - n_base * float((xyz - edge_mean) @ n_base)
        horiz = float((foot - edge_mean) @ inward)
        # Distance to infinite edge line in the table plane.
        along = float((foot - edge_mean) @ edge_dir)
        closest_on_edge = edge_mean + along * edge_dir
        planar_dist = float(np.linalg.norm(foot - closest_on_edge))
        height = float((xyz - edge_mean) @ n_base)
        return {
            "xyz_base_m": xyz.tolist(),
            "height_plane_m": height,
            "signed_robot_edge_clearance_m": horiz,
            "planar_distance_to_edge_line_m": planar_dist,
            # Outside edge (horiz<0): report how far past the edge; inside: distance to edge.
            "outside_edge": horiz < 0.0,
            "abs_edge_gap_m": abs(horiz),
        }

    def poses_at_sdk_q(q_sdk: list[float]) -> dict[str, np.ndarray]:
        mapped = convention.map_positions(
            dict(zip(convention.joint_names, q_sdk, strict=True)),
            source_model_version=mapping_doc["source_model_sha256"],
            target_model_version=mapping_doc["target_model_sha256"],
        )
        arm = {}
        for i in range(1, 9):
            names = convention.joint_names[: min(i, 7)]
            tf, _ = urdf_forward_kinematics(
                args.arm_urdf,
                {n: mapped[n] for n in names},
                base_frame="L_arm_root",
                tip_frame=f"L{i}_Link",
            )
            arm[f"L{i}_Link"] = tf
        hand = {
            "lh_hand_base_link": RigidTransform(
                "lh_hand_base_link", "lh_hand_base_link", np.eye(4), "synthetic"
            )
        }
        arm.update(attach_tool_poses(arm["L8_Link"], fixed, hand))
        return {name: tf.matrix[:3, 3].copy() for name, tf in arm.items()}

    # Reconstruct the same 9 joint samples as the rejected first lift interval.
    from h_shadow_path import fk  # SDK-locked FK path for seed→waypoint linspace

    plan = load(
        ROOT
        / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356/offline_replay.json"
    )["plan"]
    seed = np.asarray(plan["seed"], float)
    goal_q = np.asarray(plan["waypoints"][0]["ik"]["positions_rad"], float)
    qs = [q.tolist() for q in np.linspace(seed, goal_q, 9)]

    per_sample = []
    closest = None
    for idx, q in enumerate(qs):
        origins = poses_at_sdk_q(q)
        parts = []
        for name, xyz in origins.items():
            m = metrics(xyz)
            m["part"] = name
            parts.append(m)
            # Rank by how close to entering the board: prefer smallest |gap| while
            # below plane or nearest outside-edge underhang. Primary key: planar
            # distance to edge line if outside, else signed clearance.
            score = (
                abs(m["signed_robot_edge_clearance_m"])
                if m["outside_edge"]
                else m["signed_robot_edge_clearance_m"]
            )
            cand = {
                "sample_index": idx,
                "q_sdk_rad": q,
                "part": name,
                "score_m": score,
                **m,
            }
            if closest is None or cand["score_m"] < closest["score_m"]:
                closest = cand
        per_sample.append({"sample_index": idx, "q_sdk_rad": q, "parts": parts})

    # Also summarize min abs edge gap among palm + distal links.
    focus_names = ["L6_Link", "L7_Link", "L8_Link", "lh_hand_base_link"]
    focus_mins = []
    for name in focus_names:
        vals = []
        for sample in per_sample:
            part = next(p for p in sample["parts"] if p["part"] == name)
            vals.append(part)
        best = min(vals, key=lambda r: abs(r["signed_robot_edge_clearance_m"]))
        focus_mins.append({"part": name, **best})

    report = {
        "schema": "h-shadow-lift-part-proximity-0.1",
        "issue": "#36",
        "control_ready": False,
        "motion_commanded": False,
        "motion_enabled": False,
        "approved_for_motion": False,
        "phase": "first_lift_subinterval",
        "geometry_scope": "link_origins_only_L1_to_L8_plus_lh_hand_base",
        "mapping": {
            "path": str(args.mapping.as_posix()),
            "approved_for_motion": False,
            "source_model_sha256": mapping_doc["source_model_sha256"],
            "target_model_sha256": mapping_doc["target_model_sha256"],
        },
        "mount": {
            "path": str(args.mount.as_posix()),
            "assembly_sha256": mount["assembly_sha256"],
            "approved_for_motion": False,
        },
        "edge_report": str(args.edge_report.as_posix()),
        "edge_note": (
            "signed_robot_edge_clearance_m < 0 means outside robot-side near edge "
            "(same convention as robot_side_table_edge). Not a palm/arm safety margin."
        ),
        "closest_part": closest,
        "focus_part_minima": focus_mins,
        "samples": per_sample,
        "missing": [
            "fingertip frames (need bound live hand pose; can0 vs can1 teach remap open)",
            "mesh/capsule sweep vs table slab (origins only here)",
            "continuous articulated sweep certificate",
            "full measured desk polygon (edge is depth-support terminus estimate)",
        ],
        "reject_table_unchanged": True,
        "flange_audit_crosscheck": {
            "n_samples_expected": 9,
            "n_samples": len(qs),
            "independent_first_base_m": samples_doc["samples"][0]["base_m"],
        },
    }
    out = args.output / "lift_part_proximity.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {
        "closest_part": closest["part"],
        "sample_index": closest["sample_index"],
        "signed_robot_edge_clearance_m": closest["signed_robot_edge_clearance_m"],
        "height_plane_m": closest["height_plane_m"],
        "xyz_base_m": closest["xyz_base_m"],
        "focus_part_minima": [
            {
                "part": r["part"],
                "signed_robot_edge_clearance_m": r["signed_robot_edge_clearance_m"],
                "height_plane_m": r["height_plane_m"],
            }
            for r in focus_mins
        ],
        "report": str(out),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
