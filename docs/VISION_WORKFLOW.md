# 相机视觉专用开发与验收

2026-11-06 用户已明确分工：本聊天仅负责相机/视觉/定位数据，机械臂和灵巧手控制交由其他成员。旧控制诊断工具保留历史，不属于本流程入口。

## 当前状态（2026-11-06 晚间更新）

本节优先于下方首次连接的历史记录。当前确认的替换头部相机为 Gemini 335L，序列号 **CP2L863000KL**；旧相机 CP2L8630008J 的配置保留。用户已明确批准新相机一次临时 ACL，经设备身份复核后仅对当时的 `/dev/bus/usb/002/019` 执行；未改其他相机、永久规则或固件。

- 自适应桌面、密集同色分块及静态序列检查：50 帧开发回归通过。
- 新相机首次冷启动 10 帧未通过，原始数据和失败报告保留。新增至少 30 帧预热和 RGB 通道中值稳定检查后，重新采集 640×480、1280×800 各 10 帧；Windows 和 Linux 回放均通过本轮实例及静态一致性检查。
- 本地相关检查 89 项通过、1 项未执行。此结果不代表所有场景、连续运行或毫米级定位已验收。
- Linux 独立验证环境 `/home/qwer/brick_vision_validation_20261106_venv` 固定依赖见根目录 `requirements-vision-validation.txt`。原 `/home/qwer/brick_vision_venv` 仅负责相机采集，不改控制环境。
- 当前替换相机配置：`config/vision_profiles/head_replacement_candidate.yaml`。内参逐次从当前设备读取，不沿用旧相机外参。
- 后续采集使用当前仓库的 `tools/orbbec_camera_probe.py`，显式指定 `--serial CP2L863000KL`，保留默认 `--warmup-frames 30`；必须先重新枚举身份和节点。下方旧路径/旧序列号命令仅为历史示例。
- 结束时旧节点 `/dev/bus/usb/002/019` 已不存在；不能假定下一轮仍可访问该节点或 ACL 仍有效，不能将权限直接应用到同编号的其他设备。

Linux 每帧算法耗时中位数约 0.658 秒（640×480）和 1.142 秒（1280×800），尚不满足 15 Hz 在线处理。当前只输出相机坐标系下的候选位置与质量信息，`control_ready=false`。下一阶段为在线最新帧处理与延迟验收，以及独立标尺/参考点的定位误差测量。未提交正式完成版本，未操作机械臂、手或 CAN。

完整证据与限制见 `TEST_REPORTS/DENSE_LAYOUT_AND_CAMERA_TRANSFER_20261106.md`。

## 当前环境

- Windows 开发核心算法；SSH 在 Linux 运行相机 SDK。
- Linux 新建独立 /home/qwer/brick_vision_venv（system-site-packages），仅新增 pyorbbecsdk2 2.1.3，SDK 自报 2.10.6。未修改 p7_sdk_venv、机器人工作空间或控制驱动。
- 当前未发现 Orbbec ROS 驱动/图像话题，先使用官方 Python SDK 直采；后续可增加 ROS 2 图像适配器，核心检测保持不变。
- 官方参考：orbbec/pyorbbecsdk 的 v2-main，已读 commit 68cdfa181e09f0ddd0f21b77dff29cb3e7a0f0d2 的 README、对齐示例和类型接口。此 commit 是文档审查版本，实际安装的是 PyPI wheel 2.1.3，不声称两者逐文件一致。

## 当前实测与阻断

USB 层见到一台 335L 和两台其他 Gemini；SDK 枚举为一台 Orbbec Gemini 335L、两台 Orbbec Gemini2，序列号列表均为空。实际腕相机型号需核对，尚不能记录成 SDK 已验证 Gemini 335。

335L 曾从 V4L by-id 读取序列号 CP2L8630008J。SDK 通过 UID 打开时失败：usbEnumerator openUsbDevice failed。检查 /dev/bus/usb/002/013 为 root:root 0664，qwer 无写权限，无相机 udev 规则/ACL。没有取得图像、内参或深度；未通过采集验收。

2026-11-06 自动审批拒绝执行临时 ACL 修改，要求用户明确授权具体目标和范围；当前权限未变。申请仅限已核对的 335L USB 节点，为 qwer 增加 rw。USB 节点编号/UID 会随重连变化，获准后也须重新核对设备，禁止照抄旧节点操作另一设备。临时 ACL 不等于持久 udev 配置，不自动更新固件。

## Windows 离线验证

**后续实测更新**：用户已明确批准头部相机临时权限，经再次核对设备后执行成功。335L 已采集 10 组 RGB-D，序列号 CP2L8630008J、固件 1.4.60、640×480/15 Hz；数据已下载 Windows 并回放。详见 TEST_REPORTS/HEAD_CAMERA_CAPTURE_20261106.md。上面的权限拒绝与阻断为首次尝试历史，当前不再阻挡本台相机，但重新插拔后临时权限可能消失。

另外两台 0x0670 与官方源码 Gemini2 映射一致，先按 Gemini2 记录；未打开/采集，未授予额外权限，左右角色未知。不会要求必须肉眼查看铭牌才继续头部视觉开发。

安装项目后，在工程根目录：

```powershell
python experiments/scripts/run_vision_validation.py
python -m brick_stacking.app.offline_runner --synthetic
```

