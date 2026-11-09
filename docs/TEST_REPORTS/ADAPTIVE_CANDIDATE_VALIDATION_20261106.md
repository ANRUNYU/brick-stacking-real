# 自适应视觉候选：冻结验证记录

日期：2026-11-06。状态：**本地开发候选，未完成正式验收，不发布、不推送完成版本。**

本记录续接 `ADAPTIVE_TABLETOP_20261106.md`，保留此前失败报告作为历史证据，不覆盖旧结果。

## 本轮修复

1. 多阈值提出的黄色区域不再仅按像素距离消重。对已通过几何验证的实例建立临时体积假设，检查重复区域的实际深度点能否被已有实例解释。平面残差、受上限约束的尺寸/高度模型偏差，以及通过实际内参传播的半像素采样范围，均写入诊断。覆盖比例是像素支持比例，不是统计置信度，也不是实测传感器精度。
2. 解释为重复表面的原提议、支持实例及容差完整保留在 `explained_surface_fragments`；落在体积范围外的真实部分可见物体仍保留为不确定。新增相邻部分物体、同像素异深度及错误模型不确定性放大的反例测试。
3. 接缝搜索改在原始分辨率的局部区域内运行，再恢复全图掩码和坐标，减少递归过程重复扫描整幅图像的开销，没有用缩小图像换取表观精度。
4. 新增连续观测检查：至少三帧一致才确认；重复/倒退时间戳、旧会话回放、采集间断、候选歧义、物体位置/数量变化、支撑平面变化和明显背景变化，会拒绝或重新累计。旧结果不用于补齐当前帧。缓存使用独立快照，防止调用者修改旧列表而掩盖物体移动。
5. 发现 Linux 原环境 OpenCV 4.6 低于工程声明的最低 4.10。新建独立的纯视觉验证环境，用与 Windows 一致的 NumPy 2.5.4、OpenCV headless 5.0.0.93、PyYAML 6.0.3 验证。原相机 SDK 环境、ROS 环境、臂/手 SDK 均未修改。
6. 固定依赖环境中通过覆盖 `PYTHONPATH` 避免继承 ROS 的 Python 搜索路径。最初 pip 在继承 ROS 路径时报告 launch-ros 缺少 setuptools；清除继承路径后 `pip check` 通过，确认验证进程不可导入 rclpy。未因此修改 ROS 或补装控制依赖。

## 已通过的检查

- 自动化：76 passed、1 deselected；仅视觉、相机数据、定位数学。包含场景移动、同色接缝、均匀矩形不得强拆、重复表面与真实部分物体区别，以及时序故障反例。
- 旧机位与新机位两组历史录制数据，共 20 帧：每帧 10 个匹配，FP=0、FN=0、AMBIGUOUS=0；各组前两帧预热，第三帧起连续观测一致。均为开发回归，不再视为独立场景。
- 冻结源码和配置后，于 19:20（北京时间）重新打开头部相机 CP2L8630008J 采集 10 帧 RGB-D。当前图像布局与前一轮基本一致，光照更暗；这验证新采集会话与这一光照变化，**不构成新的布局验收**。
- 新采集数据经人工图像复核、临时二维标注，Windows 和 Linux 的冻结候选均通过匹配及连续帧检查，每帧 10 个匹配且无额外不确定区域。
- 固定依赖的 Linux 与 Windows 逐帧、逐颜色对应，共比较 100 个中心，最大数值差约 `4.97e-16 m`。这仅表明同输入计算一致，不能解释为机器人或相机测量精度。
- Linux 只对头部相机采集；USB 身份与原临时权限已重新核对，未新增权限。相机不再采集、SSH 已退出，无控制动作。

## 证据索引

以下均相对项目根目录：

- 自动化：`artifacts/test_runs/2026-11-06/Verification_VisionCore_PYTHON_202611061917`
- 历史回归：`artifacts/test_runs/2026-11-06/Perception_TabletopBlocks_RGBD_202611061917` 及 `_R02`
- 冻结文件 SHA-256 清单：`artifacts/adaptive_validation_20261106_02/freeze.json`
- 新 RGB-D：`artifacts/vision-head-adaptive-20261106-03`
- 新二维标注：`artifacts/adaptive_validation_20261106_02/fresh_labels.json`
- Windows 新数据重放：`artifacts/test_runs/2026-11-06/Perception_TabletopBlocks_RGBD_202611061922`
- Linux 固定依赖记录：`artifacts/adaptive_validation_20261106_02/linux_pinned_reports/pinned_runs/2026-11-06/Perception_TabletopBlocks_RGBD_202611061929`
- 平台与隔离审计：`artifacts/adaptive_validation_20261106_02/linux_pinned_reports/pinned_platform_summary.json`
- 汇总：`artifacts/adaptive_validation_20261106_02/validation_summary.json`

## 尚未通过的门槛

- 未见的新物理布局：已请求现场改变位置、方向和同色块间距，等待用户明确完成；“调整完成后回复”不视为已经调整，不提前采集或认定通过。
- 在线实时性能：Windows 新数据单帧处理约中位 0.38 秒；Linux 固定依赖环境约中位 0.728 秒、最大 0.740 秒。含识别与连续帧检查、不含文件读写和相机采集时延。未达到 15 Hz，也尚未运行连续在线识别链路。
- 三维精度：缺少独立实测参考、边长测量及外参验收。临时二维框和低阈值 IoU 不检验毫米级定位、实例轮廓、姿态或抓取精度。
- 任意环境适应：多层堆叠、隐藏物体、严重遮挡、极端机位、完全不可见的同色接缝和更大范围照明变化尚未验收。
- 连续帧一致不等于相机静止或世界坐标稳定；输出仍为当帧相机坐标，`reference_stationarity_verified=false`、`control_ready=false`。

本轮尝试了减少平面采样、提前结束 RANSAC 和全深度重拟合等提速方法。由于综合提速或稳定性未达到要求，未将这些试验设置用于冻结候选；保留稳定搜索设置。可选 RANSAC 提前终止接口有单独测试，但默认候选未启用。

## Linux 复现范围

- 采集仍使用原专用 `/home/qwer/brick_vision_venv`，只调用指定头部相机。
- 录制数据验证使用 `/home/qwer/brick_vision_validation_20261106_venv`，依赖对应根目录 `requirements-vision-validation.txt`；该环境不含相机 SDK 或 ROS 驱动，不用它代替机器人控制环境。
- 冻结候选位于 `/home/qwer/vision_candidate_20261106_02`，通过显式 `PYTHONPATH=<候选目录>/src` 运行 `brick_stacking.app.tabletop_runner`。代码和验证记录都独立于现有控制工程。

下一步保持此冻结版本，先做未见布局检验。若失败，记录问题并继续修改，不以更改验收阈值、删除失败帧或补足固定块数来获得通过。
