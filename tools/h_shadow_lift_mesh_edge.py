"""Offline A/164356: screen eight arm meshes and the rigid palm against a fitted half-plane.

Run after tools/fetch_p7_collision_assets.py and tools/fetch_o6_collision_assets.py.
The signed coordinate is positive towards the table, perpendicular to its fitted edge.
The maximum over triangle vertices is the maximum over their triangles at that pose.
"""
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brick_stacking.localization.joint_conventions import JointConventionMap
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.mesh_envelopes import stl_vertices

FIELD = ROOT / "docs/team/B/evidence/line_h/readonly_shadow/live_A_164356"
PALM = "lh_hand_base_link"
ARM = [f"L{i}_Link" for i in range(1, 9)]


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def vertices(directory, urdf, lock, names):
    raw = urdf.read_bytes()
    if digest(raw) != lock["urdf_sha256"]:
        raise ValueError("URDF hash differs from the repository lock")
    root = ET.fromstring(raw)
    entries = {entry["path"]: entry for entry in lock["meshes"]}
    result = {}
    for name in names:
        collisions = root.findall(f"link[@name='{name}']/collision")
        if len(collisions) != 1:
            raise ValueError(f"expected one collision geometry: {name}")
        origin = collisions[0].find("origin")
        mesh = collisions[0].find("geometry/mesh")
        if mesh is None or any(float(x) != 1 for x in mesh.get("scale", "1 1 1").split()):
            raise ValueError(f"unsupported geometry/scale: {name}")
        if origin is not None and any(float(x) for k in ("xyz", "rpy") for x in origin.get(k, "0 0 0").split()):
            raise ValueError(f"unsupported collision offset: {name}")
        entry = entries[mesh.attrib["filename"]]
        data = (directory / entry["path"]).read_bytes()
        if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
            raise ValueError(f"mesh bytes differ from repository lock: {name}")
        if name == PALM:
            points = np.array([line.split()[1:4] for line in data.splitlines()
                               if line.startswith(b"v ")], dtype=float)
        else:
            points = stl_vertices(data)
        if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
            raise ValueError(f"invalid vertices: {name}")
        result[name] = points
    return result


