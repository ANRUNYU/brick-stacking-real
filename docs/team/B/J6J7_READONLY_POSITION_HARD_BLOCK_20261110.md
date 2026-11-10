# J6/J7 只读位置硬阻塞（2026-11-10 / 检索更新 2026-11-11）

## 裁决

**不存在**已审计的 MotorV2（J6/J7）**只读位置**查询。  
2026-11-11 全库 + 主机 pinned SDK（`motor_v2.py` SHA256 `6f45000ba0f7f049e0a23b7ddceb318154b9672a5181472ea899099ea3127aba`）穷尽检索后：**仍无**可进入 `pending_protocol_audit` 的位置读角载荷（`ENABLE_PENDING_PROTOCOL_AUDIT` 默认 **false**，且 payload 为空）。

**同日仓库外检索（Web + 本机只读路径）亦否定**：未找到 Motorevo CAN 协议手册、Flash COM Theta 索引图、或纯位置/状态查询字节。公开 `linkerbot-python-sdk` `main` 的 `motor_v2.py`（fetch SHA256 `6f45000b…`，已与主机 pin 对齐）Flash 仍仅 `0x00`/`0x0B`；Motorevo-Studio 仓仅 EXE。机读证据：[`evidence/field_20261110/j6j7_external_protocol_search_20261111.json`](evidence/field_20261110/j6j7_external_protocol_search_20261111.json)。

因此 `ArmStateReader` 不能产出七轴有限 `q_rad`，`counts_as_live_valid=false`，`live_valid_arm_state` 保持硬阻塞，**正式抓取入口仍否**。  
**Goal 不得标 complete**——现约束下（禁 Rest / 禁 `--enable-motion` / 禁伪造 live VALID）**无法仅靠软件解除** `j6_j7_readonly`；**外部依赖仍是厂商手册/索引（或书面确认无纯查询）**。

机读：`src/brick_stacking/arm/v2_wrist_readonly.py`（`HARD_BLOCK_ID=j6_j7_no_audited_readonly_position_query`；`candidate_search_report()` / `EXTERNAL_PROTOCOL_SEARCH`）。

## 仓库外检索范围与否定结论（2026-11-11）

| 通道 | 范围 | 结果 |
| --- | --- | --- |
| WebSearch / WebFetch | Motorevo 官网与产品页、`docs.linkerhub.work` A7/P7 文档、GitHub `linkerbot-python-sdk` `motor_v2.py`、DeepWiki、通用「CAN 协议/Flash Theta」PDF 检索 | **无** Motorevo 协议 PDF；§6.3.2 仅见于 SDK 注释引用；A7 `get_angles` 需 `enable()`（禁） |
| 本机只读 | Desktop / Downloads / Documents / `E:\OneDrive\Desktop`；模式 `*motor*v2*` / `*Motorevo*` / `*LinkerBot*` / `*protocol*` / 相关 `*.pdf` | 命中均为 **LinkerHand 灵巧手** SDK/报告或 PEAK 驱动安装包；**无** MotorV2 手册或 Theta 索引 |
| 公开 SDK 交叉 | `raw.githubusercontent.com/.../motor_v2.py` vs 主机 pin `6f45000b…` | Flash 索引仍仅 SAVE/MODE；**无**纯查询字节；**未**接入 `pending_protocol_audit` |

**否定结论**：在现检索范围内，**找不到**可落地的纯位置查询载荷或 Flash Theta 索引；**不要**把 Goal 标 complete；**不要**反复空转相同库内 8 类候选。

## 已审计 / 未审计对照

| 路径 | 内容 | 只读？ | 可用于 live VALID？ |
| --- | --- | --- | --- |
| A7 `0x06`（J1–J5） | float32 rad | 是 | 是（前五轴） |
| Flash mode `670b…`（J6/J7） | 控制模式 int | 是 | **否**（不是角度） |
| Flash 通用 `_read_flash_param(index)` | 任意 index 的 READ 帧形 | 是（协议形） | **否**（SDK 仅定义 `0x00` SAVE / `0x0B` MODE；Theta MIN/MAX **无索引**；即使有也是量程不是 live 角） |
| `MotorV2.read_initial_state` / Rest `FF×7+FD` | 状态切换后原始反馈 | **否**（失持） | **否**（副作用；非只读） |
| Enter Motor `FF×7+FC` / P-T-M 控制帧 | 使能或施 PD 目标 | **否** | **否** |
| host_monitor J6/J7 `_read_angle_locked` | 调用 Rest | **否** | **否** |
| `c_left_wrist_rest_capture` | 显式 Rest（需支撑+授权） | **否** | **否**（现场授权采样，非正式只读 API） |
| `rest_state_capture` 门控（默认关） | 离线把已有 Rest 结果编成 live VALID *草案* | **否**（不发送；真机 Rest 另授权） | 单门：**否**（仍 `j6_j7_readonly`）；**双重门** `--attest-rest-for-pregrasp`：formal 可经 `live_arm_via=rest_attested`（≠ 已审计只读；不抬 `control_ready`） |
| 使能后 V2 打包反馈 U16 | 运行反馈 | 需使能/心跳 | **否**（量化/COM Theta 未审计） |
| 被动 CAN 监听（C21） | 无发送 | 是 | **否**（空闲窗口 0 帧） |
| SDK 默认 ±12.5 rad 反量化 | 注释出厂量程 | N/A | **否**（未现场读回；`left_wrist_theta_ranges.json` 仍 null） |

依据：[`LEFT_STATE_ACQUISITION.md`](../C/LEFT_STATE_ACQUISITION.md)、[`HARDWARE_INTERFACES.md`](../../hardware/HARDWARE_INTERFACES.md)、`tools/c_left_arm_readonly_probe.py`、主机 `motor_v2.py` 源码只读核对。

