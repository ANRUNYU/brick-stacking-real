# 固定红块局部微抬离线检查

**声明模型通过，现场验收待签。** 本次只计算 100523 `preshape_at_block` 起点的无载微抬与保持。起点从已核对 SHA-256 的原始七轴重算，并与锁定 URDF FK 证据逐元素比对。全程使用 `L_arm_root` → `L8_Link`（含固定 `L8_Joint`），J6/J7 保持 `sdk_report_not_audited`。运行期间没有连接设备、发手指指令或执行物理空跑。 [配置草案](../../../../../config/planning/fixed_red_block_micro_lift_20261112.json) · [起点审计](left_preshape_20261112_100523/left_preshape_joint_source_audit.md)

| 检查 | 本次结果 |
| --- | --- |
| 局部逆解与插值 | 每 2.5 mm 一点，以前一点为种子做锁定模型 IK。4 个各 1 s 的五次关节插值段，再保持 2 s。模型保持段的关节速度为零。 |
| 方向与幅度 | 以 `table_board` 的 +Z 向上，法线在 `L_arm_root` 中约为 `[0.060929, 0.054383, 0.996659]`。L8 从 `[0.319101, -0.021698, -0.322421]` 到 `[0.319710, -0.021154, -0.312455]` m，沿法线抬升 10.000 mm。 |
| L8 轨迹与关节 | 50 ms 区间中点最大横偏 0.0029 mm、最大姿态漂移 0.000084°，采样高度无回落。L8 原点全段速度保守上界 9.005 mm/s；J2 最小 −0.004674 rad，七轴全段在 URDF 声明限位内。 |
| 左臂与桌面 | 8 个散列校验的 STL 凸包、21 个非排除自碰对、120 个时间区间。扣除每半区间的模型表面位移上界后，自碰分离下界 1.692 mm、拟合桌面净空下界 178.260 mm、水平桌面敏感性检查下界 167.087 mm。 |

**覆盖范围。** 桌面法线和高度来自旧 `FIT_ONLY` 桌板，现场竖直与同布局仍需重新确认。空载模型移除了块与负载。O6、手指闭合包络、相机、躯干、右臂和现场障碍物未建模，安装接缝对沿用供应商审查排除项。全机碰撞、实际 TCP 跟踪、夹持和结束方案仍待复核。局部路径按本记录重新求解和验算，215245 仅提供已有 STL 资产的 SHA-256 清单。

20 项 URDF FK、局部 IK、关节插值及表面速度边界相关单测通过。现场签字项见[授权检查单](red_block_micro_lift_signoff_20261112.md)。

## 机读检查结果

```json
{
  "config_sha256": "d6983b122ad4a2d284734ed8b7e6cb6ca44903ddd1f5189b70f6a1737f69fdcf",
  "asset_manifest_sha256": "a3dbb50536305539c2c82a6b0f16d3279cedabf5909635d3be87a3cb323c0840",
  "geometry_mapping_sha256": "86ed31fbe92b35a09fe0b95cbafa46832a37cb92aac9df61405885d44127dd98",
  "seams_sha256": "0e6cb9043ba059d42bd7951be8d73a71162cbfca522a683008ae82036c05893e",
  "asset_mesh_count": 8,
  "self_pairs": 21,
  "intervals": 120,
  "up_normal_in_L_arm_root": [
    0.06092852448030999,
    0.05438347230033436,
    0.9966594969422662
  ],
  "start_m": [
    0.3191006140903376,
    -0.021698005599919593,
    -0.3224213712907774
  ],
  "lift_end_m": [
    0.31970989942210376,
    -0.021154171006423056,
    -0.3124547772610926
  ],
  "end_height_delta_m": 0.009999999061656845,
  "max_midpoint_lateral_deviation_m": 2.8752726599597835e-06,
  "max_midpoint_rotation_delta_rad": 1.4563644178324461e-06,
  "min_midpoint_height_increment_m": 0.0,
  "l8_speed_upper_bound_m_s": 0.009004677790741733,
  "min_j2_rad": -0.004673847928643227,
  "min_joint_position_margin_rad": 0.06532615207135678,
  "max_joint_speed_rad_s": 0.01718566547805625,
  "model_clearance_lower_bounds_m": {
    "self": [
      0.0016916486573870558,
      [
        "L5_Link",
        "L7_Link"
      ]
    ],
    "table": [
      0.17825991114146897,
      "L7_Link"
    ],
    "horizontal_table_sensitivity": [
      0.16708719581968454,
      "L7_Link"
    ]
  },
  "l8_geometry_check": "PASS",
  "arm_hull_check": "PASS_DECLARED_EMPTY_MODEL",
  "full_collision": "UNKNOWN",
  "motion_enabled": false,
  "live_authorized": false,
  "q_waypoints_rad": [
    [
      -0.0511726438999176,
      -0.004673847928643227,
      0.33557960391044617,
      -1.4567917585372925,
      1.7294782400131226,
      0.2161058976119623,
      -0.49725337605859465
    ],
    [
      -0.05139166825204666,
      -0.0035159082176583296,
      0.3358338789059326,
      -1.4659574467922558,
      1.7302391421316954,
      0.21480656722656577,
      -0.5063614720253685
    ],
    [
      -0.051687640853729504,
      -0.0023780588361110386,
      0.3360710701461282,
      -1.475036089164973,
      1.7309822876703516,
      0.21349506483924058,
      -0.5154567377579218
    ],
    [
      -0.052060317961415276,
      -0.0012602867828669004,
      0.3362913029741786,
      -1.4840286451073275,
      1.7317075533044404,
      0.21217138365964672,
      -0.5245398950080868
    ],
    [
      -0.05250948025862352,
      -0.00016257775123619433,
      0.336494698066752,
      -1.4929360334038007,
      1.7324148087214206,
      0.21083551297585437,
      -0.5336116736437626
    ]
  ]
}
```

