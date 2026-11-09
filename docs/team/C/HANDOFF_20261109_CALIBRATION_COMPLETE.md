# 2026-11-09 标定收官与开发交接总结（C47–C49）

本文档总结截至 **2026-11-09 21:40** 的真机标定进展、主机环境状态、文件与脚本路径，以及后续视觉（B）、机械臂控制（A）、规划（C）与状态机（D）的联调开发路径，便于团队成员无缝交接与并行推进。

---

## 1. 当前项目整体进度总览

目前项目已将 A、B、C、D 各阶段基础分支汇总合并至 `main` 主分支，**左机械臂（主工作臂）作业所需的全部核心标定参数已采集并求解完毕**：

| 模块分工 | 当前完成状态 | 已有核心产出文件 | 待推进下一步 |
| :--- | :--- | :--- | :--- |
| **C：标定与坐标链** | **核心标定全部完成（100%）** | 1. 头部相机外参：[`C35_left_head_fit_only_user10mm_20261108.json`](../../../calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json)<br>2. 左腕相机外参：[`C48_left_wrist_fit_only_user10mm_20261109.json`](../../../calibration/candidates/C48_left_wrist_fit_only_user10mm_20261109.json)<br>3. 左爪持块偏移：[`C49_left_grasp_offset_candidate_20261109.json`](../../../calibration/candidates/C49_left_grasp_offset_candidate_20261109.json)<br>4. 多角点腕相机求解器：[`wrist_camera_calibration.py`](../../../src/brick_stacking/localization/wrist_camera_calibration.py) | 将 `C49` 的真实 `T_flange_block` 接入 `c_scene_geometry.py` 与数值 IK 轨迹生成 |
| **B：视觉感知** | **离线自适应分割已就绪，可与真机并行调优** | [`tabletop_segmentation.py`](../../../src/brick_stacking/vision/tabletop_segmentation.py)、[`color_segmentation.py`](../../../src/brick_stacking/vision/color_segmentation.py)、[`HANDOFF_20261109.md`](../B/HANDOFF_20261109.md) | 对接桌面红/黄/蓝/绿 50 mm 木块的实时/单帧检测输出 `BlockPose` |
| **A：左机械臂控制** | **7 轴只读采样与 Mock 轨迹反馈已完成** | [`c_left_arm_readonly_probe.py`](../../../tools/c_left_arm_readonly_probe.py)、[`adapter.py`](../../../src/brick_stacking/arm/adapter.py)、主机 `read_7axis_once.py` | 在安全监督下接入单块抓取/放置的低速真机轨迹执行 |
| **D：灵巧手与任务编排** | **O6 只读探测、单块/十块状态机已完成** | [`o6_hand.py`](../../../src/brick_stacking/hardware/o6_hand.py)、[`pick_place_fsm.py`](../../../src/brick_stacking/execution/pick_place_fsm.py)、[`task_scheduler.py`](../../../src/brick_stacking/planning/task_scheduler.py) | 使用 `C49` 实测抓握角度预设，完成张手—闭合—释放动作封装 |

---

## 2. 本轮关键技术突破与标定成果（C47–C49）

### 2.1 破解 C37 棋盘格 25.9 mm 深度差悬案（`C47`）
- **原因定位**：现场 A4 纸打印的 `10 × 7` 棋盘格（`9 × 6` 内角点）因打印机页边距自动缩放，真实方格边长并非标称 `20.0 mm`。通过 `c47_scene_clearance60cm01` 激光深度点云反投影与卡尺实测确认，真实平均格长为 **`19.38 mm`（`19.30 ~ 19.47 mm`）**。
- **验证结论**：将 `square_size_m = 0.01938` 代入 PnP 后，RGB 视觉距离与激光深度距离之差从 `25.9 mm` 降至 **`< 0.2 mm`**，彻底消除了尺度矛盾。

