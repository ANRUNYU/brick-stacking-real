# Host / Safety · `control_ready` / `motion_enabled` 抬起条件（2026-11-10）

本文件对照代码冻结 **host/safety** 使能条件，并给出机读 checklist。  
**硬约束**：本路径**永不**把 `control_ready` / `motion_enabled` 置 true，不开臂、不发 CAN。

相关实现：

- `src/brick_stacking/execution/host_control_readiness.py`
- `src/brick_stacking/execution/safety_gate.py`（`OfflineSafetyGate.issue_dry_run_diagnostic`）
- `tools/host_control_readiness.py`
- 证据：`docs/team/B/evidence/field_20261110/host_control_readiness_20261110.json`

M 侧 Permit 权威见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。

## 1. 代码中的抬起条件（查清结果）

### 1.1 `control_ready`

| 条件 | 代码依据 | 当前 |
| --- | --- | --- |
| 上游视觉证据门禁清 | `vision_pre_grasp_ready` / `evidence_gates_clear` | **PASS** |
| live `contracts.Permit` | `OfflineSafetyGate.check_step_evidence` | **MISSING**（dry-run draft ≠ live） |
| `PlanBundle.trajectory_hash` | shadow PlanBundle（并行线） | **PASS**（shadow；`executable=false`） |
| `ArmState.device_id` | recorded binding left P7 | **PASS**（recorded；非 live VALID） |
| offline dry_run 配置 | `OfflineSafetyGate` + MockArm | 路径可探测 + 签发诊断 |
| **host 策略决策抬升** | 本仓库无生产抬升路径 | **POLICY_HOLD** |

### 1.2 Dry-run / arm-disabled SafetyGate 签发诊断

| 入口 | 作用 | 是否动臂 |
| --- | --- | --- |
| `--probe-dry-run-arm-disabled` | MockArm + 拒无 permit 步 + `issue_dry_run_diagnostic` + plumbing | **否** |
| `issue_dry_run_diagnostic` | 组装 Permit 字段；`executable=false`；齐则 draft 过 gate | **否** |
| plumbing self-check | 标签探针 hash 证明签发→校验管线 | **否** |

当前结论（含 shadow PlanBundle）：

- `issuance_fields_complete=true`，`gate_accepts_draft=true`，`plumbing_ok=true`
- `only_hardware_enable_and_policy_remaining=true`（相对 **MockArm dry-run**）
- `live_permit=null`；`control_ready=false`；`formal_grasp_ready=false`

## 2. 硬缺口

| 缺口 | 类别 | 仅差操作员？ |
| --- | --- | --- |
| live `Permit` | live_permit | 否 |
| live VALID `ArmState` | software/field | 否（recorded ≠ live） |
| host 策略抬 `control_ready` | host_policy | 否 |
| host_monitor ENABLE | actuator_operator | 仅真机运动前 |

机读：

- `only_operator_enable_remaining=false`
- `needs_operator_physical_enable_now=false`
- `needs_operator_physical_enable_before_real_motion=true`
- dry-run `only_hardware_enable_and_policy_remaining=true`

## 3. CLI

```text
python tools/host_control_readiness.py \
  --pre-grasp-gaps docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json \
  --diagnostic-permit docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json \
  --plan-bundle docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json \
  --arm-state docs/team/B/evidence/field_20261110/recorded_arm_state_left_p7_20261110.json \
  --probe-dry-run-arm-disabled \
  --config config/offline_task.yaml \
  --output docs/team/B/evidence/field_20261110/host_control_readiness_20261110.json
```

## 4. 正式抓取裁决

| 问题 | 答案 |
| --- | --- |
| 正式抓取？ | **否** |
| diagnostic permit | `permit_eligible=true`；`executable=false` |
| live Permit | **null** |
| dry-run 签发 | 字段齐 + gate 接受 draft；**仍非 live** |
| 现在要用户物理开臂？ | **否** |
| 真机运动前要开臂？ | **是** |
