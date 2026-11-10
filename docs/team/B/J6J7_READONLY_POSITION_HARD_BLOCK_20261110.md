# J6/J7 只读位置硬阻塞（2026-11-10）

## 裁决

**不存在**已审计的 MotorV2（J6/J7）**只读位置**查询。  
因此 `ArmStateReader` 不能产出七轴有限 `q_rad`，`counts_as_live_valid=false`，`live_valid_arm_state` 保持硬阻塞，**正式抓取入口仍否**。

机读：`src/brick_stacking/arm/v2_wrist_readonly.py`（`HARD_BLOCK_ID=j6_j7_no_audited_readonly_position_query`）。

## 已审计 / 未审计对照

| 路径 | 内容 | 只读？ | 可用于 live VALID？ |
| --- | --- | --- | --- |
| A7 `0x06`（J1–J5） | float32 rad | 是 | 是（前五轴） |
| Flash mode `670b…`（J6/J7） | 控制模式 int | 是 | **否**（不是角度） |
| `MotorV2.read_initial_state` / Rest `FF×7+FD` | 状态切换后原始反馈 | **否**（失持） | **否**（副作用；非只读） |
| host_monitor J6/J7 `_read_angle_locked` | 调用 Rest | **否** | **否** |
| `c_left_wrist_rest_capture` | 显式 Rest（需支撑+授权） | **否** | **否**（现场授权采样，非正式只读 API） |
| 使能后 V2 打包反馈 U16 | 运行反馈 | 需使能/心跳 | **否**（量化/COM Theta 未审计） |

依据：[`LEFT_STATE_ACQUISITION.md`](../C/LEFT_STATE_ACQUISITION.md)、[`HARDWARE_INTERFACES.md`](../../hardware/HARDWARE_INTERFACES.md)、`tools/c_left_arm_readonly_probe.py`。

## 安全默认（本轮强制）

- **禁止** enable-motion / Rest / 大幅关节运动 / Flash 写入 / 构造会写模式的 P7 初始化路径。
- `ArmStateReader` 继续：J1–J5 位置 READ + J6/J7 **仅** mode READ；J6/J7 `q_rad=None` → `validity=INVALID`。
- 真机 `live-readonly` 仅允许上述已审计只读；失败软跳过；**不得**回退到 Rest 补角。
- Mock / recorded / fixture **不等于** live VALID。

## 解除条件（需另轮审计）

同时满足后才可实现并单测接通：

1. 厂商或源码确认的 **纯查询** 请求字节与应答布局（无 Rest / 无使能副作用）。
2. U16（或其它）→ rad 的量化与符号/零位版本，有现场交叉验证。
3. 新鲜度与绑定规则写入 `AUDITED_READONLY_POSITION_QUERY_BYTES` 等常量后，再改 `ArmStateReader`。

在此之前：骨架 `decode_audited_wrist_position_reply` / `try_read_wrist_positions_readonly` **一律拒绝**，保持 `counts_as_live_valid` 不可达。

## 对正式抓取的影响

| 问题 | 答案 |
| --- | --- |
| live VALID 是否可达？ | **否**（只读路径下） |
| 正式抓取是否仍否？ | **是（仍否）** |
| 现需用户开臂/Rest/大幅运动？ | **否**（软件硬阻塞；勿为补角动腕） |
| 用户可做的后续？ | 提供/确认 V2 纯查询协议文档，或单独授权支撑 Rest 采样（仍不算正式只读 API） |
