# Host / Safety · `control_ready` / `motion_enabled` 抬起条件（2026-11-10）

本文件对照代码冻结 **host/safety** 使能条件，并给出机读 checklist。  
**硬约束**：本路径**永不**把 `control_ready` / `motion_enabled` 置 true，不开臂、不发 CAN。

相关实现：

- `src/brick_stacking/execution/host_control_readiness.py`
- `tools/host_control_readiness.py`
- `src/brick_stacking/planning/shadow_plan_bundle.py` + `tools/emit_shadow_plan_and_arm_state.py`
- `src/brick_stacking/arm/device_binding.py` + `config/observed/arm_device_binding_left_p7_20261110.json`
- 证据：`docs/team/B/evidence/field_20261110/host_control_readiness_20261110.json`
- 影子计划：`shadow_plan_bundle_20261110.json`；录制臂状态：`recorded_arm_state_left_p7_20261110.json`

M 侧 diagnostic permit 权威见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。

## 1. 代码中的抬起条件（查清结果）

### 1.1 `control_ready`

| 条件 | 代码依据 | 当前 |
| --- | --- | --- |
| 上游视觉证据门禁清 | `vision_pre_grasp_ready` / `evidence_gates_clear`（pre_grasp） | **PASS** |
| live `contracts.Permit` | `OfflineSafetyGate.check_step_evidence` 要求非空 permit 且字段匹配 | **MISSING** |
| `PlanBundle.trajectory_hash` | Permit / MockArm 执行上下文 | **PASS**（shadow plan；非 H3 生产包） |
| 新鲜 `ArmState.device_id` | 与 permit.device_id 匹配；相机 SN ≠ 臂 ID | **PASS**（`source=recorded`；非 live 读） |
| offline dry_run 配置 | `config_loader` + `OfflineSafetyGate.check` 仅接受 `dry_run=true` / `environment=offline` | 路径可探测 |
| 执行器拒绝真机适配 | `OfflineExecutionManager`：`backend!=mock` 或 `hardware_enabled!=False` → SAFE_HALT | 恒拒绝真机 |
| 契约类型 | `ObservationBundle.control_ready: Literal[False]` | 视觉包不可为 true |
| **host 策略决策抬升** | 本仓库**无**生产路径把 `control_ready` 写成 true | **POLICY_HOLD**（本 checklist 永不抬） |

### 1.2 `motion_enabled`

| 条件 | 代码依据 | 当前 |
| --- | --- | --- |
| 规划/候选输出 | 各 planning 模块输出恒 `motion_enabled=false` | 恒 false |
| host_monitor 进程旗标 | `main` 上 `tools/host_monitor`：`--enable-motion` → `motion_process_enabled` | 本分支无 host_monitor 源码；默认视为未开 |
| 控制会话 | `confirm=READY` 开会话 | 未开 |
| 关节使能 | `confirm=ENABLE` → `MOVE` → `RELEASE` | 未使能 |
| 轨迹执行链 | 另需 live Permit +（未来）host 抬 `control_ready` | 未满足 |

> 说明：`host_monitor` 源码在 **main**（本 `codex/v-vision-20261110` tip 未携带 `.py`）；checklist 仍记录其抬起阶梯，缺快照时标 `MISSING`。

### 1.3 Dry-run / arm-disabled 入口（已接通）

| 入口 | 作用 | 是否动臂 |
| --- | --- | --- |
| `probe_dry_run_arm_disabled()` / CLI `--probe-dry-run-arm-disabled` | 加载 `config/offline_task.yaml`，实例化 `MockArm`（`hardware_enabled=False`）+ `OfflineSafetyGate`；验证无 permit 时 step 被拒 | **否** |
| `OfflineExecutionManager` | 仅 mock 事务环；拒硬件适配器 | **否** |
| `tools/c_a_mock_replay.py` | 合成轨迹 + MockArm 合同回放 | **否** |

### 1.4 Shadow PlanBundle / 臂 ID 绑定（本轮软件缺口关闭）

| 产物 | 权威来源 | 说明 |
| --- | --- | --- |
| `trajectory_hash` | `arm.adapter.trajectory_hash(validate_trajectory(...))` | 对 offline shadow 路点做 sha256；**不手写 hash** |
| shadow PlanBundle | `m-shadow-plan-bundle-0.1` | `executable=false`；`h3_production_plan=false`；绑定 shadow Inspection 的 calib/config/scene |
| 臂 `device_id` | `can2:61,62,63,64,65,66,67` | 对齐 `ArmStateReader.ENDPOINTS['left']` + `hardware_20261107.json` |
| recorded ArmState | `source=recorded` | host checklist 接受；**不是** live CAN 读；live Permit 仍要新鲜反馈 |

> 这不是 #20 H3 侧向接近生产 PlanBundle；正式抓取仍要 live Permit + host 策略抬升 +（真运动前）开臂。

## 2. 对照当前证据的硬缺口

输入：`pre_grasp_gaps_20261110.json` + shadow plan + recorded arm state  
（`vision_pre_grasp_ready=true`，`permit_eligible=true`）。

| 缺口 | 类别 | 仅差操作员？ | host checklist |
| --- | --- | --- | --- |
| live `Permit` | live_permit | 否（需 SafetyGate 签发） | **MISSING** |
| `PlanBundle.trajectory_hash` | software | 否 | **PASS**（shadow） |
| `ArmState.device_id` | software | 否（recorded 已接；live 新鲜读仍缺） | **PASS**（recorded） |
| host 策略抬 `control_ready` | host_policy | 否（本 release 无抬升路径） | **POLICY_HOLD** |
| host_monitor `--enable-motion` + READY + ENABLE | actuator_operator | 仅在真机单关节调试时 | **MISSING** |

机读结论字段：

- `missing_software` = **[]**
- `only_operator_enable_remaining` = **false**（不只差操作员使能）
- `needs_operator_physical_enable_now` = **false**
- `needs_operator_physical_enable_before_real_motion` = **true**
- `formal_grasp_ready` = **false**

## 3. CLI

```text
python tools/emit_shadow_plan_and_arm_state.py \
  --diagnostic-permit docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json \
  --shadow docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json \
  --plan-bundle-output docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json \
  --arm-state-output docs/team/B/evidence/field_20261110/recorded_arm_state_left_p7_20261110.json

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
| 软件两项缺口？ | **已关**（shadow `trajectory_hash` + recorded 臂 `device_id`） |
| 剩余硬阻塞 | live Permit；host 策略抬 `control_ready`；`motion_enabled` 使能链；H3 生产 PlanBundle（#20）；live 新鲜臂读 |
| 现在要用户物理开臂？ | **否**（软件宣布 checklist / dry-run probe 不要求开臂） |
| 真机运动前要开臂？ | **是**（host_monitor ENABLE 或等价执行器使能） |
