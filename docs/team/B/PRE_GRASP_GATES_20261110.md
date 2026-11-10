# Pre-grasp 软件门禁清单（2026-11-10）

目标：进入正式抓取前的软件门禁。本清单与 `tools/pre_grasp_readiness.py` / `src/brick_stacking/planning/pre_grasp_gates.py` 对齐。

**硬约束**：门禁未全过前 `control_ready` 必须保持 `false`；不发运动/CAN；不伪造正式 PASS / permit。

**裁决标注**：操作员授权 AI 代裁决（「你来自己决定不用问我」）。

对照证据（bound overlay）：`docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json`（3/3 MATCH；confirmed 帧 `SHADOW_INSPECTION_READY`；`evidence_gates_clear=true`；`vision_pre_grasp_ready=true`）。

| 门禁 | 接口/字段 | 软件现状 | 阻塞？ | 备注 |
| --- | --- | --- | --- | --- |
| association | `target_association_confirmed` + 操作员记录 | durable `association_confirm_switch_20261110.json` → PASS | 已过（代裁决） | reference=`table_black_cross_20mm`；target=`m-first-red-01` |
| hand_clear | handoff `hand_clear: bool` | overlay + `hand_clear_arm_idle_evidence_20261110.json` → PASS | 已过（代裁决） | 依据=`arm_idle/no_motion`；非 scene_consistent |
| support_ok | handoff / post_place | null；Inspection 可保留 None | 否（FAIL 才阻塞） | post_place 更关键 |
| stable | handoff / 稳定窗口 | null；pre_grasp 记缺口 | 否（FAIL 才阻塞） | post_place 必需 |
| neighbors_unchanged | handoff | null | 否 | 显式证据 |
| yaw_bound | `yaw_rad` + `yaw_policy` | UNKNOWN + `symmetric_90_unbounded` → 门禁 PASS | **否（已旁路）** | **未伪造 MEASURED**；Inspection.yaw_rad=None |
| xy/height | LocalizedReview ErrorBound | 红对照 MEASURED，xy≈6.7–7.2 mm | 对照已过 | 正式 verify 另路 |
| color_match | color_check | S140 诊断 3/3 MATCH | 对照已过 | 会话临时 S140；生产默认未改 |
| reference_id | `table_black_cross_20mm` | 已确认并采纳 | 已过 | |
| expected_pose_adopted | adopted request formal/review | 已采纳相机系期望 | 已过 | formal=`model_center`；review=`visible_top_center` |
| calibration_binding | `calibration_hash` 当前绑定 | `CURRENT_BINDING_ACTIVE` a8711b80… | 已过（代裁决） | hash 身份 only；非精度批准 |
| bundle_binding_clock | BundleBinding + `clock_error_bound_s` + evidence_ref | S140 3/3 binding_present | 已过 | |
| m_context | `Context(target_id, scope, hashes…)` | `--build-m-context` 最小合法 Context | 已过（影子） | 勿伪造 hash |
| formal_verify_path | `visual_transition.verify` | confirmed 帧 PASS；warmup UNKNOWN 跳过 | 已过 | raw 仍 1 PASS/2 UNKNOWN；不放宽 monitor |
| shadow_inspection | `SHADOW_INSPECTION_READY` | confirmed 帧 READY（1/1 eligible） | 已过 | warmup SCENE 跳过，非伪造 |
| permit | permit (live) | 恒 null；证据齐时 `permit_eligible=true` | 是（策略） | live 仅 D/M SafetyGate；本工具可发 **diagnostic** 资格记录 |
| control_ready_policy | control_ready | 恒 false | 是（策略） | 本工具永不抬升；host/safety |

权威细节见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。

## 布尔语义（A/B 区分）

