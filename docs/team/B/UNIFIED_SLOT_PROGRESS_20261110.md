# 统一推进 · 槽位期望与影子复检（不分 V/M 线）

日期：2026-11-10。本分支同时承载原 V 观测与 M 消费代码；`control_ready=false`。

**裁决标注**：操作员授权 AI 代裁决（「你来自己决定不用问我」）。本轮未再向用户确认。

## 已完成

1. 操作员确认黑十字 = 槽位中心。
2. 清场固定曝光参考采集 + 确认标注。
3. 相机系期望草案并 **shadow 采纳**：`config/planning/first_placement_review_request.adopted.json`
4. 合入 `placement_bridge` / `verify_handoff_consumer` 等消费层。
5. `tools/slot_shadow_pipeline.py`：导出 + 消费诊断一条龙（现支持 `--calibration-binding` / `--build-m-context`）。
6. 现场对照采（空桌）：`slot_contrast_20261110_214216*` → 0 VALID 块，正式 verify 因关联未确认保持 UNKNOWN；消费 BLOCKED。
7. 历史单红 + 采纳期望：LocalizedReview xy/height 已 MEASURED；因 `association=false` 正式仍 UNKNOWN（`camera_or_table_reference_unconfirmed`）。
8. 红块居中对照：原始 `slot_contrast_20261110_214801` 生产 HSV(S≥160) 0 VALID；**本会话临时诊断** profile [`head_slot_contrast_s140.yaml`](../../config/vision_profiles/head_slot_contrast_s140.yaml) 离线回放 3/3 VALID red，`color_check=MATCH`，top xy≈6.7–7.2 mm / |h|≲1 mm。**未永久改写生产默认** `head_replacement_candidate.yaml`。
9. 影子复检：`slot_contrast_red_s140_shadow*_20261110_214801.json`；`--association-confirmed` 下正式 verify 1 PASS / 2 UNKNOWN（scene 未齐）。
10. **Pre-grasp 门禁清单与 readiness**：`docs/team/B/PRE_GRASP_GATES_20261110.md`、`FIELD_OPS_PRE_GRASP_20261110.md`；`src/brick_stacking/planning/pre_grasp_gates.py`；CLI `tools/pre_grasp_readiness.py`、`tools/association_confirm_switch.py`。报告缺口，**不**抬 `control_ready`、**不**发 permit/运动。
11. **Clock / BundleBinding**：S140 preserve-clock 回放后 **3/3 可构造 BundleBinding**。
12. **Calibration 当前绑定（AI 代裁决）**：Live SN 现场录包均为 `CP2L863000KL` → 已激活 `CURRENT_BINDING_ACTIVE`，`calibration_hash=a8711b804660ff8888e85e07b836bb336832ab04a31bf5337e7b64157a003461`（见 `config/observed/calibration_current_binding_c35_20261110.json`）。**仅 hash 身份绑定，非精度批准**；`control_ready` 仍 false。
13. **Association durable（AI 代裁决）**：`association_confirm_switch_20261110.json`；reference=`table_black_cross_20mm`，target=`m-first-red-01`。
14. **hand_clear 显式证据（AI 代裁决）**：`hand_clear_arm_idle_evidence_20261110.json`，依据=`arm_idle/no_motion`（臂/CAN 未启用、台面静态对照）；**禁止**用 `scene_consistent` 冒充。
15. **M Context 影子接入**：overlay + ACTIVE binding 下 `--build-m-context`；消费不再报 `CALIBRATION_BINDING_MISSING` / `M_CONTEXT_MISSING` / `HAND_CLEAR_EVIDENCE_MISSING`。
16. 最新 bound 影子：`slot_contrast_red_s140_shadow_assoc_bound_20261110_214801.json`；readiness：`pre_grasp_readiness_20261110.json` / `pre_grasp_gaps_20261110.json`。
17. **yaw_policy=symmetric_90_unbounded**：方块 90° 对称保持 `yaw_rad=UNKNOWN`（**未伪造 MEASURED**）；consumer 在显式策略下构造 `Inspection.yaw_rad=None`，不再报 `ERROR_BOUND_UNKNOWN:yaw_rad`。confirmed 帧 → `SHADOW_INSPECTION_READY`；`evidence_gates_clear=true`。
18. **vision_pre_grasp_ready 接通（A）**：证据门禁已清时宣布「视觉侧 pre_grasp 就绪」；**不**抬 `control_ready`、**不**开臂/CAN。`formal_grasp_entry_allowed` 恒 false。
19. **diagnostic permit 资格（本轮）**：证据齐 → `permit_eligible=true` + `m-diagnostic-permit-eligibility-0.1`（`executable=false`，`live_permit=null`）。权威说明见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。`awaiting_m_permit=false` → `awaiting_live_permit_host_enable=true`（精确状态）。**未伪造** live `contracts.Permit`。

## 物理阻塞

无臂/CAN 执行。本轮**不再**需要用户做标定/association/hand_clear/yaw 确认（对称策略已代裁决）。**仅当要真正动臂时**才需要操作员开臂/使能；软件宣布视觉就绪 / diagnostic 资格本身不要求开臂。

## 仍不抬 control_ready 的原因（真实剩余阻塞）

- live `permit=null`（仅 D/M SafetyGate 可签发；本路径只发 diagnostic 资格）。
- `control_ready` / `motion_enabled` 策略性保持 false（host/safety；本 readiness 永不抬升）。
- `formal_grasp_entry_allowed=false`（设计硬持有；视觉就绪 ≠ 正式抓取入口）。
- 仍差：host enable + PlanBundle `trajectory_hash` + 新鲜臂 `device_id` + 开臂（物理动作前）。
- post_place 缺动作完成/释放/稳定窗口证据（本轮非抓取入口硬阻塞，但列出）。

## SCENE 说明（已解除会话级误报）

S140 三帧：`required_frames=3` → 帧0/1 为 `WARMING_UP`（consecutive=1/2，`scene_consistent=false`），帧2 `CONFIRMED`。原因是时序确认窗口，**不是** gap/shift 失败；**无需现场重采**。

readiness 现只采纳 `scene_consistent` 帧：warmup 上的 `SCENE_OR_RGBD_NOT_CONFIRMED` 跳过（不伪造 confirm、不降低 `required_frames`）。正式 verify 在 confirmed 帧为 PASS；raw 仍可见 1 PASS / 2 UNKNOWN。

## 能否进入正式抓取

**否。**  
- 视觉侧：`vision_pre_grasp_ready=true` / `evidence_gates_clear=true` / `permit_eligible=true`（diagnostic 已写；**(A)**）。  
- live `permit=null`；`awaiting_m_permit=false`，`awaiting_live_permit_host_enable=true`，`awaiting_actuator_enable=true`。  
- 正式抓取入口：仍被 live permit / `control_ready` / `motion_enabled` / `formal_grasp_entry_allowed` 挡住；未开臂、未发 CAN。  
- **是否需用户开臂**：现在不必；仅 host/safety 准备真运动前才需要。
