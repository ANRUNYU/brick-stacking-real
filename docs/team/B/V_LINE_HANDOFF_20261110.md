# V 线交接 · 2026-11-10

当前交付为开发机软件和录包回放证据。进度依赖按 #16/#8 → #7/#17 → #9/#20 → #10 → #18 → #19 排列。

| 顺序 | 本次交付 | 现场或跨线待验收 |
| --- | --- | --- |
| #16 / #8 | [H0 草案](evidence/first_grasp_h0_draft.json) **V+M 已 ACK 预算**（`control_ready` 仍 false）。Fixture 索引、三帧 C 录包样例、四类状态与契约门面 `vision.service`。 | 时钟误差界与标定 hash 仍缺；C/D 审查字段及样例 |
| #7 / #17 | 两会话联采后 [时钟研究](evidence/field_20261110/clock_error_bound_study_v0.1.json) **≈1.69 ms** 已写入在线观测；短采冒烟 16/16 `timing.validity=VALID`（见 [live smoke](evidence/field_20261110/clock_bound_live_smoke_20261110.json)）。`control_ready` 仍 false。 | M 完成独立对尺；标定 hash 仍缺 |
| #9 / #20 | **exposure→output** p50≈0.69 s / max≈1.33 s；诊断 freshness 门建议 **2.656 s**（max×2）。在线 freshness 在有 bound 时按曝光候选计龄。 | H0 正式冻结 freshness；M 路径模板 #20 |
| #10 | 点语义冻结；十字已确认；期望已 shadow 采纳；红块居中对照完成（S140 会话诊断）；统一影子管线已复检；pre_grasp 门禁 + readiness/association 开关已落地；S140 preserve-clock 可构造 BundleBinding；**AI 代裁决**已激活 C35 `CURRENT_BINDING_ACTIVE`（a8711b80…）、association durable、hand_clear(arm_idle)、M Context 影子接入、`yaw_policy=symmetric_90_unbounded`；**`vision_pre_grasp_ready=true` + `permit_eligible=true`（diagnostic；live permit 仍 null）**；**host gate ladder**：`dry_run_grasp_entry_ready=true`；`formal_grasp_entry_allowed=false`；`control_ready=false`（operator policy attest **默认关**）；dry-run SafetyGate 签发诊断已通；shadow PlanBundle + recorded 臂使 `missing_software=[]`；**live-or-recorded 臂读机读路径**已接通（`arm_feedback.counts_as_live_valid=false`；recorded ≠ live；ArmStateReader 因 J6/J7 仍 INVALID；见 [HOST_CONTROL_READY](HOST_CONTROL_READY_20261110.md)、[UNIFIED_SLOT_PROGRESS](UNIFIED_SLOT_PROGRESS_20261110.md)、[M_PERMIT_AUTHORITY](M_PERMIT_AUTHORITY_20261110.md)）。 | **证据门禁已清**；`dry_run_grasp_entry_ready=true`；`can_enter_formal_grasp=false`。**剩余硬阻塞**：live SafetyGate `Permit` + `counts_as_live_valid`（七轴有限角）；抬 `control_ready` 另需显式 attest；`motion_enabled` 仍默认 false（+ H3 生产 PlanBundle）。**正式抓取：否**；现不必开臂/使能/大幅运动。 |
| #18 / #19 | 提供观测与复检接口供 M 线接入。 | 由 M 按 H5、H6 和 T1–T5 逐级验收 |
| #11 | 三帧既有开发录包已登记 SHA-256 与原始出处。 | 独立布局、物理参考及逐条件报告，首抓后验收 |

## H1 样例与坐标

- [Fixture 索引](../../../tests/fixtures/vision_exchange/FIXTURE_INDEX.json)列出录包、合成状态与复检 golden；并标明仍缺的独立单块/紧贴失败例。
- [三帧 C 实录回放](../../../tests/fixtures/vision_exchange/c_recording_bundles_v0.1.json)源自头相机 CP2L863000KL，原流 1280×800@15，样例图为裁剪。三帧都产生四个单块候选和两个歧义候选。该结果来自同场景开发样本，独立精度仍待验收。
- [合成状态样例](../../../tests/fixtures/vision_exchange/synthetic_status_v0.1.json)覆盖正常、歧义、无效深度和过期。合成 RGB-D 可用 `python -m brick_stacking.app.offline_runner --synthetic` 重建，invalid-depth 由同一帧的深度置为 NaN 生成。
- `rgbd.sample_id` 和 `blocks[].observation_id` 只在当前采集会话内引用图像及检测。持久对象关联由 M 的事务侧维护。
- `b_extensions.top_surface_point_camera_m` 在桌面检测路径表示可见顶面中心，在单组件路径表示表面采样点。用 `top_surface_point_kind` 区分。桌面路径的 `model_center_camera_m` 由顶面沿桌面法向减去半个标称边长得到。实测顶面跨度、标称三轴尺寸和未知方向/协方差分别保留。长度单位 m，角度单位 rad，坐标系由 `frame_id` 标识。
- 录包中的原始 C 时钟桥接结果可供追溯。现场研究接受后，在线路径可填 `timing.exposure_host_stamp_s` 与 `clock_error_bound_s`（见证据 JSON）；无证据时仍为 null/`UNKNOWN`。候选几何有效性独立于 `control_ready`（仍 false）。

