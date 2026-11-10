# 统一推进 · 槽位期望与影子复检（不分 V/M 线）

日期：2026-11-10。本分支同时承载原 V 观测与 M 消费代码；`control_ready=false`。

## 已完成

1. 操作员确认黑十字 = 槽位中心。
2. 清场固定曝光参考采集 + 确认标注。
3. 相机系期望草案并 **shadow 采纳**：`config/planning/first_placement_review_request.adopted.json`
4. 合入 `placement_bridge` / `verify_handoff_consumer` 等消费层。
5. `tools/slot_shadow_pipeline.py`：导出 + 消费诊断一条龙。
6. 现场对照采（空桌）：`slot_contrast_20261110_214216*` → 0 VALID 块，正式 verify 因关联未确认保持 UNKNOWN；消费 BLOCKED。
7. 历史单红 + 采纳期望：LocalizedReview xy/height 已 MEASURED；因 `association=false` 正式仍 UNKNOWN（`camera_or_table_reference_unconfirmed`）。
8. 红块居中对照：原始 `slot_contrast_20261110_214801` 生产 HSV(S≥160) 0 VALID；会话诊断 profile [`head_slot_contrast_s140.yaml`](../../config/vision_profiles/head_slot_contrast_s140.yaml) 离线回放 3/3 VALID red，`color_check=MATCH`，top xy≈6.7–7.2 mm / |h|≲1 mm。
9. 影子复检：`slot_contrast_red_s140_shadow*_20261110_214801.json`；正式 verdict 仍 UNKNOWN（calibration 未绑定）；消费 BLOCKED（缺 binding/clock evidence、M context、hand_clear 等）。`audit_bundle(binding=None)` 不再抛异常。
10. **Pre-grasp 门禁清单与 readiness**：`docs/team/B/PRE_GRASP_GATES_20261110.md`、`FIELD_OPS_PRE_GRASP_20261110.md`；`src/brick_stacking/planning/pre_grasp_gates.py`；CLI `tools/pre_grasp_readiness.py`、`tools/association_confirm_switch.py`。报告缺口，**不**抬 `control_ready`、**不**发 permit/运动。

## 物理阻塞

无臂/CAN 执行。下一步仍依赖 calibration 当前绑定批准与 clock/BundleBinding 证据链（并行智能体），以及现场 association/hand_clear 等人工项（见 FIELD_OPS）。

## 仍不抬 control_ready 的原因

- `calibration_hash` 未做当前绑定批准（C35 仍为候选）。
- 录包 timing/`error_bound_evidence_ref` 不完整 → BundleBinding 无法构造。
- post_place 缺动作完成/释放/稳定窗口证据。
- association durable 记录、hand_clear、yaw MEASURED、M Context 未齐；permit 策略性保持 null。
