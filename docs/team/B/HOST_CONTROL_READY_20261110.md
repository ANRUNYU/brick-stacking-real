# Host / Safety · 门控阶梯与 `control_ready`（2026-11-10）

本文件对照代码冻结 **host/safety** 使能条件，并给出机读 checklist。

## 0. 门控阶梯（权威）

| 字段 | 含义 | 何时可为 true |
| --- | --- | --- |
| `vision_pre_grasp_ready` | 视觉侧 pre_grasp 证据门禁清 | `pre_grasp_gates.evidence_gates_clear` |
| `dry_run_grasp_entry_ready` | dry-run / arm-disabled 全链可进入 | vision + diagnostic eligible + PlanBundle hash + ArmState.device_id（recorded/mock OK）+ dry-run 签发字段齐且 gate 接受 draft |
| `formal_grasp_entry_allowed` | **可进入正式抓取** | dry-run ready + **validated live `contracts.Permit`** + **`counts_as_live_valid`** |
| `control_ready` | host 控制就绪（真机大幅运动前置） | **本 reporter 恒 false**（大幅运动安全硬持有）。前置可审计：formal + 显式 attest；抬升推迟到专用 host 路径 |

**默认安全**：`control_ready=false`、`motion_enabled=false`；operator policy attest **已实现但不自动打开**（`attested=false`）；即使 attest 打开，本 checklist **仍不抬** `control_ready`。  
**硬约束**：不伪造 live Permit；不开臂；不发运动；`dry_run_grasp_entry_ready` 可为 true。真机只读非必须——本轮以 Mock/recorded 机读路径验收。

相关实现：

- `src/brick_stacking/execution/host_control_readiness.py`（schema `host-control-readiness-0.2`）
- `src/brick_stacking/arm/arm_state_validity.py`（recorded vs live VALID 分类）
- `src/brick_stacking/execution/host_policy_attest.py`
- `src/brick_stacking/execution/safety_gate.py`（`OfflineSafetyGate.issue_dry_run_diagnostic`）
- `tools/host_control_readiness.py`
- `tools/arm_state_live_or_recorded.py`
- `tools/host_control_ready_policy_attest.py`
- 证据：`docs/team/B/evidence/field_20261110/host_control_readiness_20261110.json`、`arm_live_or_recorded_*_20261110.json`

### 0.1 live VALID 臂读条件（`counts_as_live_valid`）

| 条件 | recorded binding | fixture-valid（软件） | MockArm | ArmStateReader 只读 |
| --- | --- | --- | --- | --- |
| `source` | recorded | recorded/mock | mock | real |
| `validity` | INVALID | VALID | VALID | **INVALID**（J6/J7 无已审计只读位置查询） |
| `counts_as_live_valid` | **false** | **false** | **false** | **false**（直至七轴有限角度可读） |

机读：`arm_feedback.counts_as_live_valid`；checklist `live_valid_arm_state` 与 `arm_state_device_id` 分开——后者 recorded 可 PASS，前者仍 MISSING。  
**硬阻塞文档**：[J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md](J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md)（`hard_block=j6_j7_no_audited_readonly_position_query`；骨架 `v2_wrist_readonly.py`；禁止 Rest 回退）。  
CLI：`python tools/arm_state_live_or_recorded.py --mode recorded|fixture-valid|live-readonly --output …`（`live-readonly` 软失败可跳过；不 enable-motion / 不 Rest）。

### 0.2 Rest 双重门控（均默认关）

