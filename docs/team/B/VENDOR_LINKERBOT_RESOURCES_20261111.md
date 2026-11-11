# LinkerBot / Motorevo 设备资源索引（2026-11-11）

操作员提供；用于 T2+ 与完整抓取对接，**不**自动使能运动。

## 产品

| 资源 | URL | 用途 |
| --- | --- | --- |
| Linker Arm P7 产品页 | https://www.linkerbot.cn/details/LinkerArm | 7 DoF、CAN、负载/半径/精度规格（以实物为准） |

## 官方仓库

| 资源 | URL | 本仓库用途 |
| --- | --- | --- |
| URDF / 仿真资产（P7 + 手 + 工位） | https://github.com/linker-bot/linker-sim-assets | `components/arms/p7` 左/右 URDF+STL；O6 手与法兰组装；composer |
| Python SDK（臂） | https://github.com/linker-bot/linkerbot-python-sdk | `P7` FK/IK、`move_j`/`move_p`/`move_l`、`motor_v2`、`p7__left.urdf` |
| O6 灵巧手 ROS2 SDK | https://github.com/linker-bot/linkerhand-ros2-sdk | 手预设/状态（T2 闭合对接参考） |

## 与本仓库已锁定资产的关系

- 本仓已锁定主机 SDK 包内 `p7__left.urdf`（sha256 `233a0fd9…f7edce`）→ [`config/models/p7_left/`](../../config/models/p7_left/)。
- `linker-sim-assets` 中 P7 变体来源注明 `A7V2_50_4.27` / `p7_i1_dual_arm_description`；含 **L8/R8** 法兰虚链路（tool0）。对接笛卡尔 TCP 时应以官方 `tool0` / L8 为准，勿与仅 L1–L7 的旧假设混用而不声明。
- `motor_v2.py`（公开 SDK）Flash 索引仍见 **SAVE `0x00` / MODE `0x0B`**；Theta 量化默认 **±12.5 rad** — 继续记为 sdk-report，**禁止**写入 `verified=true` 量程表，除非厂商给出 COM Theta Flash 索引或协议手册。

## 检索备忘（2026-11-11）

- SDK 文档（zh）：`docs/zh/src/reference/p7/{kinematics,motion,state,config}.md`
- 仿真资产 README：units/workstations 组合加载；P7 基座碰撞为 named assemblies（LFS mesh）
- 更多信息以 GitHub 上述三仓为准；协议级 Flash 表仍可能需向销售/支持索取
