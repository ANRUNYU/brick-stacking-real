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
20. **host/safety checklist**：机读抬起条件 + dry-run/arm-disabled 探测已接通；见 [HOST_CONTROL_READY_20261110.md](HOST_CONTROL_READY_20261110.md) 与 `host_control_readiness_20261110.json`。`only_operator_enable_remaining=false`；**仍不**抬 `control_ready` / 开臂 / CAN。
21. **shadow PlanBundle + recorded 臂 ID（本轮）**：`tools/emit_shadow_plan_and_arm_state.py` 产出 `shadow_plan_bundle_20261110.json`（`trajectory_hash` 由 `arm.adapter.trajectory_hash` 计算）与 `recorded_arm_state_left_p7_20261110.json`（`device_id=can2:61,62,63,64,65,66,67`，`source=recorded`）。host checklist **`missing_software=[]`**；**不是** H3 生产 PlanBundle（#20），**不是** live 臂读。
22. **dry-run SafetyGate 签发诊断（本轮）**：`OfflineSafetyGate.issue_dry_run_diagnostic` 在 MockArm/`hardware_enabled=False` 下走通；消费 shadow PlanBundle 后 `issuance_fields_complete=true`、`gate_accepts_draft=true`、`only_hardware_enable_and_policy_remaining=true`（相对 dry-run）；`executable=false`，`live_permit=null`。见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)。
23. **门控阶梯（本轮）**：区分 `vision_pre_grasp_ready` → `dry_run_grasp_entry_ready` → `formal_grasp_entry_allowed` → `control_ready`。证据满足 dry-run 全链时 **`dry_run_grasp_entry_ready=true`**；`formal_grasp_entry_allowed` 仅在 live Permit + live VALID 臂满足时为 true；`control_ready` 另需显式 operator policy attest（**默认关**，不自动打开）。见 [HOST_CONTROL_READY_20261110.md](HOST_CONTROL_READY_20261110.md)。
24. **live-or-recorded→VALID 机读路径（本轮）**：`arm_state_validity` + `tools/arm_state_live_or_recorded.py`；readiness 区分 `arm_state_device_id`（recorded PASS）与 `live_valid_arm_state`（`counts_as_live_valid`）。Mock/recorded/fixture 已测；**未**做真机大幅运动；Windows 上 `live-readonly` 软失败可跳过。ArmStateReader 因 J6/J7 无已审计只读位置查询，live 样本仍 INVALID。
25b. **J6/J7 只读位置硬阻塞（本轮）**：审计确认无只读位置协议 → 文档化 `j6_j7_no_audited_readonly_position_query` + 拒绝骨架 `v2_wrist_readonly.py`（不 Rest / 不 enable-motion）；`gate_ladder.j6j7_readonly_position_hard_block=true`；**live VALID 不可达**；正式抓取仍否。见 [J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md](J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md)。
25c. **J6/J7 候选穷尽（2026-11-11）**：主机 `motor_v2.py`（SHA `6f45000b…`）+ 全库检索；8 类候选无一 `pending_protocol_audit_eligible`；`ENABLE_PENDING_PROTOCOL_AUDIT` 默认 false 且 payload 空；**Goal 无法仅靠软件完成**，需 Motorevo/LinkerBot 手册或 Flash 索引图（或书面确认无纯查询）。未开臂、未 Rest、未抬 `control_ready`。
25d. **J6/J7 仓库外协议检索否定（2026-11-11）**：WebSearch/WebFetch（Motorevo 官网、`docs.linkerhub.work`、公开 `linkerbot-python-sdk` `motor_v2.py`）+ 本机 Desktop/Downloads/Documents/`E:\OneDrive\Desktop` 只读检索；**无**协议手册 / Flash Theta 索引 / 纯查询字节；`pending_protocol_audit` **未**接入；`goal_complete=false`。见 [J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md](J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md)、`j6j7_external_protocol_search_20261111.json`。
25c. **live Permit 软件路径推到极限（本轮）**：Mock dry-run 签发字段齐 + gate 接受 draft；机读 `live_permit_path.status=software_exhausted_awaiting_live_arm`；`formal_grasp_blocked_by=["j6_j7_readonly","awaiting_live_arm"]`；**仍** `executable=false` / `live_permit=null` / `control_ready=false`。解除需协议审计授权，非 Rest。见 [M_PERMIT_AUTHORITY_20261110.md](M_PERMIT_AUTHORITY_20261110.md)、`formal_grasp_entry_audit_20261110.json`。
25. **diagnostic 对齐 shadow PlanBundle / recorded 臂（本轮）**：`pre_grasp_readiness --plan-bundle/--arm-state` 将 diagnostic 字段标为 `PRESENT_FROM_SHADOW_PLAN_BUNDLE` / `PRESENT_FROM_RECORDED_OR_MOCK_ARM`；**仍** `live_permit=null`、`formal_grasp_entry_allowed=false`、`control_ready=false`。完成审计见 `docs/team/B/evidence/field_20261110/formal_grasp_entry_audit_20261110.json`。