| 字段 | 默认 | 含义 |
| --- | --- | --- |
| `rest_state_capture_available` | **true** | 软件门控已接线（可研究） |
| `rest_state_capture_enabled` | **false** | CLI `--rest-state-capture` 或 env `BRICK_STACKING_REST_STATE_CAPTURE=1` |
| `attest_rest_for_pregrasp_enabled` | **false** | CLI `--attest-rest-for-pregrasp` 或 env `BRICK_STACKING_ATTEST_REST_FOR_PREGRASP=1` |
| `dual_rest_pregrasp_gates_open` | **false** | 两门均开 |
| `blocked_unless_rest_attested` | **true**（双重门未齐） | 默认路径不把 Rest 当真机 live VALID 解法 |
| `live_arm_via` | `null` / `rest_attested` | 双重门 + 结构合法 Rest 草案时旁路 `j6_j7_readonly`（≠ 已审计只读） |

- **失持 ≠ 大幅轨迹**：Rest 会丢腕持力，但不是 `--enable-motion` / 轨迹；Goal「不开臂/CAN」按禁止轨迹解释。
- **CI / 默认路径绝不自动 Rest 真机**；`rest-draft` 模式只离线消费已有捕获 JSON。
- 仅开 `rest_state_capture`：可构造结构上 `counts_as_live_valid` 的 *草案*；formal 仍被 `j6_j7_readonly` 挡住；**不**抬 `control_ready`。
- **双重门全开** + Rest JSON 结构 live VALID：`live_arm_via=rest_attested`；清除 formal ladder 上的 `j6_j7_readonly`；可签发/校验 Rest-attested Permit 草案（`executable=false`；耐久 `live_permit=null`）；在 dry-run 等门已过时可置 `formal_grasp_entry_allowed=true`。
- **永不**抬 `control_ready` / 发轨迹；Rest ≠ 已审计 J6/J7 只读。
- 实现：`src/brick_stacking/arm/rest_state_capture.py`、`issue_rest_attested_permit_draft`。

M 侧 Permit 权威见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。

## 1. 代码中的抬起条件

### 1.1 阶梯对照（当前证据）

| 门 | 当前 | 依据 |
| --- | --- | --- |
| `vision_pre_grasp_ready` | **true** | pre_grasp gaps |
| `dry_run_grasp_entry_ready` | **true**（探测后） | MockArm dry-run 全链 + shadow PlanBundle + recorded arm id |
| `formal_grasp_entry_allowed` | **false**（默认）/ **true**（双重 Rest attest + 合法草案 + dry-run） | 默认缺 live Permit + live VALID；双重门下 `live_arm_via=rest_attested` 可过 |
| `control_ready` | **false**（硬持有） | reporter 永不抬升；attest 默认关；无大幅运动解锁 |

### 1.2 Dry-run / arm-disabled SafetyGate 签发诊断

| 入口 | 作用 | 是否动臂 |
| --- | --- | --- |
| `--probe-dry-run-arm-disabled` | MockArm + 拒无 permit 步 + `issue_dry_run_diagnostic` + plumbing | **否** |
| `issue_dry_run_diagnostic` | 组装 Permit 字段；`executable=false`；齐则 draft 过 gate | **否** |

当前结论（含 shadow PlanBundle）：

- `issuance_fields_complete=true`，`gate_accepts_draft=true`，`plumbing_ok=true`
- `only_hardware_enable_and_policy_remaining=true`（相对 **MockArm dry-run**）
- `dry_run_grasp_entry_ready=true`
- `live_permit=null`；`formal_grasp_entry_allowed=false`；`control_ready=false`

### 1.3 Operator policy attest（不自动打开）

```text
python tools/host_control_ready_policy_attest.py \
  --operator "<name>" \
  --evidence-ref docs/team/B/evidence/field_20261110/host_control_readiness_20261110.json \
  --output config/observed/host_control_ready_policy_attest_20261110.json
# 默认 attested=false。仅在明确决策后加 --attested。
```

即使 `attested=true` 且 formal 条件将来满足，**本 reporter 仍输出 `control_ready=false`**（大幅运动安全）；抬升留给合并 main 后的专用 host 路径。

## 2. 硬缺口（相对「可进入正式抓取」）

