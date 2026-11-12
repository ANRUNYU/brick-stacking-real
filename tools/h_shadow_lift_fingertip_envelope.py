"""Offline A/164356: conservative O6 finger-mesh envelope vs fitted near-edge half-plane.

Does NOT bind live_A hand angles (none recorded; raw/percent→rad missing).
Replays sampled poses and independently bounds all finger rotations using a
per-link enclosing sphere at the first finger joint. The arm follows the same
joint-linear first lift as the 57df5f0 rigid palm/arm mesh audit.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brick_stacking.localization.hand_kinematics import hand_link_poses
from brick_stacking.localization.joint_conventions import JointConventionMap
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.tool_assembly import attach_tool_poses

FIELD = ROOT / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356"
FINGER_LINKS = [
    "lh_thumb_metacarpals_base2",
    "lh_thumb_metacarpals",
    "lh_thumb_distal",
    "lh_index_proximal",
    "lh_index_distal",
    "lh_middle_proximal",
    "lh_middle_distal",
    "lh_ring_proximal",
    "lh_ring_distal",
    "lh_pinky_proximal",
    "lh_pinky_distal",
]
DISTAL = {
    "lh_thumb_distal",
    "lh_index_distal",
    "lh_middle_distal",
    "lh_ring_distal",
    "lh_pinky_distal",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def obj_vertices(data: bytes) -> np.ndarray:
    points = np.array(
        [line.split()[1:4] for line in data.splitlines() if line.startswith(b"v ")],
        dtype=float,
    )
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError("invalid OBJ vertices")
    return points


def load_finger_meshes(hand_dir: Path, hand_lock: dict) -> dict[str, np.ndarray]:
    raw = (hand_dir / "hand.urdf").read_bytes()
    if digest(raw) != hand_lock["urdf_sha256"]:
        raise ValueError("O6 URDF hash differs from repository lock")
    entries = {e["path"]: e for e in hand_lock["meshes"]}
    out = {}
    for name in FINGER_LINKS:
        entry = next(e for e in hand_lock["meshes"] if e["link"] == name)
        data = (hand_dir / entry["path"]).read_bytes()
        if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
            raise ValueError(f"mesh lock mismatch: {name}")
        out[name] = obj_vertices(data)
    return out


def actuated_limits(hand_urdf: Path) -> list[tuple[str, float, float]]:
    root = ET.parse(hand_urdf).getroot()
    rows = []
    for j in root.findall("joint"):
        if j.get("type") != "revolute" or j.find("mimic") is not None:
            continue
        lim = j.find("limit")
        rows.append((j.get("name"), float(lim.get("lower")), float(lim.get("upper"))))
    if len(rows) != 6:
        raise ValueError(f"expected 6 actuated joints, got {len(rows)}")
    return rows


def hand_pose_grid(limits: list[tuple[str, float, float]]) -> list[dict[str, float]]:
    names = [n for n, _, _ in limits]
    corners = list(itertools.product(*[(lo, hi) for _, lo, hi in limits]))
    poses = [dict(zip(names, vals, strict=True)) for vals in corners]
    # Audit synthetic poses (radian model space, not hardware).
    poses.append(dict(zip(names, [0.0] * 6, strict=True)))
    poses.append(dict(zip(names, [0.4, 0.2, 0.6, 0.6, 0.6, 0.6], strict=True)))
    # Deduplicate.
    uniq = []
    seen = set()
    for p in poses:
        key = tuple(round(p[n], 9) for n in names)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def finger_spheres(hand_urdf: Path, meshes: dict, lock: dict) -> dict:
    """Enclose each link at every rotation about its joints, including interval interiors."""
    root = ET.parse(hand_urdf).getroot()
    joints = {j.find("child").get("link"): j for j in root.findall("joint")}
    entries = {m["link"]: m["path"] for m in lock["meshes"]}
    spheres = {}
    for name, vertices in meshes.items():
        collision, = root.findall(f"link[@name='{name}']/collision")
        mesh = collision.find("geometry/mesh")
        origin = collision.find("origin")
        if (mesh is None or mesh.get("filename") != entries[name]
                or mesh.get("scale", "1 1 1").split() != ["1", "1", "1"]
                or (origin is not None and any(float(v) for k in ("xyz", "rpy")
                                               for v in origin.get(k, "0 0 0").split()))):
            raise ValueError(f"unsupported collision binding: {name}")
        radius = float(np.linalg.norm(vertices, axis=1).max())
        child = name
        visited = set()
        while child not in visited:
            visited.add(child)
            joint = joints[child]
            if joint.get("type") not in ("revolute", "fixed"):
                raise ValueError(f"unbounded translation at {child}")
            xyz = np.array(joint.find("origin").get("xyz").split(), dtype=float)
            if xyz.shape != (3,) or not np.isfinite(xyz).all():
                raise ValueError(f"invalid joint translation at {child}")
            parent = joint.find("parent").get("link")
            if parent == "lh_hand_base_link":
                # The first joint origin is fixed in palm coordinates. Every subsequent
                # rotated displacement has constant length, regardless of mimic coupling.
                spheres[name] = (xyz, radius)
                break
            radius += float(np.linalg.norm(xyz))
            child = parent
        else:
            raise ValueError(f"cycle in hand chain: {name}")
    return spheres


def evaluate(args: argparse.Namespace) -> dict:
    edge = load(args.field / "robot_side_table_edge/robot_side_edge_report.json")
    poses = load(args.field / "lift_part_proximity/lift_part_proximity.json")
    plan = load(args.field / "offline_replay.json")["plan"]
    joints = np.linspace(plan["seed"], plan["waypoints"][0]["ik"]["positions_rad"], 9)
    if (
        edge["frame"] != "frame_009.npz"
        or plan["status"] != "REJECT_TABLE"
        or joints.shape != (9, 7)
        or not np.isfinite(joints).all()
    ):
        raise ValueError("unexpected field scene or rejected interval")

    normal = np.array(edge["table_normal_base"])
    normal /= np.linalg.norm(normal)
    axis = np.cross(normal, edge["edge_dir_base"])
    axis /= np.linalg.norm(axis)
    if axis @ edge["inward_base"] < 0:
        axis = -axis
    if not np.isfinite(axis).all() or axis @ edge["inward_base"] < 0.9:
        raise ValueError("invalid table-inward edge normal")
    center = np.array(edge["edge_mean_base_m"])

    cfg = ROOT / "config/planning"
    mapping = load(cfg / "p7_sdk_to_vendor_collision_candidate.json")
    mount = load(cfg / "p7_o6_left_mount_candidate.json")
    conv = JointConventionMap(
        tuple(mapping["joint_names"]),
        tuple(mapping["signs"]),
        tuple(mapping["offsets_rad"]),
        mapping["source_model_sha256"],
        mapping["target_model_sha256"],
    )
    locks = ROOT / "docs/team/C/evidence"
    arm_lock = load(locks / "p7_collision_asset_lock_C16.json")
    hand_lock = load(locks / "o6_asset_lock_C19.json")
    components = mount["verified_components"]
    if (
        arm_lock["urdf_sha256"] != conv.target_model_version
        or [c["sha256"] for c in components]
        != [arm_lock["urdf_sha256"], hand_lock["urdf_sha256"]]
        or poses["mount"]["assembly_sha256"] != mount["assembly_sha256"]
        or poses["mapping"]["source_model_sha256"] != conv.source_model_version
    ):
        raise ValueError("model binding mismatch")

    arm_urdf = args.arm / "arm.urdf"
    if digest(arm_urdf.read_bytes()) != arm_lock["urdf_sha256"]:
        raise ValueError("P7 URDF hash differs from repository lock")
    hand_urdf = args.hand / "hand.urdf"
    finger_meshes = load_finger_meshes(args.hand, hand_lock)
    limits = actuated_limits(hand_urdf)
    hand_qs = hand_pose_grid(limits)
    spheres = finger_spheres(hand_urdf, finger_meshes, hand_lock)
    fixed = RigidTransform(
        "L8_Link",
        "lh_hand_base_link",
        mount["T_L8_hand_root"],
        "vendor_declared",
        mount["assembly_sha256"],
    )

    # Lever-arm upper bound: arm chain + mount + farthest finger vertex in any local frame.
    chain = ET.parse(arm_urdf).getroot().findall("joint")
    translations = [
        np.fromstring(j.find("origin").get("xyz", "0 0 0"), sep=" ") for j in chain
    ]
    finger_radius = max(np.linalg.norm(v, axis=1).max() for v in finger_meshes.values())
    # Also add a crude hand kinematic reach: sum of absolute joint origin translations in hand URDF.
    hand_reach = 0.0
    for j in ET.parse(hand_urdf).getroot().findall("joint"):
        origin = j.find("origin")
        if origin is not None:
            hand_reach += np.linalg.norm(
                np.fromstring(origin.get("xyz", "0 0 0"), sep=" ")
            )
    lever = (
        sum(np.linalg.norm(t) for t in translations)
        + np.linalg.norm(np.array(mount["T_L8_hand_root"])[:3, 3])
        + hand_reach
        + finger_radius
    )
    max_half_step = float(np.abs(np.diff(joints, axis=0)).sum(axis=1).max() / 2)
    displacement_bound = float(lever * max_half_step)
    palm_lever = sum(np.linalg.norm(t) for t in translations) + np.linalg.norm(fixed.matrix[:3, 3])
    sphere_bounds = {}
    local_poses = [hand_link_poses(hand_urdf, hq, base_frame="lh_hand_base_link") for hq in hand_qs]

    maxima: dict = {}
    global_best = None
    for idx, (q, record) in enumerate(zip(joints, poses["samples"], strict=True)):
        if idx != record["sample_index"] or not np.allclose(
            q, record["q_sdk_rad"], atol=1e-9, rtol=0
        ):
            raise ValueError("reference joint sample mismatch")
        mapped = conv.map_positions(
            dict(zip(conv.joint_names, q, strict=True)),
            source_model_version=conv.source_model_version,
            target_model_version=conv.target_model_version,
        )
        arm = {}
        for j in range(1, 9):
            positions = {k: mapped[k] for k in conv.joint_names[:j]}
            pose, _ = urdf_forward_kinematics(
                arm_urdf,
                positions,
                base_frame="L_arm_root",
                tip_frame=f"L{j}_Link",
            )
            arm[f"L{j}_Link"] = pose
        refs = {p["part"]: p["xyz_base_m"] for p in record["parts"]}
        if not np.allclose(arm["L8_Link"].matrix[:3, 3], refs["L8_Link"], atol=1e-6, rtol=0):
            raise ValueError(f"L8 FK mismatch at sample {idx}")

        palm = arm["L8_Link"].matrix @ fixed.matrix
        if not np.allclose(palm[:3, 3], refs["lh_hand_base_link"], atol=1e-6, rtol=0):
            raise ValueError(f"palm FK mismatch at sample {idx}")
        sample_caps = {}
        for name, (anchor, radius) in spheres.items():
            anchor_base = palm[:3, :3] @ anchor + palm[:3, 3]
            cap = float((anchor_base - center) @ axis + radius)
            sample_caps[name] = cap
            if name not in sphere_bounds or cap > sphere_bounds[name]["sample_upper_m"]:
                extra = float((palm_lever + np.linalg.norm(anchor)) * max_half_step)
                sphere_bounds[name] = dict(sample=idx, radius_m=radius, sample_upper_m=cap,
                                           arm_anchor_displacement_bound_m=extra,
                                           interpolation_upper_m=cap + extra)

        for hq_i, (hq, local) in enumerate(zip(hand_qs, local_poses, strict=True)):
            world = attach_tool_poses(arm["L8_Link"], fixed, local)

            for name, xyz in finger_meshes.items():
                T = world[name].matrix
                signed = xyz @ (T[:3, :3].T @ axis) + (T[:3, 3] - center) @ axis
                k = int(np.argmax(signed))
                if signed[k] > sample_caps[name] + 1e-10:
                    raise ValueError(f"sampled vertex outside enclosing bound: {idx}/{name}")
                point = T[:3, :3] @ xyz[k] + T[:3, 3]
                height = float((point - center) @ normal)
                cand = dict(
                    sample=idx,
                    hand_pose_index=hq_i,
                    hand_actuated_rad=hq,
                    link=name,
                    distal=name in DISTAL,
                    signed_perpendicular_m=float(signed[k]),
                    height_at_this_vertex_m=height,
                    vertex_base_m=point.tolist(),
                )
                key = name
                if key not in maxima or cand["signed_perpendicular_m"] > maxima[key][
                    "signed_perpendicular_m"
                ]:
                    maxima[key] = cand
                if global_best is None or cand["signed_perpendicular_m"] > global_best[
                    "signed_perpendicular_m"
                ]:
                    global_best = cand

    max_signed = float(global_best["signed_perpendicular_m"])
    bound = max_signed + displacement_bound
    distal_max = max(
        v["signed_perpendicular_m"] for v in maxima.values() if v["distal"]
    )
    sources = [
        "offline_replay.json",
        "robot_side_table_edge/robot_side_edge_report.json",
        "lift_part_proximity/lift_part_proximity.json",
    ]
    source_sha256_lf = {
        name: digest((args.field / name).read_bytes().replace(b"\r\n", b"\n"))
        for name in sources
    }
    return dict(
        schema="h-shadow-lift-fingertip-envelope-0.2",
        issue="#36",
        frame=edge["frame"],
        source_sha256_lf=source_sha256_lf,
        arm_samples=len(joints),
        hand_pose_count=len(hand_qs),
        hand_pose_method=(
            "all 2^6 URDF actuated limit corners plus audit synthetics "
            "[0]*6 and [0.4,0.2,0.6,0.6,0.6,0.6]; NOT live_A or can1 probe angles"
        ),
        actuated_limits={n: dict(lower=lo, upper=hi) for n, lo, hi in limits},
        per_link=maxima,
        closest_overall=global_best,
        closest_distal_signed_m=float(distal_max),
        all_envelope_meshes_outside=all(
            v["signed_perpendicular_m"] < 0 for v in maxima.values()
        ),
        modeled_interpolation=dict(
            method="nearest arm sample plus global revolute lever-arm bound; hand pose held fixed within each evaluation",
            assumption="joint-linear arm seed to first IK; only the listed fixed hand poses",
            lever_arm_bound_m=float(lever),
            half_step_joint_l1_rad=max_half_step,
            displacement_bound_m=displacement_bound,
            max_signed_upper_bound_m=bound,
            covered_envelope_outside_fitted_halfplane=bound < 0,
        ),
        all_hand_angles=dict(method="sphere at each finger base joint; downstream translation lengths plus mesh radius",
                             arm_model="joint-linear seed to first IK; nearest arm sample bounds anchor displacement",
                             per_link=sphere_bounds,
                             max_signed_upper_m=max(row["interpolation_upper_m"] for row in sphere_bounds.values()),
                             outside=all(row["interpolation_upper_m"] < 0 for row in sphere_bounds.values())),
        can_mapping_working_assumption="left O6 SN on can1 (see o6_can_readonly_probe_20261112_193239.json)",
        live_A_hand_angles="UNKNOWN_NOT_RECORDED",
        raw_to_rad="MISSING",
        scope="live_A first lift only; sampled poses and separate all-angle enclosing spheres",
        table="depth-fitted near-edge half-plane; finite board and uncertainty unmeasured",
        whole_robot_sweep="UNKNOWN",
        planner_status=plan["status"],
        approved_for_motion=False,
        control_ready=False,
        motion_commanded=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", type=Path, default=FIELD)
    parser.add_argument("--arm", type=Path, default=ROOT / "artifacts/vendor_p7_left")
    parser.add_argument("--hand", type=Path, default=ROOT / "artifacts/vendor_o6_left")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        args.output,
        "outside=",
        result["all_envelope_meshes_outside"],
        "closest_mm=",
        round(result["closest_overall"]["signed_perpendicular_m"] * 1000, 1),
        "sampled_pose_upper_mm=",
        round(result["modeled_interpolation"]["max_signed_upper_bound_m"] * 1000, 1),
        "all_angles_upper_mm=",
        round(result["all_hand_angles"]["max_signed_upper_m"] * 1000, 1),
    )
