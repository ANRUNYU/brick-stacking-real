# V 线交接 · 2026-11-10

当前交付为开发机软件和录包回放证据。进度依赖按 #16/#8 → #7/#17 → #9/#20 → #10 → #18 → #19 排列。

| 顺序 | 本次交付 | 现场或跨线待验收 |
| --- | --- | --- |
| #16 / #8 | [H0 草案](evidence/first_grasp_h0_draft.json)绑定计划内容哈希、视觉候选 profile 和 golden 路径。发布现有三帧 C 录包样例和四类状态。 | V/M 书面 ACK，C/D 审查字段及样例 |
| #7 / #17 | 读取 C 录包中的设备、SDK system/global、主机接收时间、时钟域、session 和 RGB-D 配对差。保留原始桥接证据。 | 统一曝光参考、boot/进程时钟映射与误差界，由 C 完成独立对尺 |
| #9 / #20 | 最新完整帧对队列、覆盖计数、过期拒绝、同 SN 有限重连、延迟统计、场景复确认。 | 头相机原生流连续测试，冻结实测曝光延迟上界及有效期 |
| #10 | pre_grasp、post_grasp、post_place 的 V 证据生成器、Mock golden 和 D FSM 兼容回归。 | 实景关联、持握、撤离后释放和稳定证据 |
| #18 / #19 | 提供观测与复检接口供 M 线接入。 | 由 M 按 H5、H6 和 T1–T5 逐级验收 |
| #11 | 三帧既有开发录包已登记 SHA-256 与原始出处。 | 独立布局、物理参考及逐条件报告，首抓后验收 |

## H1 样例与坐标

- [三帧 C 实录回放](../../../tests/fixtures/vision_exchange/c_recording_bundles_v0.1.json)源自头相机 CP2L863000KL，原流 1280×800@15，样例图为裁剪。三帧都产生四个单块候选和两个歧义候选。该结果来自同场景开发样本，独立精度仍待验收。
- [合成状态样例](../../../tests/fixtures/vision_exchange/synthetic_status_v0.1.json)覆盖正常、歧义、无效深度和过期。合成 RGB-D 可用 `python -m brick_stacking.app.offline_runner --synthetic` 重建，invalid-depth 由同一帧的深度置为 NaN 生成。
- `rgbd.sample_id` 和 `blocks[].observation_id` 只在当前采集会话内引用图像及检测。持久对象关联由 M 的事务侧维护。
- `b_extensions.top_surface_point_camera_m` 在桌面检测路径表示可见顶面中心，在单组件路径表示表面采样点。用 `top_surface_point_kind` 区分。桌面路径的 `model_center_camera_m` 由顶面沿桌面法向减去半个标称边长得到。实测顶面跨度、标称三轴尺寸和未知方向/协方差分别保留。长度单位 m，角度单位 rad，坐标系由 `frame_id` 标识。
- 录包中的原始 C 时钟桥接结果可供追溯。SDK 拟合误差与曝光参考尚未验证，`timing.exposure_host_stamp_s` 和 `timing.clock_error_bound_s` 保持 null。候选几何有效性独立于时钟有效性，`control_ready` 保持 false。

开发机回放入口，从仓库根目录运行：

```text
python -m brick_stacking.app.tabletop_runner --config config/vision_profiles/head_replacement_candidate.yaml --recordings tests/fixtures/real/C_20261108_tabletop/camera/frame_000.npz tests/fixtures/real/C_20261108_tabletop/camera/frame_001.npz tests/fixtures/real/C_20261108_tabletop/camera/frame_002.npz
```

## 在线诊断入口

机器人主机的视觉环境需要已安装仓库及既有 Orbbec SDK。候选 profile 的 SN、分辨率、HSV 和高度带沿用现有配置。采集端独占相机，检测端只保留一对待处理 RGB-D。以下数值用于诊断试跑，曝光有效期仍由 H0 实测冻结：

```text
python tools/orbbec_camera_probe.py --capture --serial CP2L863000KL --width 640 --height 480 --fps 15 --frames 450 --seconds 40 --max-skew-ms 20 --observe-profile config/vision_profiles/head_replacement_candidate.yaml --max-receive-age-s 3 --reconnects 1 --output artifacts/head_online_v_diagnostic
```

输出包含 `observation_bundles.jsonl`、实际发布帧的 NPZ 和 `camera_report.json`。报告分别统计检测耗时与主机接收到生成输出的 P50/P95/最大值，采样窗口最多 256 条。时钟验收前，曝光到输出为 null。SDK 完整帧超时、处理过期、缓冲覆盖、时间戳逆序和重连通过各自计数或事件保留。已知相机或桌面移动时调用 `LatestFramePipeline.invalidate()` 并用新 epoch 开始。可见平面或静态场景变化会触发重新确认，绝对相机静止性仍需独立参照。

## H4 复检

[Mock 请求与期望响应](../../../tests/fixtures/vision_exchange/verification_v0.1.json)覆盖持握、抓空、撤离后稳定、错色、偏移、遮挡、失效深度、超时、移机和旧帧复用。生产者使用 `verification.visual_transition.verify()`，由调用方把目标关联和图像证据装入 `VisualSample`。post_place 要求颜色相符、平面偏差 ≤15 mm、明确释放证据及独立稳定帧。真机请求还需有效曝光误差界及其证据引用。仅有供料区消失或单帧到位时返回 UNKNOWN。D 的 `PICK`/`PLACE` 回调兼容现有 `VerificationEvidence`，槽位提交仍由 FSM 负责。
