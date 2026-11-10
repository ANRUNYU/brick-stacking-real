# Pre-grasp 软件门禁清单（2026-11-10）

目标：进入正式抓取前的软件门禁。本清单与 `tools/pre_grasp_readiness.py` / `src/brick_stacking/planning/pre_grasp_gates.py` 对齐。

**硬约束**：门禁未全过前 `control_ready` 必须保持 `false`；不发运动/CAN；不伪造正式 PASS / permit。

对照证据基线：红块 S140 影子 `docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_20261110_214801.json`（3/3 MATCH，xy≈7 mm；正式 UNKNOWN；消费 BLOCKED）。

| 门禁 | 接口/字段 | 软件现状 | 阻塞？ | 备注 |
| --- | --- | --- | --- | --- |
| association | `target_association_confirmed` + 操作员记录 | 脚本开关已落地；adopted 仍 false；assoc 影子可 CLI 置 true，但缺 durable operator record → readiness=UNKNOWN | 是 | 单 VALID 候选 ≠ 关联；见 FIELD_OPS |
| hand_clear | handoff `hand_clear: bool` | 现 null；consumer 缺则 `HAND_CLEAR_EVIDENCE_MISSING` | 是 | 不可用 `scene_consistent` 冒充 |
| support_ok | handoff / post_place | null；Inspection 可保留 None | 否（FAIL 才阻塞） | post_place 更关键 |
| stable | handoff / 稳定窗口 | null；pre_grasp 记缺口 | 否（FAIL 才阻塞） | post_place 必需 |
| neighbors_unchanged | handoff | null | 否 | 显式证据 |
| yaw_bound | `yaw_rad` MEASURED | UNKNOWN（90° 对称） | 是（Inspection） | 需朝向策略或人工确认 |
| xy/height | LocalizedReview ErrorBound | 红对照 MEASURED，xy≈6.7–7.2 mm | 对照已过 | 正式 verify 另路 |
| color_match | color_check | S140 诊断 3/3 MATCH | 对照已过 | 生产 HSV S≥160 仍 0 VALID |
| reference_id | `table_black_cross_20mm` | 已确认并采纳 | 已过 | |
| expected_pose_adopted | adopted request formal/review | 已采纳相机系期望 | 已过 | formal=`model_center`；review=`visible_top_center` |
| calibration_binding | `calibration_hash` 当前绑定 | null；C35 仅候选 sha | **是** | **依赖并行 calibration 工作** |
| bundle_binding_clock | BundleBinding + `clock_error_bound_s` + evidence_ref | 对照包 timing bound/ref 空 → `BUNDLE_BINDING_MISSING` | **是** | **依赖并行 clock/BundleBinding** |
| m_context | `Context(target_id, scope, hashes…)` | shadow pipeline `context=None` → `M_CONTEXT_MISSING` | 是 | 软件可补 Context；勿伪造 hash |
| formal_verify_path | `visual_transition.verify` | 正式仍 UNKNOWN（缺 association/calibration/clock 等） | 是 | 位置 PASS ≠ 抓取许可 |
| shadow_inspection | `SHADOW_INSPECTION_READY` | 现全部 BLOCKED | 是 | 见 consumer reasons |
| permit | permit | 恒 null | 是（策略） | 本工具永不签发 |
| control_ready_policy | control_ready | 恒 false | 是（策略） | 本工具永不抬升 |

## 工具

```text
# 关联确认开关（不改 adopted；可写 overlay）
python tools/association_confirm_switch.py \
  --operator "<name>" \
  --evidence-ref docs/team/B/evidence/field_20261110/slot_contrast_20261110_214801.zip \
  --output docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json

# 影子复检（已有）
python tools/slot_shadow_pipeline.py <bundles.jsonl> \
  --association-confirmed \
  --output docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_….json

# 缺口 / readiness（永不 control_ready=true）
python tools/pre_grasp_readiness.py \
  --shadow docs/team/B/evidence/field_20261110/slot_contrast_red_s140_shadow_assoc_20261110_214801.json \
  --association-record docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json \
  --output docs/team/B/evidence/field_20261110/pre_grasp_readiness_20261110.json

python tools/pre_grasp_readiness.py --gaps-only --shadow … --output …/pre_grasp_gaps_20261110.json
```

## 与 permit / Inspection 接口

- `consume_handoff` → 仅当无 reasons 时构造 `Inspection`；成功状态为 `SHADOW_INSPECTION_READY`，`formal_placement_verdict` 仍为 `UNKNOWN`，`permit=null`。
- `to_shadow_inspection` 要求 association、reference、`visible_top_center`、calibration_hash 与 Context 一致。
- readiness 报告只列缺口；`formal_grasp_entry_allowed` 在本模块恒为 `false`。
