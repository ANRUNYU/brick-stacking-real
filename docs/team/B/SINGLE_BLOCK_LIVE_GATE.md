# 单块抓放 · 真机门（本会话不执行）

**状态**：runbook only。软件闭环（侧向 PlanBundle + Mock 回放）可在 `control_ready=false` 下离线跑通；**真机 Rest / 开臂 / CAN 不在默认路径**。

**关联**：`PRE_GRASP_GATES_20261110.md`、`HOST_CONTROL_READY_20261110.md`、`J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md`、`THREE_TRACK_GRASP_DEV_PLAN.md` §3.5。

## 执行前必须再单独确认的两件事

在未获操作员**当场口头/书面再确认**前，禁止进入下列任一步：

1. **Rest 取角（腕部有支撑）** — 会短暂失持；不可默认代执行。
2. **一次有界开臂** — 仅在 Rest 证据与现场安全确认后；不可默认 `--enable-motion`。

确认之前：**不 Rest、不 `--enable-motion`、不开臂、不发 CAN。**

## 未解除则永不发真机命令

| 阻塞 | 说明 |
|------|------|
| J6/J7 | 仍无已审计**纯只读**取角协议；禁止空搜绕过（见硬阻塞文档） |
| live VALID 七轴 | 无 live 七轴 VALID → 无 live Permit |
| `control_ready` | reporter **硬持 false**；本会话不新增抬升开关 |
| C35 | 独立验证未做；包内 `accuracy_claim=FIT_ONLY`，禁止标成可下发 |
| 整臂碰撞 | `full_collision=UNKNOWN`；禁止改写成 PASS |

## 阶梯不可跳（T1→T2→T3→T4）

| 级 | 内容 | 未过则 |
|----|------|--------|
| **T1** | 无块空跑整段 PlanBundle | **不得碰块**；停在此级 |
| **T2** | 触块：下探 → 闭合 → 微抬 | 不得进入只抓 |
| **T3** | 只抓（Pick only） | 不得进入抓放 |
| **T4** | 抓起 + 放到十字槽 | 复检 PASS 且 ≤ §0.2 放置门 |

T1 未过禁止进入 T2。任一级失败：改方法，**不**放宽 §0.2 门控后强行下级。

## 软件包 vs 真机

- Schema：`m-single-block-plan-bundle-0.1`（与 shadow `m-shadow-plan-bundle-0.1` 分离）。
- 默认旗标：`executable=false`、`motion_enabled=false`、`control_ready=false`。
- Mock 回放只接受 `MockArm`（`hardware_enabled=false`）；手用内存 `MOCK_OPEN`/`MOCK_HOLD`。
- 本文件**不授权**把 Mock DONE 写成真机已完成。

## 本会话明确不做

十块、改生产 HSV 默认、提交 slot junk、O6 真机预设、伪造 live Permit、抬 `control_ready`、把 fit-only 标成可下发。
