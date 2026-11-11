# 单块抓放 · 真机门

**状态**：操作员已于 2026-11-11 授权持续推进；支撑 Rest、**T1 单关节子集**与 **T1 短多关节有界空跑（J1–J5）均已 PASS**。仍按 T1→T4，不可跳级进 T2。软件闭环已离线可跑；真机默认仍 `control_ready=false`，每步显式门控。

**关联**：`PRE_GRASP_GATES_20261110.md`、`HOST_CONTROL_READY_20261110.md`、`J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md`、`THREE_TRACK_GRASP_DEV_PLAN.md` §3.5。

## 授权记录

| 项 | 状态 |
| --- | --- |
| 支撑下 Rest 取角（会失持） | **已授权**（2026-11-11 会话） |
| 有界开臂 | **已授权**（同会话；仍须 T1 空跑先过） |
| 默认 `--enable-motion` / 自动抬 `control_ready` | **否**（仍显式、有界） |

## 执行前现场确认（每次 Rest 前）

授权不等于当场可发。发 Rest 前操作员须确认：

1. **左腕 J6/J7 已可靠物理支撑**（失持不会砸桌/砸人）。
2. 工作区清人；急停可达。
3. 回复「腕已支撑，可以 Rest」后再由主机跑 `c_left_wrist_rest_capture`。

本轮（2026-11-11）操作员已回复该口令；Rest **已执行**（见下方证据）。

## 本轮已做到（2026-11-11）

| 步 | 结果 |
|----|------|
| 主机 Rest | **已执行** `docs/team/B/evidence/left_supported_rest_20261111_011818.json`；`status=RAW_SEVEN_AXIS_CAPTURED`；auth=`chat-20261111-wrist-supported-rest` |
| J1–J5 | Rest 后 A7 `position_sdk_rad` 已读回（有限角） |
| J6/J7 | 仅 `position_raw_u16`（66=32622，67=33179）；**无** audited `position_sdk_rad` |
| rest-draft | **诚实 GAP**：`left_wrist_theta_ranges.json` 仍 `verified=false` → 不得反量化为审计角；见 `t1_rest_draft_status_20261111.json` |
| SDK 报告角 | 可按 MotorV2 默认 ±12.5 反量化并标注 provenance=`sdk_default_pm_12_5_dequantize`；**≠** audited range_profile；**禁止**写 `verified=true` |
| URDF | 主机 SDK 包内有 `p7__left.urdf`（L6/L7 limit ±1.59）；摘录在 `evidence/host_sdk_snippets_20261111/`；runner 尚未接线真机执行 |
| T1 执行器 | 仅有 **有界 dry-plan 骨架**（`t1_bounded_live_runner`，默认 motion 关）；**无**整段 PlanBundle 真机执行器 |
| T1 子集真机 | **PASS**（2026-11-11）：`host_monitor` 已带 `--enable-motion`；J6 ENABLE-only 恢复持力（未 MOVE）→ J1 `step_deg=1.0` READY→ENABLE→MOVE→RELEASE；`|err|=4.3e-6 rad` ≪ 0.012；证据 `t1_bounded_single_joint_live_20261111_093412.json`；auth=`chat-20261111-operator-continue-t1-bounded` |
| T1 短多关节真机 | **PASS**（2026-11-11）：同会话门控；J6 ENABLE-only → 顺序 J1–J5 各 `step_deg=1.0` READY→ENABLE→MOVE→RELEASE（一轴失败即停）；各轴 `|err|` ≪ 0.012；证据 `t1_bounded_multi_joint_live_20261111_093852.json`；auth 同上；**仍非**整段 PlanBundle 真机轨迹 |
| T1 全量 / 整段空跑 | **未做**（无有界整段执行器）；不得据此进 T2 |
| `control_ready` / live Permit | 仍 false / 不伪造 |

## 未解除则永不发真机命令

| 阻塞 | 说明 |
|------|------|
| J6/J7 | 仍无已审计**纯只读**取角协议；禁止空搜绕过（见硬阻塞文档） |
| 腕量程 | COM Theta 未 verified；SDK ±12.5 仅可作 sdk-report，不可标 verified |
| live VALID 七轴 | 无 audited 七轴 → 无 live Permit；Rest attested draft 亦被量程缺口挡住 |
| `control_ready` | reporter **硬持 false**；本会话不新增抬升开关 |
| C35 | 独立验证未做；包内 `accuracy_claim=FIT_ONLY`，禁止标成可下发 |
| 整臂碰撞 | `full_collision=UNKNOWN`；禁止改写成 PASS |

## 阶梯不可跳（T1→T2→T3→T4）

| 级 | 内容 | 未过则 |
|----|------|--------|
| **T1** | 无块空跑（Rest 七轴 → 低速单关节/短多关节空跑；**单关节 + J1–J5 短多关节已 PASS**；整段 PlanBundle 真机仍缺） | **不得碰块**；停在此级 |
| **T2** | 触块：下探 → 闭合 → 微抬 | 不得进入只抓 |
| **T3** | 只抓（Pick only） | 不得进入抓放 |
| **T4** | 抓起 + 放到十字槽 | 复检 PASS 且 ≤ §0.2 放置门 |

说明：完整 PlanBundle 真机空跑仍未接线；**不得**把合成 FK PlanBundle 直接当真机 T1。优先 `host_monitor` 单关节小步（显式 `--enable-motion`）或未来有界 runner。

T1 未过禁止进入 T2。任一级失败：改方法，**不**放宽 §0.2 门控后强行下级。

## 软件包 vs 真机

- Schema：`m-single-block-plan-bundle-0.1`（与 shadow `m-shadow-plan-bundle-0.1` 分离）。
- 默认旗标：`executable=false`、`motion_enabled=false`、`control_ready=false`。
- Mock 回放只接受 `MockArm`（`hardware_enabled=false`）；手用内存 `MOCK_OPEN`/`MOCK_HOLD`。
- 本文件**不授权**把 Mock DONE 写成真机已完成。

## 一键 Rest（仅支撑确认后）

```bash
cd ~/brick-stacking-real
python3 tools/c_left_wrist_rest_capture.py \
  docs/team/B/evidence/left_supported_rest_<stamp>.json \
  --supported-wrist --allow-rest \
  --authorization-ref chat-20261111-wrist-supported-rest
```

离线 rest-draft / T1 状态（不发 CAN）：

```bash
python tools/t1_rest_draft_and_status.py \
  --rest-capture docs/team/B/evidence/left_supported_rest_20261111_011818.json \
  --range-profile calibration/measurement_templates/left_wrist_theta_ranges.json \
  --rest-state-capture --attest-rest-for-pregrasp --urdf-available \
  --output docs/team/B/evidence/t1_rest_draft_status_20261111.json
```

## 本会话明确不做

十块、改生产 HSV 默认、提交 slot junk、O6 真机预设、伪造 live Permit、抬 `control_ready`、把 fit-only / SDK ±12.5 标成可下发或 verified。
