# Host / Safety · 门控阶梯与 `control_ready`（2026-11-10）

本文件对照代码冻结 **host/safety** 使能条件，并给出机读 checklist。

## 0. 门控阶梯（权威）

| 字段 | 含义 | 何时可为 true |
| --- | --- | --- |
| `vision_pre_grasp_ready` | 视觉侧 pre_grasp 证据门禁清 | `pre_grasp_gates.evidence_gates_clear` |
| `dry_run_grasp_entry_ready` | dry-run / arm-disabled 全链可进入 | vision + diagnostic eligible + PlanBundle hash + ArmState.device_id（recorded/mock OK）+ dry-run 签发字段齐且 gate 接受 draft |
| `formal_grasp_entry_allowed` | **可进入正式抓取** | dry-run ready + **validated live `contracts.Permit`** + **`counts_as_live_valid`** |
| `control_ready` | host 控制就绪 | formal allowed + **显式** `operator_policy_attest.attested=true` |

**默认**：`control_ready=false`；operator policy attest 开关**已实现但不自动打开**（`config/observed/host_control_ready_policy_attest_20261110.json` 中 `attested=false`）。  
**硬约束**：不伪造 live Permit；不开臂；不发运动；`motion_enabled` 仍默认 false。真机只读非必须——本轮以 Mock/recorded 机读路径验收。

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
CLI：`python tools/arm_state_live_or_recorded.py --mode recorded|fixture-valid|live-readonly --output …`（`live-readonly` 软失败可跳过；不 enable-motion / 不 Rest）。

M 侧 Permit 权威见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。

## 1. 代码中的抬起条件

### 1.1 阶梯对照（当前证据）

| 门 | 当前 | 依据 |
| --- | --- | --- |
| `vision_pre_grasp_ready` | **true** | pre_grasp gaps |
| `dry_run_grasp_entry_ready` | **true**（探测后） | MockArm dry-run 全链 + shadow PlanBundle + recorded arm id |
| `formal_grasp_entry_allowed` | **false** | 缺 live Permit + live VALID 臂（recorded ≠ live） |
| `control_ready` | **false** | formal 未过 + attest 关闭 |

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

即使 `attested=true`，若 `formal_grasp_entry_allowed=false`，`control_ready` 仍保持 false。

## 2. 硬缺口（相对「可进入正式抓取」）

| 缺口 | 类别 | 仅差操作员？ |
| --- | --- | --- |
| live `Permit`（SafetyGate 校验通过） | live_permit | 否 |
| live VALID `ArmState`（`counts_as_live_valid`：`source=real` + `validity=VALID` + 七轴有限 `q_rad`） | software/field | 否（recorded/mock ≠ live；ArmStateReader 现因 J6/J7 仍 INVALID） |
| operator policy attest（抬 `control_ready`） | host_policy | 是（显式使能；**默认关**） |
| host_monitor ENABLE | actuator_operator | 仅真机运动前 |

机读（`gate_ladder`）：

- `can_enter_formal_grasp=false`
- `formal_grasp_entry_missing` ⊇ `live_contracts_Permit_validated`, `live_VALID_ArmState_source_real`
- `control_ready_missing` ⊇ `formal_grasp_entry_allowed`, `operator_policy_attest_control_ready`
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
| 可进入正式抓取？（`formal_grasp_entry_allowed` / `can_enter_formal_grasp`） | **否** |
| dry-run 入口就绪？ | **是**（`dry_run_grasp_entry_ready=true`） |
| diagnostic permit | `permit_eligible=true`；`executable=false` |
| live Permit | **null**（未伪造） |
| `control_ready` | **false**（formal 未过 + attest 默认关） |
| 现在要用户物理开臂？ | **否** |
| 是否需用户使能？ | **现在不必**开臂；正式抓取前还需 live Permit + live 臂读；抬 `control_ready` 另需显式 `--attested` |
| 真机运动前要开臂？ | **是** |