结果在 artifacts/test_runs，不连接硬件。原十块 Mock/手部测试不属于视觉验收流程。

## Linux 相机枚举/采集

已上传独立脚本 /home/qwer/orbbec_camera_probe.py。该文件不导入机器人包、不访问 CAN，没有运动命令或固件更新逻辑。默认仅枚举：

```bash
~/brick_vision_venv/bin/python ~/orbbec_camera_probe.py \
  --output ~/captures/vision-inventory-02
```

输出 camera_report.json，记录型号、序列号、UID 和库版本。不根据枚举索引默认选第一台。

权限与身份确认后，再选指定序列号采集：

```bash
~/brick_vision_venv/bin/python ~/orbbec_camera_probe.py \
  --capture --serial CP2L8630008J \
  --frames 10 --seconds 20 --output ~/captures/vision-head-02
```

如果序列号列表为空，只能用同次枚举的 --uid 精确定位，并在打开后核对实际序列号；不匹配则拒绝采集，不自动换另一台。首次测试一台相机，其他人不要同时打开它；不会占用机器人 CAN 控制。

## 产物与阶段

- V0：权限/身份/SDK 可打开，三台角色分别确认。
- V1：10 帧 RGB-D、真实内参、深度尺度、拍摄时间、配准和图像预览。CAPTURED 只表示取得规定数量样本，不代表深度/外参精度合格。
- V2：录制 NPZ 转回 Windows，检测颜色/实例、无效深度、歧义及遮挡，构建固定标注测试集。
- V3：多点定位误差/桌面/外参验收。涉及腕相机姿态时只读取控制负责人提供的 TF/关节数据，不由视觉程序发运动命令。

采集成功时保存 color_raw.png、color_rectified.png、depth_preview.png、frame_*.npz 和 camera_report.json。深度尺度由设备读取（mm/raw → m）；仅支持已审核畸变模型的同图去畸变，未知模型拒绝，不能拉伸深度图冒充配准。NPZ 使用现有 RecordedCamera 格式，带相机独立时钟域；没有世界外参或可执行抓取目标。

## 桌面识别回放（当前开发配置）

在 Windows 项目根目录，已安装包或设置好 src 的 PYTHONPATH 后：

```powershell
$frames = (Get-ChildItem 'artifacts/vision-head-20261106-02/frame_*.npz' | Sort-Object Name).FullName
python -m brick_stacking.app.tabletop_runner --recordings $frames --labels tests/fixtures/scenes/head_recorded_scene_labels.json
```

运行器默认加载 head_sunlight_candidate.yaml。只有对已标注的同一拍摄组才传入这份 --labels；新布局必须重新标注，不能沿用旧标注文件。不传标签时输出 INCONCLUSIVE，并保留候选和标注图供分析。

输出 overlay_*.png、height_above_table.png、events.jsonl、metrics.json。默认 ROI 基于当前 640×480 拍摄组的桌面像素边界；不是已批准的机器人工作区。

当前 10 帧均得到红4/黄3/蓝2/绿1，并通过暂定二维框匹配。当前数据用于开发调参，尚未做独立布局/光照测试，详见 TEST_REPORTS/TABLETOP_DETECTION_20261106.md。

## 并行边界

同一相机只由一个程序直接打开，后续 ROS 适配可由一个采集节点向多个视觉消费者发布。视觉不启动/关闭他人的驱动，不改动控制环境；静态精度采样时请控制负责人保持场景稳定。机械臂运动测试可与已保存图像的离线分析并行。
# 2026-11-06 自适应候选更新

新增 `config/vision_profiles/head_adaptive_candidate.yaml`：全图自动搜索桌面并提出带接缝证据的同色分割，不需要手工重填像素 ROI。旧配置保留用于基线比较。

当前离线回归：两机位共 20 帧均匹配 10 块，但 4 帧残留额外黄色不确定区域，完整验收仍为 FAIL；处理约 0.46～1.44 s/帧，尚未达到 15 Hz。详见 [开发报告](TEST_REPORTS/ADAPTIVE_TABLETOP_20261106.md)。这组数据已经参与开发，下一次验收必须使用新数据。

自动模式示例（Windows 与 Linux 复用；录制文件需实际存在）：

```bash
python -m brick_stacking.app.tabletop_runner --config config/vision_profiles/head_adaptive_candidate.yaml --recordings <frame_000.npz> <frame_001.npz>
```

未提供标注时结果为 INCONCLUSIVE；识别候选不输出机器人控制目标。相机变化后应重新确认坐标标定，不能把当帧相机坐标当成稳定世界坐标。

# 当前开发状态（2026-11-06 晚间）

此前黄色重复区域问题已进一步修复，并增加连续帧一致性检查。76 项视觉/定位测试通过；两组历史数据回归及一组新采集会话的二维匹配检查通过，Windows/Linux 固定依赖验证结果一致。完整验收尚未完成：待新物理布局、在线性能和独立定位误差测试。保持开发候选，不作为完成版本发布。

本轮报告：[冻结候选验证记录](TEST_REPORTS/ADAPTIVE_CANDIDATE_VALIDATION_20261106.md)。纯录制数据验证的固定依赖见根目录 `requirements-vision-validation.txt`；不要安装到机器人控制环境或覆盖原相机 SDK 环境。