### 2.2 修复 Orbbec 相机 Linux USB 权限问题
- 在机器人主机（`10.157.173.135`）新增持久化规则 `/etc/udev/rules.d/99-orbbec.rules`：
  ```udev
  SUBSYSTEM=="usb", ATTR{idVendor}=="2bc5", MODE="0666"
  ```
- 普通用户 `qwer` 无需 `sudo` 即可直接打开全部 3 台 Orbbec 相机（头部 `CP2L863000KL`、左腕 `AY6M8630086`、右腕 `AY6M86300GH`），重启或拔插 USB 后永久生效。

### 2.3 完成左腕相机眼在手上标定（`C48`）
- **算法实现**：在 [`src/brick_stacking/localization/wrist_camera_calibration.py`](../../../src/brick_stacking/localization/wrist_camera_calibration.py) 中新增 `solve_wrist_camera_from_head_bridge` 与 `solve_wrist_camera_from_fixed_board_corners`（利用 54 个棋盘格内角点的 3D 刚体约束，通过交替 Kabsch 与阻尼 Gauss-Newton 联合求解，自动消解普通棋盘格 180° 翻转对称歧义）。
- **真机采样与结果**：采集 6 组不同视角与位置的左腕观测样本（保存在主机 `/home/qwer/c_calibration_runs/c48_wrist_handeye_live/pose_01..pose_06`），生成候选文件 [`calibration/candidates/C48_left_wrist_fit_only_user10mm_20261109.json`](../../../calibration/candidates/C48_left_wrist_fit_only_user10mm_20261109.json)：
  - 5 组完全静止样本中心点拟合 **`RMSE = 8.63 mm`（`< 10 mm`）**，270 个 3D 角点 `RMSE = 9.59 mm`；
  - 实测左腕相机光学中心相对 `L8_Link` 法兰原点的平移为 **`[+31.28, -23.95, +67.33] mm`**（距离法兰中心 `77.9 mm`）；
  - 交叉验证确认腕部 `MotorV2` 电机 `66` 对应 `L6_Joint`（符号 `+1`）、电机 `67` 对应 `L7_Joint`（符号 `+1`）。

### 2.4 完成左手爪持块抓取偏移标定（`C49`）
- **采样方法**：将 `50 × 50 × 50 mm` 蓝色木块放置在桌面棋盘格上（经头部相机 21 个未遮挡方格中心亚像素 PnP 定位，重投影误差 `0.27 px`，桥接高度偏差 `< 2.6 mm`，定出木块在 `L_arm_root` 下精确位姿 `T_base_block`），操作员手扶左臂使 O6 灵巧手处于稳固捏住木块的抓取姿态，连续采集 6 组（3 训练 + 3 验证）7 轴角度与灵巧手角度。
- **标定结果**：生成标准候选文件 [`calibration/candidates/C49_left_grasp_offset_candidate_20261109.json`](../../../calibration/candidates/C49_left_grasp_offset_candidate_20261109.json)：
  - 训练/验证集最大平移波动仅 **`0.038 mm`**，`consistency: PASS`；
  - 实测木块中心相对 `L8_Link` 的平移为 **`[+75.87, -56.90, -87.91] mm`**（直线距离 **`129.3 mm`**）；
  - 记录左手 O6 灵巧手（`can1`, ID `0x28`, SN `LHO6-04-322-L-Z-1-D`）捏取 50 mm 木块的关节角度预设：`angles_raw = [245, 58, 246, 246, 254, 254]`。

---

## 3. 坐标变换完整调用公式（供 A / B / C / D 联调）

项目中所有变换矩阵遵循约定：**`T_A_B` 将 `B` 坐标系中的点变换到 `A` 坐标系**（即 $p_A = T_{A\_B} \cdot p_B$）。

1. **头部相机定位桌面木块**：
   $$T_{\text{L\_arm\_root\_block}} = T_{\text{L\_arm\_root\_head\_cam}}^{(\text{C35})} \cdot T_{\text{head\_cam\_block}}$$
