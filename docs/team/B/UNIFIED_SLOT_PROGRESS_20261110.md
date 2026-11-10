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

## 物理阻塞（仅此）

在十字上**居中放置一块红积木**后继续对照采与关联影子复检。不执行臂/CAN。

## 仍不抬 control_ready 的原因

- `calibration_hash` 未做当前绑定批准（C35 仍为候选）。
- 目标关联未确认。
- post_place 缺动作完成/释放/稳定窗口证据。