def evaluate(args):
    edge = load(args.field / "robot_side_table_edge/robot_side_edge_report.json")
    poses = load(args.field / "lift_part_proximity/lift_part_proximity.json")
    plan = load(args.field / "offline_replay.json")["plan"]
    joints = np.linspace(plan["seed"], plan["waypoints"][0]["ik"]["positions_rad"], 9)
    if (edge["frame"] != "frame_009.npz" or plan["status"] != "REJECT_TABLE"
            or joints.shape != (9, 7) or not np.isfinite(joints).all()):
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
    conv = JointConventionMap(tuple(mapping["joint_names"]), tuple(mapping["signs"]),
                              tuple(mapping["offsets_rad"]), mapping["source_model_sha256"],
                              mapping["target_model_sha256"])
    locks = ROOT / "docs/team/C/evidence"
    arm_lock = load(locks / "p7_collision_asset_lock_C16.json")
    hand_lock = load(locks / "o6_asset_lock_C19.json")
    components = mount["verified_components"]
    if (arm_lock["urdf_sha256"] != conv.target_model_version
            or [c["sha256"] for c in components] != [arm_lock["urdf_sha256"], hand_lock["urdf_sha256"]]
            or poses["mount"]["assembly_sha256"] != mount["assembly_sha256"]
            or poses["mapping"]["source_model_sha256"] != conv.source_model_version):
        raise ValueError("model binding mismatch")
    urdf = args.arm / "arm.urdf"
    meshes = vertices(args.arm, urdf, arm_lock, ARM)
    meshes.update(vertices(args.hand, args.hand / "hand.urdf", hand_lock, [PALM]))
    # An upper bound on any vertex's lever arm about any upstream joint:
    # triangle inequality over all fixed link translations, mount and local vertex radius.
    chain = ET.parse(urdf).getroot().findall("joint")
    if any(j.get("type") not in ("fixed", "revolute") for j in chain):
        raise ValueError("lever-arm bound requires a fixed/revolute model")
    translations = [np.fromstring(j.find("origin").get("xyz", "0 0 0"), sep=" ") for j in chain]
    lever = (sum(np.linalg.norm(t) for t in translations)
             + np.linalg.norm(np.array(mount["T_L8_hand_root"])[:3, 3])
             + max(np.linalg.norm(v, axis=1).max() for v in meshes.values()))
    # At most half a sample interval to the nearest endpoint on a joint-linear segment.
    max_half_step = np.abs(np.diff(joints, axis=0)).sum(axis=1).max() / 2
    displacement_bound = float(lever * max_half_step)
    maxima = {}
    for idx, (q, record) in enumerate(zip(joints, poses["samples"], strict=True)):
        if idx != record["sample_index"] or not np.allclose(q, record["q_sdk_rad"], atol=1e-9, rtol=0):
            raise ValueError("reference joint sample mismatch")
        mapped = conv.map_positions(dict(zip(conv.joint_names, q, strict=True)),
                                    source_model_version=conv.source_model_version,
                                    target_model_version=conv.target_model_version)
        transforms = {}
        for j, name in enumerate(ARM, 1):
            positions = {k: mapped[k] for k in conv.joint_names[:j]}
            pose, _ = urdf_forward_kinematics(urdf, positions, base_frame="L_arm_root", tip_frame=name)
            transforms[name] = pose.matrix
        transforms[PALM] = transforms["L8_Link"] @ mount["T_L8_hand_root"]
        refs = {p["part"]: p["xyz_base_m"] for p in record["parts"]}
        for name, transform in transforms.items():
            offset = transform[:3, 3]
            if not np.allclose(offset, refs[name], atol=1e-6, rtol=0):
                raise ValueError(f"reference FK mismatch: {idx}/{name}")
            xyz = meshes[name]
            signed = xyz @ (transform[:3, :3].T @ axis) + (offset - center) @ axis
            k = int(np.argmax(signed))
            if name not in maxima or signed[k] > maxima[name]["signed_perpendicular_m"]:
                point = transform[:3, :3] @ xyz[k] + offset
                maxima[name] = dict(sample=idx, signed_perpendicular_m=float(signed[k]),
                                    height_at_this_vertex_m=float((point - center) @ normal),
                                    vertex_base_m=point.tolist())
    max_signed = max(v["signed_perpendicular_m"] for v in maxima.values())
    bound = max_signed + displacement_bound
    interpolation = dict(method="nearest sample plus global revolute lever-arm bound",
                         assumption="joint-linear interpolation of this SDK seed to first IK waypoint",
                         lever_arm_bound_m=float(lever), half_step_joint_l1_rad=float(max_half_step),
                         displacement_bound_m=displacement_bound, max_signed_upper_bound_m=bound,
                         covered_meshes_outside_fitted_halfplane=bound < 0)
    sources = ["offline_replay.json", "robot_side_table_edge/robot_side_edge_report.json",
               "lift_part_proximity/lift_part_proximity.json"]
    source_sha256_lf = {name: digest((args.field / name).read_bytes().replace(b"\r\n", b"\n"))
                        for name in sources}
    return dict(frame=edge["frame"], source_sha256_lf=source_sha256_lf, samples=len(joints), per_part=maxima,
                all_sampled_meshes_outside=all(v["signed_perpendicular_m"] < 0 for v in maxima.values()),
                scope="A first lift only; discrete P7 collision meshes and rigid O6 palm",
                table="depth-fitted near-edge half-plane; finite board and uncertainty unmeasured",
                modeled_interpolation=interpolation, whole_robot_sweep="UNKNOWN",
                fingers="UNKNOWN", planner_status=plan["status"],
                approved_for_motion=False, control_ready=False, motion_commanded=False)


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
    print(args.output, result["all_sampled_meshes_outside"])