2. **左腕相机近距离复核桌面木块**：
   $$T_{\text{L\_arm\_root\_block}} = T_{\text{L\_arm\_root\_L8\_Link}}(q_{1..7}) \cdot T_{\text{L8\_Link\_wrist\_cam}}^{(\text{C48})} \cdot T_{\text{wrist\_cam\_block}}$$
3. **由目标木块位姿计算左臂末端法兰 `L8_Link` 抓取/释放目标位姿**：
   $$T_{\text{L\_arm\_root\_L8\_Link}}^{\text{target}} = T_{\text{L\_arm\_root\_block}} \cdot \left(T_{\text{L8\_Link\_block}}^{(\text{C49})}\right)^{-1}$$
   （代码中可直接调用 [`brick_stacking.localization.calibration.tcp_target_for_block`](../../../src/brick_stacking/localization/calibration.py#L61-L63)）。

---

## 4. 机器人主机（`10.157.173.135`）关键路径速查

- **Python 虚拟环境**：
  - 视觉与 Orbbec 相机环境（Python 3.12 + `pyorbbecsdk` + `opencv` + `pytest`）：`/home/qwer/brick_vision_venv/bin/python`
  - 机械臂 SDK 与 Pinocchio 运动学环境（含 `linkerbot` + `pinocchio`）：`/home/qwer/p7_sdk_venv/bin/python`
- **主机标定工作区脚本（`/home/qwer/wrist_calib_workspace/`）**：
  - `read_7axis_once.py`：安全读取左臂 `can2` 7 轴角度（`61..65` 只读寄存器 `0x06`，`66..67` 检查 `mode==2` 后单次 `Rest` 读取 16-bit 角度，零运动/零 Flash 写入）。
  - `read_grasp_state_once.py`：同步只读采样左臂 7 轴角度 + `L8_Link` FK 位姿 + 左手 O6（`can1`）6 指状态快照。
  - `live_wrist_capture.py`：双相机 + 7 轴实时网页预览（`http://10.157.173.135:8765`）与静态手眼标定自动采样器（当前已停止，所有相机与 CAN 句柄均处于空闲状态）。
- **主机实采归档数据（`/home/qwer/c_calibration_runs/`）**：
  - `c48_wrist_handeye_live/pose_01..pose_06`：左腕手眼标定 6 组实采图像与关节记录。
  - `c49_blue_block_locate/`：移动桌面后的棋盘格与蓝色木块定位数据及 6 组抓握采样原始记录。

---

## 5. 下一步并行开发建议

1. **视觉组（B）**：
   - 可直接使用离线数据集 [`tests/fixtures/real/C_20261108_tabletop/`](../../../tests/fixtures/real/C_20261108_tabletop/) 或主机 `/home/qwer/c_calibration_runs/c49_blue_block_locate/head_rgbd.npz`（包含桌面上摆放的红、黄、蓝、绿全部四色木块高分辨率 1280×800 RGB-D 实拍帧！）调试四色木块分割与 3D 位姿估计。
   - 如需在真机开摄像头测试，目前 3 台相机全部空闲；注意同一台相机在同一时刻只能被一个进程打开。
2. **规划与控制组（A / C / D）**：
   - 将 [`C49_left_grasp_offset_candidate_20261109.json`](../../../calibration/candidates/C49_left_grasp_offset_candidate_20261109.json) 中的 `T_flange_block` 与当前桌面实拍木块坐标接入 [`tools/c_scene_geometry.py`](../../../tools/c_scene_geometry.py) 和 [`numerical_ik.py`](../../../src/brick_stacking/planning/numerical_ik.py)，离线算出第一块木块从“预抓取 $\rightarrow$ 抓取 $\rightarrow$ 抬起 $\rightarrow$ 放置”的 7 轴关节轨迹并进行碰撞复核。