## 候选评估（朝解除硬阻塞；无一合格）

| 候选 id | 运动/Rest/使能？ | 证据 | `pending_protocol_audit`？ | 结论 |
| --- | --- | --- | --- | --- |
| `a7_cmd_0x06_on_v2_ids` | 否 | 弱 | 否 | MotorV2 无 A7 寄存器读路径 |
| `flash_control_mode_0x0b` | 否 | 强（已审计） | 否 | 只读但非角度 |
| `flash_generic_read_unknown_theta_indices` | 否 | 仅协议形 | 否 | **禁止盲猜索引**；且非 live 角 |
| `rest_ff7_fd_read_initial_state` | **是（Rest）** | 强 | 否 | 唯一无使能的取角路径，副作用失持 |
| `enter_motor_fc_or_ptm_stream` | **是** | 强 | 否 | 使能/施力目标 |
| `passive_can_listen` | 否 | 现场 C21 | 否 | 无自发反馈流 |
| `host_monitor_j6j7_read_angle` | **是（Rest）** | 强 | 否 | 包装 Rest |
| `sdk_default_pm_12_5_u16_map` | 取决于馈源 | SDK 默认未核验 | 否 | 量化未审计 |

`ENABLE_PENDING_PROTOCOL_AUDIT`：**默认 false**。打开后若仍无 `position_query_bytes`，实现仍拒绝碰总线，**不会**产出 `counts_as_live_valid`。

## 安全默认（本轮强制）

- **禁止** `--enable-motion` / 大幅关节轨迹 / Flash 写入 / 构造会写模式的 P7 初始化路径。
- **Rest 双重门控**（均 **默认 false**）：  
  - `--rest-state-capture` / `BRICK_STACKING_REST_STATE_CAPTURE`  
  - `--attest-rest-for-pregrasp` / `BRICK_STACKING_ATTEST_REST_FOR_PREGRASP`  
  - 失持 Rest ≠ 大幅轨迹；**CI / 默认路径绝不自动 Rest 真机**；不发 CAN Rest。  
  - 仅第一门：结构 live VALID 草案，formal 仍 `j6_j7_readonly`。  
  - **两门全开** + 合法 Rest 草案：`live_arm_via=rest_attested` 旁路 formal 上的 `j6_j7_readonly`；Permit 接同一 attest 链；**永不**抬 `control_ready`；**≠** 已审计只读。  
  - readiness：`blocked_unless_rest_attested=true` 直至双重门齐。
- **禁止** 对 Flash index 做盲扫以“碰运气”找 Theta。
- `ArmStateReader` 继续：J1–J5 位置 READ + J6/J7 **仅** mode READ；J6/J7 `q_rad=None` → `validity=INVALID`。
- 真机 `live-readonly` 仅允许上述已审计只读；失败软跳过；**不得**在默认路径回退到 Rest 补角。
- Mock / recorded / fixture **不等于** live VALID。

## 解除条件（需外部输入；软件 alone 不够）

同时满足后才可实现并单测接通：

1. 厂商手册或源码确认的 **纯查询** 请求字节与应答布局（无 Rest / 无使能 / 无 P-T-M 目标副作用），**或**厂商书面确认不存在此类查询（则只能走另授权的支撑 Rest，且仍非正式只读 API）。
2. U16（或其它）→ rad 的量化与符号/零位版本，有现场交叉验证（优先 Flash 读回本机 COM Theta MIN/MAX，索引须厂商给出）。
3. 新鲜度与绑定规则写入 `AUDITED_READONLY_POSITION_QUERY_BYTES` 等常量后，再改 `ArmStateReader`。

### 需用户提供 / 授权的下一步（Goal 外部依赖；软件 alone 不够）

1. **Motorevo CAN 协议手册**（SDK 引用 §6.3.2 打包帧）：纯状态/位置查询命令（若有）的精确 8 字节请求与应答；Flash 参数表中 CAN COM Theta MIN/MAX（及任何 live 位置相关）**索引号**。
2. 公开产品页与本轮 Web/本机检索均无协议 PDF；联系厂商或 LinkerBot 索取与本驱动栈匹配的手册（例：`sales@mail.motorevo.cn`）。
3. （可选）在腕部可靠支撑下，授权 **示波器 / candump** 对照一次 Rest 与一次心跳反馈布局——仅交叉验证，**不能**在无手册纯查询时冒充正式只读 API。

在此之前：骨架 `decode_audited_wrist_position_reply` / `try_read_wrist_positions_readonly` **一律拒绝**，`ENABLE_PENDING_PROTOCOL_AUDIT` 保持默认关且 payload 空；只读路径下 `counts_as_live_valid` 仍不可达。

**Goal（可进入正式抓取）**：在 **双重 Rest attest** + 结构合法 Rest 草案 + dry-run 证据下入口已可达（见审计 JSON）；默认路径仍否；**风险：腕失持**。已审计只读协议仍缺，不把 Rest 标成 audited readonly。

## 对正式抓取的影响

| 问题 | 答案 |
| --- | --- |
| live VALID（已审计只读）是否可达？ | **否** |
| 正式抓取（默认路径）？ | **仍否** |
| 正式抓取（双重 Rest attest + 合法草案）？ | **可达**（`live_arm_via=rest_attested`；`control_ready` 仍 false） |
| 现需用户开臂/`--enable-motion`/大幅轨迹？ | **否** |
| 是否需用户打开双重门？ | 仅 Rest-attested formal 入口时；默认关，CI 不开 |
| Goal complete？ | **是（入口可达已证明；默认仍 false；证据在仓库）** |
