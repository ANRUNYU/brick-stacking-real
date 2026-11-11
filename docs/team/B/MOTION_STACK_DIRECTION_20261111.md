# 完整抓取运动栈 · 后续方向（2026-11-11）

**优先级**：先推进 T2（触块微抬）；本文件只冻结**后续**完整抓取轨迹方向，减少自研量。不抬 `control_ready`，不把方向写成已验收。

## 分层原则

| 层 | 自研 / 外借 | 说明 |
| --- | --- | --- |
| 侧向笛卡尔模板 + 桌面净空 | **自研** | 避桌、先抬后移是安全策略；通用库默认不做 |
| 7 轴 IK / FK | **外借** | 优先官方 SDK；备选 Pinocchio / MoveIt IK |
| 关节/笛卡尔插值 | **外借或保留** | SDK `move_j`/`move_l`；或仓内 quintic / Ruckig |
| PlanBundle + Gate/permit | **自研薄封装** | 统一 `J1..J7` `Trajectory` + `trajectory_hash` |
| 真机下发 | **薄适配** | 先有界；整段 H3 空跑另验收 |

## 首选外借（本机设备 = P7 A7_V2 + O6）

官方 Python SDK（`linkerbot-python-sdk`）已提供与 **7 关节同维** 的接口，应优先对接而非重写：

- `P7.forward_kinematics(angles[7])` / `P7.inverse_kinematics(Pose, current_angles?)`
- `move_j(target_joints[7])` — 主机侧插值流式下发（V2 无驱动端轨迹生成器）
- `move_p(Pose)` — IK 后关节运动（末端不保证直线）
- `move_l(Pose, …)` — 笛卡尔直线 + Slerp（适合接近/微抬短段）
- `get_joint_limits()` / URDF：`src/linkerbot/arm/kinetix/urdf/p7__left.urdf`

仿真/组合资源：`linker-bot/linker-sim-assets` 的 `components/arms/p7`（左/右 URDF+mesh）与 O6 手组装单元。

产品页：https://www.linkerbot.cn/details/LinkerArm （7 DoF、CAN、重复定位 ±0.043 mm 等；参数以实物为准）。

## 明确不做（方向约束）

- 不为「省事」改用 6 轴示教包硬扩成 7 轴。
- 不把合成 FK / Mock PlanBundle 当真机 H3。
- 不把 MotorV2 默认 **±12.5 rad** 反量化标成 `left_wrist_theta_ranges.verified=true`（仍仅 `sdk-report`）。
- 不绕过 SafetyGate / permit / 限位 / 净空。

## 与当前门控的关系

- **T1** 关节有界子集已 PASS（host_monitor 单轴/短组合）。
- **T2+** 触块与完整抓放：短笛卡尔段优先评估 SDK `move_l`（显式使能、极低速、可 cancel）；整段侧向抓放仍经自研模板 → SDK IK/`move_j` → PlanBundle 哈希 → Gate。
- 接线里程碑另开：`tools` 包装 `P7` 为可审计执行后端（默认 `motion_enabled=false`）。

## 参考链接

见 [VENDOR_LINKERBOT_RESOURCES_20261111.md](VENDOR_LINKERBOT_RESOURCES_20261111.md)。
