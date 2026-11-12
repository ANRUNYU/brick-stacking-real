# 100523 左臂示教关节来源审计

## 输入与映射

- 本次输入为 [left_preshape_q.json](left_preshape_q.json) 的 `q_rad`，样本 `left-preshape-20261112-100523`，阶段 `preshape_at_block`，左 P7 / `can2`，读取时间 `2026-11-12T02:35:13.734667+00:00`。文件原始字节 SHA-256 为 `a53d0261b80a5bd60f8967fb4d471d485841cb0eb497e2da05f156144ed7ce63`。
- 单位由原始字段 `q_rad` 和仓库 P7 读角约定确认。以弧度原值直传，七轴符号系数均为 `+1`。URDF 按表中局部轴向执行右手旋转，J3、J5 的 `−Z` 已由模型处理。实机正方向和零位仍待物理核验。 [播放器 FK](../../../../../../src/brick_stacking/wrist_handoff/wrist_path_player.py#L239) · [现场 SDK 源码审计](../../../../C/STATUS.md#第十批ssh现场坐标链与sdk行为确认c1-01c1-03m0-m2a)
- `sdk_audited` 沿用 Line H 对 J1–J5 的来源标记，A7 `0x06` 读角格式为 float32 rad。J6/J7 为 MotorV2 的 SDK 报告值，保持 `sdk_report_not_audited`，现场腕轴量程与符号仍未独立审计。原始记录保存了七轴角和读取时刻，采集函数、逐轴设备时间戳及原始 CAN 帧未随样本归档。SDK 源码审计中的 `P7.get_angles()` 返回缓存的电机角度。 [A7/MotorV2 读角审计](../../../J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md)

| 输入 | 锁定 URDF | 左臂电机 ID | URDF 局部轴 | 原值（rad） | 来源标记 |
| --- | --- | --- | --- | --- | --- |
| J1 | `L1_Joint` | 61 | `+Y` | −0.0511726438999176 | `sdk_audited` |
| J2 | `L2_Joint` | 62 | `+X` | −0.004673847928643227 | `sdk_audited` |
| J3 | `L3_Joint` | 63 | `−Z` | +0.33557960391044617 | `sdk_audited` |
| J4 | `L4_Joint` | 64 | `+Y` | −1.4567917585372925 | `sdk_audited` |
| J5 | `L5_Joint` | 65 | `−Z` | +1.7294782400131226 | `sdk_audited` |
| J6 | `L6_Joint` | 66 | `+Y` | +0.2161058976119623 | `sdk_report_not_audited` |
| J7 | `L7_Joint` | 67 | `+X` | −0.49725337605859465 | `sdk_report_not_audited` |

## 模型与复算

`config/models/p7_left/p7__left.urdf` 原始字节 SHA-256 为 `233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce`，与 `config/models/p7_left/LOCK.json` 相符。链从 `L_arm_root` 到 `L8_Link`，含 `L7_Link` → `L8_Link` 的固定 `L8_Joint`，平移 `[0.000025732, 0, -0.0455]` m，RPY 为零。矩阵将 `L8_Link` 的齐次列向量映射到 `L_arm_root`。完整矩阵见 [FK JSON](left_preshape_locked_urdf_fk.json)。

在播放器仓库根目录，用已安装 NumPy 的 Python 运行以下代码，标准输出为 FK JSON。Windows 上可用 `git clone -c core.autocrlf=false` 保留参与哈希校验的 LF 文件字节。按数值复核矩阵时使用绝对容差 `1e-12`。缺轴、轴序错误、单位字段无效、输入哈希变化或模型锁不符都会在输出前报错。

```python
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path("src").resolve()))

from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.wrist_handoff.constants import (
    CHILD_FRAME,
    JOINT_NAMES,
    PARENT_FRAME,
    SDK_MOTOR_IDS,
    SEED_PROVENANCE_DEFAULT,
)

folder = Path("docs/team/B/evidence/line_h/left_preshape_20261112_100523")
source = folder / "left_preshape_q.json"
raw_bytes = source.read_bytes()
raw_sha = sha256(raw_bytes).hexdigest()
sample = json.loads(raw_bytes)
q = sample.get("q_rad")
if sample.get("joint_names") != list(JOINT_NAMES):
    raise ValueError("expected J1 through J7 in order")
if (
    sample.get("joint_unit", "rad") != "rad"
    or not isinstance(q, list)
    or len(q) != len(JOINT_NAMES)
    or any(type(v) not in (int, float) or not math.isfinite(v) for v in q)
):
    raise ValueError("expected seven finite values in q_rad (radians)")
if raw_sha != "a53d0261b80a5bd60f8967fb4d471d485841cb0eb497e2da05f156144ed7ce63":
    raise ValueError("unexpected raw sample SHA-256")

model = Path("config/models/p7_left/p7__left.urdf")
lock_path = model.with_name("LOCK.json")
lock = json.loads(lock_path.read_bytes())
model_sha = sha256(model.read_bytes()).hexdigest()
expected_model_sha = "233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce"
if (
    lock["urdf_relpath"] != model.as_posix()
    or lock["urdf_sha256"] != expected_model_sha
    or model_sha != expected_model_sha
):
    raise ValueError("locked URDF mismatch")

urdf_names = [f"L{i}_Joint" for i in range(1, 8)]
positions = dict(zip(urdf_names, q, strict=True))
pose, meta = urdf_forward_kinematics(
    model, positions, base_frame=PARENT_FRAME, tip_frame=CHILD_FRAME,
)
if (
    meta["model_sha256"] != model_sha
    or meta["joint_names"] != urdf_names
    or (pose.target_frame, pose.source_frame) != (PARENT_FRAME, CHILD_FRAME)
):
    raise ValueError("FK chain or model mismatch")

result = {
    "sample_id": sample["sample_id"],
    "phase": sample["phase"],
    "side": sample["side"],
    "interface": sample["interface"],
    "read_utc": sample["read_utc"],
    "input_path": source.as_posix(),
    "input_sha256": raw_sha,
    "joint_unit": "rad",
    "joint_names": list(JOINT_NAMES),
    "q_rad": q,
    "urdf_joint_mapping": dict(zip(JOINT_NAMES, urdf_names, strict=True)),
    "input_to_urdf_sign": dict.fromkeys(JOINT_NAMES, 1),
    "motor_ids": dict(zip(JOINT_NAMES, SDK_MOTOR_IDS, strict=True)),
    "joint_provenance": dict(zip(JOINT_NAMES, SEED_PROVENANCE_DEFAULT, strict=True)),
    "joint_source_audit": (folder / "left_preshape_joint_source_audit.md").as_posix(),
    "urdf_path": model.as_posix(),
    "urdf_lock_path": lock_path.as_posix(),
    "urdf_sha256": model_sha,
    "fk_function": "brick_stacking.localization.urdf_chain.urdf_forward_kinematics",
    "parent_frame": pose.target_frame,
    "child_frame": pose.source_frame,
    "terminal_fixed_joint": "L8_Joint",
    "translation_unit": "m",
    "T_base_L8_teach": pose.matrix.tolist(),
    "hardware_match_verified": meta["hardware_match_verified"],
    "motion_enabled": meta["motion_enabled"],
}
print(json.dumps(result, indent=2, allow_nan=False))
```

## 已保存位姿核对

- 100523 同次采集目录只有左臂七轴与手型、相机记录等附件，缺少同样本 `flange_pose`，因此本次原始 `q_rad` 与历史保存位姿的一致性无法直接判定。
- 目录外的 `teach_preshape_20261111.json` 属于 `preshape_field_20261111`，其七轴来自另一采样。以该旧样本自身的 `q_rad` 重算，平移与其保存的 `flange_pose` 一致，旋转相差 `111.925°`。原因可由旋转乘序复现。对旧记录的 `[rz, ry, rx]`，按记录标签构造的 `Rz(rz) @ Ry(ry) @ Rx(rx)` 与其保存四元数一致，而 `Rx(rx) @ Ry(ry) @ Rz(rz)` 与锁定 URDF 重算一致，最大矩阵元素差约 `2.2e-16`。旧示教记录器按前一种乘序写入四元数。 [旧示教记录](../teach_preshape_20261111.json) · [记录器](../../../../../../tools/h_record_teach_sample_host.py)

## 附项：旧路径 215245 起点

对 `wrist_path_layer1_grasp_to_place_20261111_215245.json`（SHA-256 `349adb65352c820dc13ece77da26b575b269ab31af821244ec60e426758d16a3`）的 `segments[0].points[0].q_rad` 使用同一锁定 FK。旧 `grasp_ready` 的 L8 平移为 `[0.43704060430410385, 0.03568436322969936, -0.319015465944929]` m，与本次示教 L8 的三维平移距离为 `131.20281146128914` mm。 [旧路径](../../../../P/evidence/wrist_path_layer1_grasp_to_place_20261111_215245.json)
