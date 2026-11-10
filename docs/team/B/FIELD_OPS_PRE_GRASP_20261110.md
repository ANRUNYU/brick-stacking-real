# 现场 / 人工确认清单 · Pre-grasp（2026-11-10）

软件门禁工具已可报告缺口；下列项**必须现场摆放或人工确认**，代码不会伪造。

**裁决标注**：操作员授权 AI 代裁决（「你来自己决定不用问我」）。下列 1–5 已由 AI 按授权证据落档；**仍不抬** `control_ready`，不开臂/CAN。

## 必须由用户 / 现场完成

1. **目标关联人工确认** — **已代裁决**  
   目视确认：十字槽上的红块 = `m-first-red-01`，参考 = `table_black_cross_20mm`。  
   已写入 `docs/team/B/evidence/field_20261110/association_confirm_switch_20261110.json` + overlay。  
   仅跑 `--association-confirmed` 影子导出 ≠ 正式关联归档（本轮已有 durable 记录）。

2. **手已撤离 / hand_clear 事实** — **已代裁决（显式，非 scene_consistent）**  
   依据：`arm_idle/no_motion`（本会话臂/CAN 未启用；台面静态对照，无机械手在环）。  
   证据：`docs/team/B/evidence/field_20261110/hand_clear_arm_idle_evidence_20261110.json`。  
   禁止把 `scene_consistent` 拷成 hand_clear。

3. **标定当前绑定批准** — **已代裁决**  
   Live SN 现场录包均为 `CP2L863000KL`。  
   已激活 `CURRENT_BINDING_ACTIVE`，`calibration_hash=a8711b80…`（C35 候选字节身份）。  
   **不是**独立精度批准；候选 `approved/motion_enabled` 仍 false。

4. **时钟误差界与 BundleBinding** — **软件侧已过**  
   S140 preserve-clock 回放 3/3 可构造 `BundleBinding`；消费不再报 `BUNDLE_BINDING_MISSING`。

5. **生产色阈 vs S140 诊断** — **本会话临时采用 S140（非永久改默认）**  
   生产 HSV `S≥160` 对本会话照明漏检；会话 observe profile = `config/vision_profiles/head_slot_contrast_s140.yaml`（diagnostic/session）。  
   生产默认仍为 `head_replacement_candidate.yaml`，除非后续测试与文档支持且判定安全再改。

6. **Yaw / 朝向** — **已代裁决（策略旁路，非 MEASURED）**  
   方块 90° 对称 → yaw **保持 UNKNOWN**；显式 `yaw_policy=symmetric_90_unbounded`（period=π/2）。  
   **未伪造 MEASURED PASS**；Inspection 记 `yaw_rad=None` + `yaw_bound_source=POLICY_UNBOUNDED_NOT_MEASURED`。  
   不再构成 pre_grasp Inspection 阻塞；**无需现场测角**。

7. **post_place（非本轮抓取入口，但勿忽略）**  
   释放、动作完成时间、稳定窗口、support/neighbors：仍待执行侧联调；不是再采静态对照能替代的。

## 软件已覆盖、现场不必重复

- 十字 = 槽位中心（已确认）
- 相机系期望 shadow 采纳
- 红块居中对照（S140）xy/height MEASURED、color MATCH
- readiness / 缺口报告器、association 开关、shadow pipeline（含 binding stamp + M Context）
- ACTIVE calibration hash 身份绑定 + hand_clear(arm_idle) + association durable

## 禁止

- 抬 `control_ready=true`（门禁未全过）
- 发臂/手/CAN
- 用观测点当自身期望、用候选 sha 冒充当前标定、用 scene_consistent 冒充 support/stable/hand_clear
- 伪造 yaw MEASURED PASS