开发机回放入口，从仓库根目录运行：

```text
python -m brick_stacking.app.tabletop_runner --config config/vision_profiles/head_replacement_candidate.yaml --recordings tests/fixtures/real/C_20261108_tabletop/camera/frame_000.npz tests/fixtures/real/C_20261108_tabletop/camera/frame_001.npz tests/fixtures/real/C_20261108_tabletop/camera/frame_002.npz
```

契约门面：

```text
from brick_stacking.vision.service import replay, detect_blocks, verify, VisionSession
```

连续录包经最新帧队列回放（主机到达时间重映射，不伪造曝光延迟）：

```text
python -c "from brick_stacking.vision.replay_pipeline import replay_recordings; replay_recordings(['tests/fixtures/real/C_20261108_tabletop/camera/frame_000.npz','tests/fixtures/real/C_20261108_tabletop/camera/frame_001.npz','tests/fixtures/real/C_20261108_tabletop/camera/frame_002.npz'], config_path='config/vision_profiles/head_replacement_candidate.yaml', report_path='docs/team/B/evidence/c_recording_replay_latency_v0.1.json')"
```

## 现场单红块（2026-11-10）

头相机 `CP2L863000KL`，会话内关自动曝光（exposure=100，gain=16，非持久写入）。桌面仅一块疏排红方块时，在线入口发布 12 帧，每帧 1 个 `VALID` 红候选。相机系顶面点相对中位偏差最大约 1.1 mm，这只说明静态重复性，不是基座系 10 mm 验收。`control_ready` 保持 false；`exposure_to_output_s` 与 `clock_error_bound_s` 保持 null。诊断用接收龄期门建议 2.564 s（实测 max×2），写入 H0 草案时标明尚未替代曝光时钟门。证据见 [field_20261110](evidence/field_20261110/single_red_stability.json)。

### 独立尺量（临时十字原点）

桌面固定 20×20 mm 黑十字为临时原点。红块测量点为**顶面中心在桌面的竖直投影**，另测顶面高 50 mm，得十字系 `[0.172, 0.079, 0.050] m`（±2 mm）。十字相对中心立柱：左 191 mm、前/后 592 mm、水平直线 622 mm（直角闭合）。左肩 J1：到立柱水平 165 mm，到十字斜距约 772 mm，桌面以上约 495 mm；拟合后相对十字约右 26 mm、靠机器人 586 mm。J1 是否等于 `L_arm_root` 待 M 确认。完整数值见 [independent_ruler_reference_v0.1.json](evidence/field_20261110/independent_ruler_reference_v0.1.json)。

## 在线诊断入口

机器人主机的视觉环境需要已安装仓库及既有 Orbbec SDK。候选 profile 的 SN、分辨率、HSV 和高度带沿用现有配置。采集端独占相机，检测端只保留一对待处理 RGB-D。以下数值用于诊断试跑，曝光有效期仍由 H0 实测冻结：

```text
python tools/orbbec_camera_probe.py --capture --serial CP2L863000KL --width 640 --height 480 --fps 15 --frames 450 --seconds 40 --max-skew-ms 20 --observe-profile config/vision_profiles/head_replacement_candidate.yaml --max-receive-age-s 3 --reconnects 1 --output artifacts/head_online_v_diagnostic
```

输出包含 `observation_bundles.jsonl`、实际发布帧的 NPZ 和 `camera_report.json`。报告分别统计检测耗时与主机接收到生成输出的 P50/P95/最大值，采样窗口最多 256 条。时钟验收前，曝光到输出为 null。SDK 完整帧超时、处理过期、缓冲覆盖、时间戳逆序和重连通过各自计数或事件保留。已知相机或桌面移动时调用 `LatestFramePipeline.invalidate()` 并用新 epoch 开始。可见平面或静态场景变化会触发重新确认，绝对相机静止性仍需独立参照。

## H4 复检

[Mock 请求与期望响应](../../../tests/fixtures/vision_exchange/verification_v0.1.json)覆盖持握、抓空、撤离后稳定、错色、偏移、遮挡、失效深度、超时、移机和旧帧复用。生产者使用 `verification.visual_transition.verify()`（或 `vision.service.verify`），由调用方把目标关联和图像证据装入 `VisualSample`。post_place 要求颜色相符、平面偏差 ≤15 mm、明确释放证据及独立稳定帧。真机请求还需有效曝光误差界及其证据引用。仅有供料区消失或单帧到位时返回 UNKNOWN。D 的 `PICK`/`PLACE` 回调兼容现有 `VerificationEvidence`，槽位提交仍由 FSM 负责。
