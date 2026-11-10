# Pre-grasp 软件门禁清单（2026-11-10）

目标：进入正式抓取前的软件门禁。本清单与 `tools/pre_grasp_readiness.py` / `src/brick_stacking/planning/pre_grasp_gates.py` 对齐。

**硬约束**：门禁未全过前 `control_ready` 必须保持 `false`；不发运动/CAN；不伪造正式 PASS / permit。

**裁决标注**：操作员授权 AI 代裁决（「你来自己决定不用问我」）。

对照证据（bound overlay）：`docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json`（3/3 MATCH；消费仍 BLOCKED，**仅剩 yaw**）。

| 门禁 | 接口/字段 | 软件现状 | 阻塞？ | 备注 |
| --- | --- | --- | --- | --- |
| association | `target_association_confirmed` + 操作员记录 | durable `association_confirm_switch_20261110.json` → PASS | 已过（代裁决） | reference=`table_black_cross_20mm`；target=`m-first-red-01` |
| hand_clear | handoff `hand_clear: bool` | overlay + `hand_clear_arm_idle_evidence_20261110.json` → PASS | 已过（代裁决） | 依据=`arm_idle/no_motion`；非 scene_consistent |
| support_ok | handoff / post_place | null；Inspection 可保留 None | 否（FAIL 才阻塞） | post_place 更关键 |
| stable | handoff / 稳定窗口 | null；pre_grasp 记缺口 | 否（FAIL 才阻塞） | post_place 必需 |
| neighbors_unchanged | handoff | null | 否 | 显式证据 |
| yaw_bound | `yaw_rad` MEASURED | UNKNOWN（90° 对称） | **是（Inspection）** | **未伪造 PASS**；无有界测量 |
| xy/height | LocalizedReview ErrorBound | 红对照 MEASURED，xy≈6.7–7.2 mm | 对照已过 | 正式 verify 另路 |
| color_match | color_check | S140 诊断 3/3 MATCH | 对照已过 | 会话临时 S140；生产默认未改 |
| reference_id | `table_black_cross_20mm` | 已确认并采纳 | 已过 | |
| expected_pose_adopted | adopted request formal/review | 已采纳相机系期望 | 已过 | formal=`model_center`；review=`visible_top_center` |
| calibration_binding | `calibration_hash` 当前绑定 | `CURRENT_BINDING_ACTIVE` a8711b80… | 已过（代裁决） | hash 身份 only；非精度批准 |
| bundle_binding_clock | BundleBinding + `clock_error_bound_s` + evidence_ref | S140 3/3 binding_present | 已过 | |
| m_context | `Context(target_id, scope, hashes…)` | `--build-m-context` 最小合法 Context | 已过（影子） | 勿伪造 hash |
| formal_verify_path | `visual_transition.verify` | confirmed 帧 PASS；warmup UNKNOWN 跳过 | 已过 | raw 仍 1 PASS/2 UNKNOWN；不放宽 monitor |
| shadow_inspection | `SHADOW_INSPECTION_READY` | 仅评 scene_consistent 帧；仍 BLOCKED（yaw） | **是** | warmup SCENE 跳过，非伪造 |
| permit | permit | 恒 null | 是（策略） | 本工具永不签发 |
| control_ready_policy | control_ready | 恒 false | 是（策略） | 本工具永不抬升 |

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

# 缺口 / readiness（永不 control_ready=true）
python tools/pre_grasp_readiness.py \
  --request docs/team/B/evidence/field_20261110/first_placement_request_assoc_handclear_overlay_20261110.json \
  --shadow docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json \
  --association-record docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json \
  --output docs/team/B/evidence/field_20261110/pre_grasp_readiness_20261110.json

python tools/pre_grasp_readiness.py --gaps-only --shadow … --output …/pre_grasp_gaps_20261110.json
```

## 与 permit / Inspection 接口

- `consume_handoff` → 仅当无 reasons 时构造 `Inspection`；成功状态为 `SHADOW_INSPECTION_READY`，`formal_placement_verdict` 仍为 `UNKNOWN`，`permit=null`。
- `to_shadow_inspection` 要求 association、reference、`visible_top_center`、calibration_hash 与 Context 一致。
- readiness 报告只列缺口；`formal_grasp_entry_allowed` 在本模块恒为 `false`。