| 字段 | 当前 | 含义 |
| --- | --- | --- |
| `evidence_gates_clear` | **true** | 证据类阻塞门禁全 PASS（不含 permit/control_ready 策略门） |
| `vision_pre_grasp_ready` | **true** | **(A)** 视觉侧 pre_grasp 就绪；**不等于**正式抓取许可 |
| `permit_eligible` | **true** | 证据够评估 live 签发资格；**不是** `contracts.Permit` |
| `diagnostic_permit` | 已写 | `m-diagnostic-permit-eligibility-0.1`；`executable=false`；`live_permit=null` |
| `formal_grasp_entry_allowed` | **false** | 正式进入抓取（含运动路径）— 本模块恒 false |
| `control_ready` | **false** | 控制就绪 — 永不由 readiness/V 抬升 |
| `motion_enabled` | **false** | 运动使能 — 永不由本路径打开 |
| `permit` | **null** | **live** Permit — 仅 D/M SafetyGate 可签发；禁止把 diagnostic 当 live |
| `awaiting_m_permit` | **false** | 证据已齐 → 不再笼统「等 M permit」 |
| `awaiting_live_permit_host_enable` | **true** | 仍差 host/safety 使能 + live SafetyGate 签发 |
| `awaiting_actuator_enable` | **true** | 仍等执行器/开臂使能（物理动作前才需要） |
| `permit_hold_reason` | `eligible_awaiting_host_enable_and_live_safety_gate` | 精确持有原因 |

**裁决**：**(A)** 视觉就绪 + **diagnostic 资格**已签发；**不允许**伪造 live Permit，**不允许**抬 `control_ready` / 发 CAN。正式抓取仍否。

签发点摘要：

- V / `verify_export` / `consume_handoff` / `placement_bridge`：恒 `control_ready=false`、`permit=null`、`motion_enabled=false`；成功止于 `SHADOW_INSPECTION_READY`。
- `pre_grasp_gates`：证据齐时可置 `permit_eligible` + diagnostic；`formal_grasp_entry_allowed` 恒 false；live `permit` 恒 null。
- `OfflineSafetyGate`：无匹配未过期 **live** `Permit` 则拒步；diagnostic 不可替代。
- 标定绑定 / association 开关：显式拒绝抬 `control_ready` / `motion_enabled`。

## 工具

```text
# 关联确认开关（不改 adopted；可写 overlay）
python tools/association_confirm_switch.py \
  --operator "<name>" \
  --evidence-ref docs/team/B/evidence/field_20261110/slot_contrast_20261110_214801.zip \
  --output docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json

# 标定当前绑定（ACTIVE；不抬 control_ready）
python tools/approve_calibration_current_binding.py \
  --live-serial CP2L863000KL --attest-live-serial --attest-current-binding \
  --activate --write --force --update-adopted-request

# 影子复检（binding + M Context）
python tools/slot_shadow_pipeline.py <bundles.jsonl> \
  --association-confirmed \
  --calibration-binding config/observed/calibration_current_binding_c35_20261110.json \
  --build-m-context \
  --request docs/team/B/evidence/field_20261110/first_placement_request_assoc_handclear_overlay_20261110.json \
  --output docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_….json

# 缺口 / readiness（永不 control_ready=true；可报 vision_pre_grasp_ready + permit_eligible）
python tools/pre_grasp_readiness.py \
  --request docs/team/B/evidence/field_20261110/first_placement_request_assoc_handclear_overlay_20261110.json \
  --shadow docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json \
  --association-record docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json \
  --output docs/team/B/evidence/field_20261110/pre_grasp_readiness_20261110.json \
  --diagnostic-permit-output docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json

python tools/pre_grasp_readiness.py --gaps-only --shadow … --output …/pre_grasp_gaps_20261110.json
```

## 与 permit / Inspection 接口

- `consume_handoff` → 仅当无 reasons 时构造 `Inspection`；成功状态为 `SHADOW_INSPECTION_READY`，`formal_placement_verdict` 仍为 `UNKNOWN`，`permit=null`。
- `to_shadow_inspection` 要求 association、reference、`visible_top_center`、calibration_hash 与 Context 一致。
- readiness：`vision_pre_grasp_ready` ≡ `evidence_gates_clear`；证据齐 → `permit_eligible` + diagnostic；live `permit` 恒 null；`formal_grasp_entry_allowed` 恒 false；不开臂。