## 物理阻塞

无臂/CAN 执行。本轮**不再**需要用户做标定/association/hand_clear/yaw 确认（对称策略已代裁决）。**仅当要真正动臂时**才需要操作员开臂/使能；软件宣布视觉就绪 / diagnostic 资格本身不要求开臂。

## 仍不抬 control_ready 的原因（真实剩余阻塞）

- live `permit=null`（仅 D/M SafetyGate 可签发 live；本路径只发 diagnostic + dry-run 签发诊断）。
- `formal_grasp_entry_allowed=false`；根因机读 **`formal_grasp_blocked_by=["j6_j7_readonly","awaiting_live_arm"]`**（Permit 软件路径已尽）。
- `control_ready=false`：**reporter 硬持有**（大幅运动安全）；operator policy attest **默认关闭**（开关已实现，未打开；打开也不在本路径抬升）。
- `motion_enabled` 硬持有 false。
- dry-run MockArm 路径：`dry_run_grasp_entry_ready=true`；**不等于**正式抓取入口。
- host checklist 软件两项已关；`live_permit_path=software_exhausted_awaiting_live_arm`；仍差：协议审计后的 live VALID 臂 + live Permit +（抬 control_ready 时）显式 attest +（真运动前）开臂；H3 生产 PlanBundle 仍待 #20。
- post_place 缺动作完成/释放/稳定窗口证据（本轮非抓取入口硬阻塞，但列出）。

## SCENE 说明（已解除会话级误报）

S140 三帧：`required_frames=3` → 帧0/1 为 `WARMING_UP`（consecutive=1/2，`scene_consistent=false`），帧2 `CONFIRMED`。原因是时序确认窗口，**不是** gap/shift 失败；**无需现场重采**。

readiness 现只采纳 `scene_consistent` 帧：warmup 上的 `SCENE_OR_RGBD_NOT_CONFIRMED` 跳过（不伪造 confirm、不降低 `required_frames`）。正式 verify 在 confirmed 帧为 PASS；raw 仍可见 1 PASS / 2 UNKNOWN。

## 能否进入正式抓取

**否**（机读：`gate_ladder.can_enter_formal_grasp=false` / `formal_grasp_entry_allowed=false`）。  
- 视觉侧：`vision_pre_grasp_ready=true` / `evidence_gates_clear=true` / `permit_eligible=true`（diagnostic 已写；**(A)**）。  
- dry-run：`dry_run_grasp_entry_ready=true`（MockArm 全链）。  
- live `permit=null`；recorded 臂 ≠ live VALID；`awaiting_live_permit_host_enable=true`。  
- `control_ready=false`（formal 未过 + attest 默认关）；`motion_enabled=false`；未开臂、未发 CAN。  
- **是否需用户使能**：现在不必开臂/Rest/`--enable-motion`；解除正式抓取需 **协议审计授权**（J6/J7 只读位置）；抬 `control_ready` 另需显式 `--attested`。
