# 官方接口审计（2026-11-05）

> 本文保留2026-11-05静态官方审计。最新[实机接口](hardware/HARDWARE_INTERFACES.md)及[原始证据](handoff/20261107/interface_audit/README.md)记录了应答、角色与文件哈希。下文false/未连接描述当次历史审计；动作能力仍未验收。


这是静态源码/文档审计，不是 SDK 安装或真机验收。来源标记 `official_sdk`；实际硬件匹配均为 false。机器可读版本索引见 `sources.lock.json`。所有新业务代码独立实现，未复制第三方控制实现。

## 固定来源

| 仓库 | 本次固定 commit | 已核对内容 | 许可证 |
|---|---|---|---|
| [linker-sim-assets](https://github.com/linker-bot/linker-sim-assets/tree/d0224b8da58802fe7cb2e35dcc9771693c4543b6) | d0224b8da58802fe7cb2e35dcc9771693c4543b6 | README、P7/O6 meta、左右四个组件 URDF | 根目录未发现 LICENSE；再分发前待厂商明确 |
| [linkerbot-python-sdk](https://github.com/linker-bot/linkerbot-python-sdk/tree/927290b8e27f9e2df3cc5b0a0776c36e2fb5175e) | 927290b8e27f9e2df3cc5b0a0776c36e2fb5175e | P7 实现/运动文档、O6 角度文档 | MIT |
| [linkerhand-ros2-sdk](https://github.com/linker-bot/linkerhand-ros2-sdk/tree/0035f236c98b644aba6d9e972359df3fa1af4342) | 0035f236c98b644aba6d9e972359df3fa1af4342 | Topic-Reference、LICENSE | Apache-2.0 |

## 对工程有影响的发现

1. P7 组件左右各 7 个主动关节，名字分别 `L1_Joint..L7_Joint` / `R1_Joint..R7_Joint`，各 9 个 link；组件根 `L_arm_root` / `R_arm_root`，tool0 关联 `L8_Link` / `R8_Link`。这是资产命名，不能直接充当 SDK 电机 ID。
2. O6 左右 URDF 各 12 个 link、6 主动关节和 5 mimic。资产主动顺序为 thumb_cmc_yaw、thumb_cmc_pitch、index/middle/ring/pinky_mcp_pitch；SDK 角度顺序不是这份列表，禁止按数组位置直接连接。
3. 新 Python SDK `O6.angle.set_angles` 的 6 通道为 **0–100 无量纲**，顺序 thumb_flex、thumb_abd、index、middle、ring、pinky；`set_raw_angles` 使用 0–255；还存在可持久化映射表。读取接口为 `get_blocking` / `get_snapshot`。不能当弧度或复用 Rabokit 的归一化手势。
4. 旧手 ROS 2 文档列出 `/cb_left_hand_control_cmd` 等 0–255 接口和 `_arc` 接口，但通用例子并非 O6 专用。O6 的实际消息长度、通道、单位和反馈必须按设备/驱动核验，当前不绑定任何执行话题。
5. P7 SDK `move_j` / `move_p` / `move_l` 已在固定版本文档中确认；SDK 轨迹生成不等于全机避碰。`is_moving` 在所读实现中依赖运动计时器，不能替代真实到位反馈。
6. **P7 构造函数本身有硬件副作用**：创建 CAN 通信、检查电机、调用 `_ensure_v2_ptm_mode`；类文档明确涉及 V2 电机 Flash 控制模式。离线/普通只读诊断不能实例化它。`emergency_stop` 的当前实现是以缓存角度发送保持目标，不能等同物理急停。
7. 资产组件包含模板/装配约定；工作站 URDF 里的安装几何不是本机标定值。未下载/加载 mesh，没有启用仿真物理引擎，也没有碰撞规划验收。

四个 URDF 仅临时保存于被 Git 忽略的 `artifacts/source_audit/` 供只读审计；没有作为默认硬件模型打包发布。审计输出为同目录 `urdf_inspection.json`。

## 官方产品页

- [P7](https://www.linkerbot.cn/details/LinkerArm/)：核对产品名称与 7 自由度；宣传精度不记为本系统定位精度。
- [O6](https://www.linkerbot.cn/details/LinkerHandO6/)：6 主动+5 被动，触觉选配；不假设本机有触觉。
- [Gemini 335L](https://www.orbbec.com.cn/index/Product/info.html?cate=38&id=62)：所给链接对应头部型号，不用于替代腕部 335 的参数。

Orbbec 驱动适配尚未开发，具体 SDK/驱动 commit、depth unit、registration、optical frame 和时间戳模式在接相机前单独审计。当前 RecordedCamera 强制要求已转米、对齐、去畸变输入。

## v0.2 框架来源更新

部署目标由团队确认 Ubuntu 24.04 + ROS 2 Jazzy；没有因此添加厂商 SDK 运行依赖。旧仿真任务流程仅作 simulation_example 审查，详见 REFERENCE_REVIEW.md；新场景/任务/交接模块独立编写，没有复用其 common/stacking.py 或硬件适配器。飞书部署页读取失败，ROS 官方安装页受访问保护，均未作为已核对安装步骤的证据。
