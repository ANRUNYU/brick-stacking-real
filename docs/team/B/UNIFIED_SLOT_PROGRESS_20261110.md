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
9. 影子复检：`slot_contrast_red_s140_shadow*_20261110_214801.json`；`--association-confirmed` 下正式 verify 1 PASS / 2 UNKNOWN（scene 未齐）；消费仍 BLOCKED，但已越过 binding/clock。
10. **Pre-grasp 门禁清单与 readiness**：`docs/team/B/PRE_GRASP_GATES_20261110.md`、`FIELD_OPS_PRE_GRASP_20261110.md`；`src/brick_stacking/planning/pre_grasp_gates.py`；CLI `tools/pre_grasp_readiness.py`、`tools/association_confirm_switch.py`。报告缺口，**不**抬 `control_ready`、**不**发 permit/运动。
11. **Clock / BundleBinding**：现场 `slot_contrast_20261110_214801` 的 `clock_error_bound=null`（observe 相对路径找不到 accepted study）；S140 单帧 `service.replay` 又不写 `output_monotonic_s`。已修：study 相对 cwd/仓库根解析；`replay_recordings` 在 `process_monotonic` 录包上保留 host 时钟并注入 study；`attach_accepted_timing_bound` 可补齐已有 live 包。重导出 S140 jsonl 后 **3/3 可构造 BundleBinding**，消费不再报 `BUNDLE_BINDING_MISSING` / `TIMING_UNKNOWN_STALE_OR_FUTURE`。剩余：`CALIBRATION_BINDING_MISSING`、`M_CONTEXT_MISSING`、`HAND_CLEAR_EVIDENCE_MISSING`、`ERROR_BOUND_UNKNOWN:yaw_rad`（前两帧另有 `SCENE_OR_RGBD_NOT_CONFIRMED`）。

## 物理阻塞

无臂/CAN 执行。下一步：calibration 当前绑定批准，以及 association/hand_clear/yaw/M context（见 FIELD_OPS）。可选：用已合入的 observe 再短采一包，使 NPZ metadata 自带 clock bound（当前离线 preserve-clock 回放已足够推进消费诊断）。

## 仍不抬 control_ready 的原因

- `calibration_hash` 未做当前绑定批准（C35 仍为候选）。
- M context / hand_clear / yaw 误差界等消费门禁仍缺（clock/binding 已不再阻塞）。
- post_place 缺动作完成/释放/稳定窗口证据。
- association durable 记录、permit 策略性保持 null。