<details>
<summary>离线复算代码</summary>

将代码保存为临时 Python 文件。从本 worktree 根目录用 NumPy 和 SciPy 运行，将含 `arm.urdf`、`meshes/` 的供应商资产目录作为第一个参数。输入文件 SHA-256 按原始字节计算，Windows 检出须保留 LF。标准输出是本页的机读记录。关节路点仅供复核。

```python
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial import ConvexHull

sys.path.insert(0, str(Path("src").resolve()))
from brick_stacking.hardware.urdf_inspection import declared_revolute_limits
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.planning.joint_trajectory import JointLimits, sample_segment
from brick_stacking.planning.mesh_envelopes import stl_vertices
from brick_stacking.planning.numerical_ik import rotation_log, solve_pose_ik
from brick_stacking.planning.surface_clearance import surface_speed_bounds
from brick_stacking.wrist_handoff.pose_math import matrix_from_quat_xyzw


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def load_json(path, expected=None):
    if expected is not None and digest(path) != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return json.loads(Path(path).read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


assets = Path(sys.argv[1])
config = Path("config/planning/fixed_red_block_micro_lift_20261112.json")
plan = load_json(config)
require(all(plan[k] is False for k in ("executable", "motion_enabled", "control_ready", "live_authorized")), "draft flags")
start, lift = plan["start"], plan["lift"]
raw = load_json(start["q_ref"], start["q_sha256"])
record = load_json(start["fk_ref"], start["fk_sha256"])
board = load_json(lift["offline_table_ref"], lift["offline_table_sha256"])
lock = load_json("config/models/p7_left/LOCK.json")
model = Path(lock["urdf_relpath"])
require(digest(model) == lock["urdf_sha256"] == start["urdf_sha256"], "URDF lock")
parent, tip = start["parent_frame"], start["child_frame"]
joint_names = [f"J{i}" for i in range(1, 8)]
names = [record["urdf_joint_mapping"][j] for j in joint_names]
require(raw["sample_id"] == record["sample_id"] == start["sample_id"], "sample ID")
require(raw["joint_names"] == record["joint_names"] == joint_names, "joint order")
require(record["joint_unit"] == start["joint_unit"] == "rad", "joint units")
require(raw["q_rad"] == record["q_rad"] and len(raw["q_rad"]) == 7, "raw q mismatch")
require(all(record["input_to_urdf_sign"][j] == 1 for j in joint_names), "joint sign")
require(all(record["joint_provenance"][j] == start[j] == "sdk_report_not_audited"
            for j in ("J6", "J7")), "wrist provenance")
require(board["parent_frame"] == parent and board["approved_for_motion"] is False, "table scope")


def fk(q, link=tip, urdf=model):
    link_index = int(link[1])
    revolute = names[:min(link_index, 7)]
    return urdf_forward_kinematics(
        urdf, dict(zip(revolute, q[:len(revolute)], strict=True)),
        base_frame=parent, tip_frame=link,
    )[0]


q0 = np.asarray(raw["q_rad"], dtype=float)
start_pose = fk(q0)
require(np.allclose(start_pose.matrix, record["T_base_L8_teach"], atol=1e-12, rtol=0),
        "start matrix mismatch")
up = matrix_from_quat_xyzw(board["quaternion_xyzw"])[:, 2]
origin = np.asarray(board["translation_m"])
declared = declared_revolute_limits(model, joint_names=names)
limits = JointLimits(tuple(names), declared["lower_rad"], declared["upper_rad"],
                     declared["velocity_rad_s"], (2.0,) * 7, digest(model), "recorded")
settings = dict(position_tolerance_m=1e-7, rotation_tolerance_rad=1e-7,
                orientation_weight_m_per_rad=0.1, damping=0.01,
                max_step_rad=0.03, max_iterations=100, difference_step_rad=1e-6)
waypoints = [q0]
for fraction in (0.25, 0.5, 0.75, 1.0):
    target = start_pose.matrix.copy()
    target[:3, 3] += fraction * lift["height_m"] * up
    solved = solve_pose_ik(fk, RigidTransform(parent, tip, target, "offline_reference"),
                           waypoints[-1], limits, **settings)
    require(solved["ik"] == "PASS", solved["reason"])
    waypoints.append(np.asarray(solved["positions_rad"]))

duration = lift["planned_ascent_s"] / (len(waypoints) - 1)
segments = [dict(start_rad=a.tolist(), end_rad=b.tolist(), duration_s=duration)
            for a, b in zip(waypoints, waypoints[1:])]
segments.append(dict(start_rad=waypoints[-1].tolist(), end_rad=waypoints[-1].tolist(),
                     duration_s=lift["hold_s"]))
trajectory = dict(joint_names=names, segments=segments,
                  interpolation="quintic_stop_at_each_waypoint")

# Use the earlier artifact solely as the immutable asset manifest.
manifest_path = Path("docs/team/P/evidence/wrist_path_layer1_grasp_to_place_20261111_215245_verification.json")
manifest = load_json(manifest_path)["collision"]
vendor = assets / "arm.urdf"
mapping_path = Path("config/planning/p7_sdk_to_vendor_collision_candidate.json")
mapping = load_json(mapping_path)
require(digest(vendor) == manifest["mesh_urdf_sha256"] == mapping["target_model_sha256"],
        "vendor geometry hash")
require(mapping["source_model_sha256"] == digest(model) and mapping["joint_names"] == names
        and mapping["signs"] == [-1] * 7 and mapping["offsets_rad"] == [0] * 7, "geometry mapping")
seams_path = Path("config/planning/p7_vendor_installation_seams.json")
seams = {tuple(p) for p in load_json(seams_path)["reviewed_pairs"]}
links = [f"L{i}_Link" for i in range(1, 9)]
geometry = ET.parse(vendor)
hulls = {}
for link, asset in zip(links, manifest["mesh_assets"], strict=True):
    relative = f"meshes/{link}.STL"
    require(asset["path"] == relative and digest(assets / relative) == asset["sha256"],
            f"mesh checksum {link}")
    collision = geometry.findall(f".//link[@name='{link}']/collision")
    require(len(collision) == 1, f"collision geometry count {link}")
    transform = collision[0].find("origin")
    mesh = collision[0].find("geometry/mesh")
    require(mesh.get("filename") == relative and mesh.get("scale", "1 1 1") == "1 1 1"
            and transform.get("xyz") == transform.get("rpy") == "0 0 0", f"mesh placement {link}")
    vertices = stl_vertices((assets / relative).read_bytes())
    hull = ConvexHull(vertices)
    hulls[link] = (vertices[hull.vertices], hull.equations[:, :3])

speed = surface_speed_bounds(model, {n: h[0] for n, h in hulls.items()}, trajectory)["surface_speed_m_s"]
tip_speed = surface_speed_bounds(model, {tip: [[0.0, 0.0, 0.0]]}, trajectory)["surface_speed_m_s"][tip]
pairs = [p for p in combinations(links, 2) if p not in seams]
minimum = {key: (float("inf"), None) for key in ("self", "table", "horizontal_table_sensitivity")}
max_cross = max_rotation = 0.0
clearance_samples = 0
previous_height = None
worst_height_step = 0.0
for segment in segments:
    count = int(np.ceil(segment["duration_s"] / 0.05))
    half_interval = segment["duration_s"] / (2 * count)
    for step in range(count):
        q, _, _ = sample_segment(segment, (2 * step + 1) * half_interval)
        poses = {}
        axes = {}
        for link in links:
            pose = fk(q, link)
            equivalent = fk(-q, link, vendor)
            require(np.allclose(pose.matrix, equivalent.matrix, atol=1e-12, rtol=0),
                    f"kinematics/mapping disagreement {link}")
            vertices, normals = hulls[link]
            poses[link] = pose.apply(vertices)
            axes[link] = normals @ pose.matrix[:3, :3].T
            for key, normal, offset in (
                ("table", up, origin @ up),
                ("horizontal_table_sensitivity", np.array([0, 0, 1]), board["table_height_m"]),
            ):
                gap = float(np.min(poses[link] @ normal) - offset - speed[link] * half_interval)
                if gap < minimum[key][0]:
                    minimum[key] = (gap, link)

        for a, b in pairs:
            directions = np.vstack((axes[a], axes[b]))
            projected_a = np.einsum("ij,kj->ik", poses[a], directions)
            projected_b = np.einsum("ij,kj->ik", poses[b], directions)
            gap = float(np.max(np.maximum(
                projected_a.min(axis=0) - projected_b.max(axis=0),
                projected_b.min(axis=0) - projected_a.max(axis=0),
            ))) - (speed[a] + speed[b]) * half_interval
            if gap < minimum["self"][0]:
                minimum["self"] = (gap, [a, b])

        current = fk(q)
        delta = current.matrix[:3, 3] - start_pose.matrix[:3, 3]
        height = float(delta @ up)
        max_cross = max(max_cross, float(np.linalg.norm(delta - height * up)))
        max_rotation = max(max_rotation, float(np.linalg.norm(rotation_log(
            start_pose.matrix[:3, :3].T @ current.matrix[:3, :3]))))
        if previous_height is not None:
            worst_height_step = min(worst_height_step, height - previous_height)
        previous_height = height
        clearance_samples += 1

end = fk(waypoints[-1])
end_delta = end.matrix[:3, 3] - start_pose.matrix[:3, 3]
q_min, q_max = np.min(waypoints, axis=0), np.max(waypoints, axis=0)
joint_margin = float(np.min(np.minimum(q_min - limits.lower_rad, limits.upper_rad - q_max)))
dq = np.max(1.875 * np.abs(np.diff(waypoints, axis=0)) / duration, axis=0)
report = {
    "config_sha256": digest(config),
    "asset_manifest_sha256": digest(manifest_path),
    "geometry_mapping_sha256": digest(mapping_path),
    "seams_sha256": digest(seams_path),
    "asset_mesh_count": len(hulls),
    "self_pairs": len(pairs),
    "intervals": clearance_samples,
    "up_normal_in_L_arm_root": up.tolist(),
    "start_m": start_pose.matrix[:3, 3].tolist(),
    "lift_end_m": end.matrix[:3, 3].tolist(),
    "end_height_delta_m": float(end_delta @ up),
    "max_midpoint_lateral_deviation_m": max_cross,
    "max_midpoint_rotation_delta_rad": max_rotation,
    "min_midpoint_height_increment_m": worst_height_step,
    "l8_speed_upper_bound_m_s": tip_speed,
    "min_j2_rad": float(q_min[1]),
    "min_joint_position_margin_rad": joint_margin,
    "max_joint_speed_rad_s": float(np.max(dq)),
    "model_clearance_lower_bounds_m": minimum,
    "l8_geometry_check": "PASS" if (joint_margin > 0 and np.all(dq <= limits.velocity_rad_s)
         and tip_speed <= lift["proposed_max_tcp_speed_m_s"]
         and abs(float(end_delta @ up) - lift["height_m"]) <= 1e-7
         and max_cross <= 0.0001 and max_rotation <= 0.001
         and worst_height_step >= -1e-8) else "FAIL",
    "arm_hull_check": "PASS_DECLARED_EMPTY_MODEL" if all(v[0] > 0 for v in minimum.values()) else "UNRESOLVED",
    "full_collision": "UNKNOWN",
    "motion_enabled": False,
    "live_authorized": False,
    "q_waypoints_rad": [q.tolist() for q in waypoints],
}
print(json.dumps(report, indent=2, allow_nan=False))
```

</details>