| 缺口 | 类别 | 仅差操作员？ |
| --- | --- | --- |
| live `Permit`（SafetyGate 校验通过） | live_permit | 否 |
| live VALID `ArmState`（`counts_as_live_valid`：`source=real` + `validity=VALID` + 七轴有限 `q_rad`） | software/field | 否（recorded/mock ≠ live；ArmStateReader 现因 J6/J7 仍 INVALID） |
| operator policy attest（抬 `control_ready`） | host_policy | 是（显式使能；**默认关**） |
| host_monitor ENABLE | actuator_operator | 仅真机运动前 |

机读（`gate_ladder` / 顶层）：

- `can_enter_formal_grasp=false`
- `formal_grasp_entry_missing` ⊇ `live_contracts_Permit_validated`, `live_VALID_ArmState_source_real`
- **`formal_grasp_blocked_by=["j6_j7_readonly","awaiting_live_arm"]`**（dry-run 软件已尽时的根因）
- **`live_permit_path.status=software_exhausted_awaiting_live_arm`**（`executable=false`；`live_permit=null`；未伪造）
- `control_ready_missing` ⊇ `formal_grasp_entry_allowed`, `operator_policy_attest_control_ready`, `reporter_hard_hold_no_large_motion_elevation`
- `reporter_never_raises_control_ready=true` / `reporter_never_raises_motion_enabled=true`
- `only_operator_enable_remaining=false`
- `needs_operator_physical_enable_now=false`
- `needs_operator_physical_enable_before_real_motion=true`

## 3. CLI

```text
python tools/host_control_readiness.py \
  --pre-grasp-gaps docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json \
  --diagnostic-permit docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json \
  --plan-bundle docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json \
  --arm-state docs/team/B/evidence/field_20261110/recorded_arm_state_left_p7_20261110.json \
  --operator-policy-attest config/observed/host_control_ready_policy_attest_20261110.json \
  --probe-dry-run-arm-disabled \
  --config config/offline_task.yaml \
  --output docs/team/B/evidence/field_20261110/host_control_readiness_20261110.json
```

## 4. 正式抓取裁决

| 问题 | 答案 |
| --- | --- |
| 可进入正式抓取？（默认路径） | **否**（`formal_grasp_entry_allowed=false`；仍 `j6_j7_readonly`） |
| 可进入正式抓取？（双重 Rest attest + 合法草案 + dry-run） | **是**（`live_arm_via=rest_attested`；`live_permit_path.status=rest_attested_permit_validated`；`executable=false`） |
| dry-run 入口就绪？ | **是**（`dry_run_grasp_entry_ready=true`） |
| Permit 软件路径（默认） | **已尽**：`software_exhausted_awaiting_live_arm`；`blocked_by=j6_j7_readonly + awaiting_live_arm` |
| Permit（双重 Rest attest） | Rest-attested 字段校验草案可过 formal 臂门；耐久 `live_permit=null`；**非**可执行签发 |
| diagnostic permit | `permit_eligible=true`；`executable=false`；可选 shadow PlanBundle/recorded 臂 → `PRESENT_FROM_*`（≠ live） |
| `control_ready` | **false**（reporter 硬持有；attest 默认关） |
| 现在要用户物理开臂？ | **否** |
| 是否需用户使能？ | 默认不必；仅研究/正式 Rest-attested 入口时显式开双重门；**禁止**默认 `--enable-motion`；抬 `control_ready` 另需 `--attested` |
| 真机大幅运动前要开臂？ | **是**（且需专用 elevation 路径；本分支 checklist 不解锁） |
| Goal complete？ | **是（入口可达已证明）**：默认仍 false；双重门测试/审计 JSON 中可为 true；证据见 `formal_grasp_entry_audit_20261110.json`。**风险：腕失持**。 |
| Goal complete？ | **否**（见 `docs/team/B/evidence/field_20261110/formal_grasp_entry_audit_20261110.json`；勿把 dry-run 就绪偷换成 complete） |
