# M 侧 Permit 签发权威与 shadow vs live（2026-11-10）

本分支统一承载原 V/M 代码。本文冻结 **谁能签发什么**，并说明 readiness 的 diagnostic 进展。

## 权威

| 产物 | 权威签发方 | 可否执行运动 |
| --- | --- | --- |
| `contracts.Permit`（**live**） | **D/M SafetyGate**（执行前；`OfflineSafetyGate.check_step_evidence` 校验） | 是（在 A 独立复核后） |
| `m-diagnostic-permit-eligibility-0.1`（**shadow/diagnostic**） | `pre_grasp_gates` / `tools/pre_grasp_readiness.py` | **否**（`executable=false`） |
| `control_ready` / `motion_enabled` | host/safety 路径（见 [HOST_CONTROL_READY_20261110.md](HOST_CONTROL_READY_20261110.md)） | 本 readiness **永不抬升**；host checklist 亦永不抬升 |

契约依据：`docs/CONTRACTS.md` §4；`docs/THREE_TRACK_GRASP_DEV_PLAN.md` M-10。

## Live Permit 必需字段

`contracts.Permit`：

- `device_id` — **臂**设备身份（`ArmState.device_id`），不是相机 SN
- `trajectory_hash` — 可执行 `PlanBundle` / 轨迹摘要
- `config_hash`
- `calibration_hash`
- `scene_version`
- `valid_until_host_monotonic_s` — 由签发时刻 + 新鲜度窗口决定

`OfflineSafetyGate` 额外要求：标定有效、反馈新鲜、permit 与当前 step context 逐字段匹配、剩余有效期落在 offline freshness 窗口内。

## Inspection / Context（诊断侧已齐的部分）

影子 `SHADOW_INSPECTION_READY` + `Context` 已能证明：

- `target_id` / `scope` / `frame_id` / `calibration_hash` / `profile_hash` / `epoch` / `clock_domain`
- association、hand_clear(arm_idle)、bundle clock、formal verify（confirmed）、yaw 策略旁路

**仍缺（live 签发硬缺口）**：

1. live SafetyGate 在执行时刻签发
2. host/safety 使能路径（`control_ready`）
3. 操作员开臂 / 执行器使能（仅真实运动前）
4. `PlanBundle.trajectory_hash`
5. 新鲜 `ArmState.device_id`

## Shadow vs live

- **禁止**把 diagnostic 对象拷进 `StepEvidence.permit` 或交给 `arm.execute_trajectory`。
- readiness 输出：`permit=null` 恒成立；`permit_eligible=true` 仅表示证据够做资格评估。
- `awaiting_m_permit`：证据未齐时 true；证据齐后 **false**，改为 `awaiting_live_permit_host_enable=true`。
- `awaiting_actuator_enable`：物理开臂前保持 true；**不为宣布视觉就绪而开臂**。

## CLI

```text
python tools/pre_grasp_readiness.py \
  --request docs/team/B/evidence/field_20261110/first_placement_request_assoc_handclear_overlay_20261110.json \
  --shadow docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json \
  --association-record docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json \
  --output docs/team/B/evidence/field_20261110/pre_grasp_readiness_20261110.json \
  --diagnostic-permit-output docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json
```
