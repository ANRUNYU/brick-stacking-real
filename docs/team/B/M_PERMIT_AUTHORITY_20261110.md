# M 侧 Permit 签发权威与 shadow vs live（2026-11-10）

本分支统一承载原 V/M 代码。本文冻结 **谁能签发什么**，并说明 readiness 的 diagnostic 进展。

## 权威

| 产物 | 权威签发方 | 可否执行运动 |
| --- | --- | --- |
| `contracts.Permit`（**live**） | **D/M SafetyGate**（执行前；`OfflineSafetyGate.check_step_evidence` 校验） | 是（在 A 独立复核后） |
| `safety-gate-dry-run-issuance-0.1`（**dry-run/arm-disabled 签发诊断**） | `OfflineSafetyGate.issue_dry_run_diagnostic`（仅 `MockArm` + `hardware_enabled=False`） | **否**（`executable=false`；`live_permit=null`） |
| `m-diagnostic-permit-eligibility-0.1`（**shadow/diagnostic**） | `pre_grasp_gates` / `tools/pre_grasp_readiness.py` | **否**（`executable=false`） |
| `control_ready` / `motion_enabled` | host/safety 路径（见 [HOST_CONTROL_READY_20261110.md](HOST_CONTROL_READY_20261110.md)） | `control_ready` 仅在 `formal_grasp_entry_allowed` + **显式** operator policy attest 后可抬；attest **默认关**；`motion_enabled` 仍默认 false |
| `dry_run_grasp_entry_ready` | host checklist dry-run 全链 | **是（dry-run only）**；不等于正式抓取 |
| `formal_grasp_entry_allowed` | host gate ladder（live Permit + live arm；或双重 Rest attest + Rest 草案） | 默认 **false**；双重 Rest attest 下可为 **true**（`live_arm_via=rest_attested`；耐久 `live_permit=null`） |
| Rest-attested Permit 草案 | `issue_rest_attested_permit_draft`（需双重门） | **否**（`executable=false`；接同一 attest 链） |

契约依据：`docs/CONTRACTS.md` §4；`docs/THREE_TRACK_GRASP_DEV_PLAN.md` M-10。

## Live Permit 签发路径（查清）

1. **上游资格**：`pre_grasp_gates` 证据齐 → `permit_eligible=true` + shadow diagnostic（非 Permit）。
2. **执行前签发**：D/M SafetyGate 在执行时刻用新鲜 `ArmState` + `PlanBundle.trajectory_hash` + config/calib/scene 版本生成短期 `contracts.Permit`。
3. **门禁校验**：`OfflineSafetyGate.check_step_evidence` 要求 permit 非空、字段与 step context 逐字段匹配、剩余有效期落在 offline freshness 窗口内。
4. **独立复核**：A 再检硬件身份 / 起点 / 限速限位；通过后才可真运动（另需 host 抬 `control_ready` + 执行器使能）。

本分支 **尚无** 生产 live 签发器把 `contracts.Permit` 写入正式抓取路径；live `permit` 在 readiness / host checklist 恒为 `null`。

## Dry-run / shadow 变体

| 变体 | 入口 | 行为 |
| --- | --- | --- |
| shadow eligibility | `build_diagnostic_permit` | 证据够评估 live 资格；不填签发时钟 / 臂 ID / PlanBundle |
| dry-run issuance diagnostic | `OfflineSafetyGate.issue_dry_run_diagnostic` | MockArm 下组装 Permit **字段**；可填 mock `device_id` + 签发时钟；消费 shadow PlanBundle `trajectory_hash`；`executable=false` |
| plumbing self-check | 同上（标签探针 hash） | 用 `dry-run-probe:safety-gate-plumbing-only` 证明签发→`check_step_evidence` 管线通 |
| live check（拒） | `check_step_evidence(permit=None)` | 无 permit 恒拒步 |

## Live Permit 必需字段

`contracts.Permit`：

- `device_id` — **臂**设备身份（`ArmState.device_id`），不是相机 SN
- `trajectory_hash` — 可执行 `PlanBundle` / 轨迹摘要
- `config_hash`
- `calibration_hash`
- `scene_version`
- `valid_until_host_monotonic_s` — 由签发时刻 + 新鲜度窗口决定

**对 ArmState 的硬依赖**：

- live 签发/校验要求 `counts_as_live_valid`：`source=real` + `validity=VALID` + 七轴有限 `q_rad`
- `Permit.device_id` 必须等于该 live `ArmState.device_id`
- `OfflineSafetyGate.check_step_evidence` 额外绑定 clock/epoch/新鲜度与 config/calib/scene 哈希
- recorded / mock / fixture **不等于** live；J6/J7 无已审计只读位置 → live VALID 不可达（`hard_block=j6_j7_no_audited_readonly_position_query`）

## 当前 dry-run 签发结论

在 MockArm + shadow PlanBundle + diagnostic context 下：

- `issuance_fields_complete=true`，`gate_accepts_draft=true`，`executable=false`
- `only_hardware_enable_and_policy_remaining=true`（**相对 dry-run MockArm 路径**）
- `live_permit_path_status=software_exhausted_awaiting_live_arm`
- `blocked_by=["j6_j7_readonly","awaiting_live_arm"]`
- `live_permit=null` 恒成立；recorded 臂 ID ≠ live VALID `ArmState`

**仍缺（正式 live / 抓取）** — 软件路径已尽，根因仅 live 臂：

1. 新鲜 **`counts_as_live_valid`** `ArmState`（被 `j6_j7_readonly` 硬阻塞；勿 Rest / enable-motion 补角）
2. live SafetyGate 正式签发权威产物（依赖上项；禁止拷贝 dry-run draft）
3. host/safety：`formal_grasp_entry_allowed` 过后再显式 operator policy attest 抬 `control_ready`（默认关）
4. 操作员开臂 / 执行器使能（仅真实运动前）

机读：`formal_grasp_blocked_by` / `live_permit_path` 见 host checklist。

## Shadow vs live

- **禁止**把 diagnostic / dry-run draft 拷进正式 `StepEvidence.permit` 或交给 live `arm.execute_trajectory`。
- readiness 输出：`permit=null` 恒成立；`permit_eligible=true` 仅表示证据够做资格评估。
- dry-run `only_hardware_enable_and_policy_remaining=true` **不是**正式抓取许可。
- `awaiting_actuator_enable`：物理开臂前保持 true；**不为 dry-run 签发诊断而开臂**。

## CLI

```text
python tools/pre_grasp_readiness.py \
  --request docs/team/B/evidence/field_20261110/first_placement_request_assoc_handclear_overlay_20261110.json \
  --shadow docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json \
  --association-record docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json \
  --output docs/team/B/evidence/field_20261110/pre_grasp_readiness_20261110.json \
  --diagnostic-permit-output docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json

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
