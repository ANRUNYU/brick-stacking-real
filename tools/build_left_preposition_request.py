"""Build an offline planning handoff from a P7 observation and the official 215245 seed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics

MODEL_SHA = "233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce"
PATH_SHA = "349adb65352c820dc13ece77da26b575b269ab31af821244ec60e426758d16a3"
SDK_NAMES = [f"J{i}" for i in range(1, 8)]
NAMES = [f"L{i}_Joint" for i in range(1, 8)]


def sha_lf(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def finite_vector(values, size):
    result = np.array(values, dtype=float)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"expected {size} finite values")
    return result


def build(precheck, path, urdf):
    record = json.loads(precheck.read_bytes())
    official = json.loads(path.read_bytes())
    if (sha_lf(urdf) != MODEL_SHA or record["urdf_sha256_lf"] != MODEL_SHA
            or official["urdf_sha256"] != MODEL_SHA or sha_lf(path) != PATH_SHA
            or record["path_sha256_lf"] != PATH_SHA):
        raise ValueError("path or model lock mismatch")
    if (record["schema"] != "wrist-path-start-precheck-0.1" or record["interface"] != "can2"
            or any(record[key] is not False for key in ("motion_commanded", "motion_enabled", "enable_called"))
            or record["can2_released"] is not True or record["urdf_lock_ok"] is not True):
        raise ValueError("expected completed read-only left-arm precheck")
    if (official["side"], official["joint_names"], official["parent_frame"], official["child_frame"],
            official["segments"][0]["from"]) != ("left", SDK_NAMES, "L_arm_root", "L8_Link", "grasp_ready"):
        raise ValueError("unexpected path endpoint convention")
    current = finite_vector(record["q_rad"], 7)
    goal = finite_vector(official["segments"][0]["points"][0]["q_rad"], 7)
    if not np.array_equal(goal, finite_vector(record["grasp_ready_seed_q_rad"], 7)):
        raise ValueError("recorded seed differs from official seed")
    model = ET.parse(urdf)
    for i, name in enumerate(NAMES):
        limit = model.find(f"joint[@name='{name}']/limit")
        if limit is None or not all(float(limit.get("lower")) <= q <= float(limit.get("upper"))
                                     for q in (current[i], goal[i])):
            raise ValueError(f"endpoint outside declared range: {name}")

    def endpoint(q, xyz):
        transform, _ = urdf_forward_kinematics(urdf, dict(zip(NAMES, q, strict=True)),
                                               base_frame="L_arm_root", tip_frame="L8_Link")
        if not np.allclose(transform.matrix[:3, 3], finite_vector(xyz, 3), rtol=0, atol=1e-6):
            raise ValueError("recorded endpoint disagrees with locked FK")
        return dict(q_rad=q.tolist(), T_base_L8=transform.matrix.tolist())

    start = endpoint(current, record["tip_xyz_m"])
    end = endpoint(goal, record["target_xyz_m"])
    delta = float(np.linalg.norm(np.array(start["T_base_L8"])[:3, 3] - np.array(end["T_base_L8"])[:3, 3]))
    if abs(delta - float(record["error_m"])) > 1e-6 or not np.isfinite(record["error_m"]):
        raise ValueError("precheck error inconsistent with FK")
    return dict(schema="left-preposition-request-0.1", task="observed_left_arm_to_215245_grasp_ready",
                joint_names_model=NAMES, joint_names_sdk=SDK_NAMES, parent_frame="L_arm_root",
                child_frame="L8_Link", source_precheck_sha256_lf=sha_lf(precheck),
                official_path_sha256_lf=PATH_SHA, model_sha256_lf=MODEL_SHA,
                start=start, goal=end, translation_difference_m=delta,
                start_semantics="recorded snapshot; refresh before any live run",
                scene_binding=None, planned_trajectory=None, planner_result="AWAITING_BOUND_SCENE_AND_PLANNER",
                executable=False, motion_enabled=False, control_ready=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precheck", type=Path, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, default=ROOT / "config/models/p7_left/p7__left.urdf")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.precheck, args.path, args.urdf)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(result["planner_result"], round(1000 * result["translation_difference_m"], 3), "mm")
