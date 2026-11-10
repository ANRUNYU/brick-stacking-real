# 现场 / 人工确认清单 · Pre-grasp（2026-11-10）

软件门禁工具已可报告缺口；下列项**必须现场摆放或人工确认**，代码不会伪造。

## 必须由用户 / 现场完成

1. **目标关联人工确认**  
   目视确认：十字槽上的红块 = `m-first-red-01`，参考 = `table_black_cross_20mm`。  
   然后运行 `tools/association_confirm_switch.py` 写入 durable 记录（见 PRE_GRASP_GATES）。  
   仅跑 `--association-confirmed` 影子导出 ≠ 正式关联归档。

2. **手已撤离 / hand_clear 事实**  
   抓取入口消费要求显式 `hand_clear: true|false`。当前对照帧为静态摆放，**没有**机械手在场证据链；需现场声明并在证据里写入，或由执行侧在动作后提供。禁止把 `scene_consistent` 拷成 hand_clear。

3. **标定当前绑定批准**（并行智能体）  
   批准非 C35「仅拟合」候选的 **当前** `calibration_hash`，写入请求/观测。未批准前正式 verify / Inspection 保持阻塞。

4. **时钟误差界与 BundleBinding**（并行智能体）  
   对照录包需完整 `clock_error_bound_s` + `error_bound_evidence_ref` + host_boot_epoch，才能构造 `BundleBinding`。缺则 consumer `BUNDLE_BINDING_MISSING`。

5. **生产色阈 vs S140 诊断**  
   生产 HSV `S≥160` 对当前红块 0 VALID；现场要么接受会话诊断 profile `head_slot_contrast_s140.yaml` 并记录，要么调整照明/色阈后重采。未决策前不要当生产 PASS。

6. **Yaw / 朝向**（若要过 Inspection）  
   方块 90° 对称导致 yaw UNKNOWN。若消费硬门需要 MEASURED yaw，需人工确认朝向策略或提供有界测量。

7. **post_place（非本轮抓取入口，但勿忽略）**  
   释放、动作完成时间、稳定窗口、support/neighbors：仍待执行侧联调；不是再采静态对照能替代的。

## 软件已覆盖、现场不必重复

- 十字 = 槽位中心（已确认）
- 相机系期望 shadow 采纳
- 红块居中对照（S140）xy/height MEASURED、color MATCH
- readiness / 缺口报告器、association 开关、shadow pipeline

## 禁止

- 抬 `control_ready=true`
- 发臂/手/CAN
- 用观测点当自身期望、用候选 sha 冒充当前标定、用 scene_consistent 冒充 support/stable/hand_clear
