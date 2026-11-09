# 标定状态与真机标定候选索引（更新至 2026-11-09）

当前已完成左机械臂（主工作臂）作业所需的**三大核心真机标定候选**，保存在 `calibration/candidates/` 目录下。所有候选均附带设备序列号、URDF 模型 SHA256、坐标系映射、采样残差及版本追溯记录。

## 1. 真机标定候选清单（`calibration/candidates/`）

| 标定项 | 候选文件路径 | 变换矩阵符号 | 目标系 $\leftarrow$ 源系 | 核心精度指标 | 状态说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **头部固定相机外参（`C35`）** | [`C35_left_head_fit_only_user10mm_20261108.json`](candidates/C35_left_head_fit_only_user10mm_20261108.json) | `T_base_camera` | `L_arm_root` $\leftarrow$ `camera_CP2L863000KL_color_optical_frame` | 6 组静态采样拟合 `RMSE = 3.75 mm`，`max = 6.72 mm`（`< 10 mm`） | 用户按 `10 mm` 门槛接受拟合（`OPERATOR_ACCEPTED_FIT_ONLY`） |
| **左腕眼在手上外参（`C48`）** | [`C48_left_wrist_fit_only_user10mm_20261109.json`](candidates/C48_left_wrist_fit_only_user10mm_20261109.json) | `T_reference_camera` | `L8_Link` $\leftarrow$ `camera_AY6M8630086_color_optical_frame` | 5 组完全静止姿态中心 `RMSE = 8.63 mm`（`< 10 mm`），270 个角点 `RMSE = 9.59 mm` | 实测相机距 `L8_Link` 原点偏移 `[+31.3, -23.9, +67.3] mm`（范数 `77.9 mm`） |
| **左爪持块抓取偏移（`C49`）** | [`C49_left_grasp_offset_candidate_20261109.json`](candidates/C49_left_grasp_offset_candidate_20261109.json) | `T_flange_block` | `L8_Link` $\leftarrow$ `block_blue_c49_moved` | 6 组连续夹持采样（3 训练 + 3 验证）最大平移波动 `0.038 mm`，`consistency: PASS` | 实测木块中心相对 `L8_Link` 偏移 `[+75.9, -56.9, -87.9] mm`（范数 `129.3 mm`） |

## 2. 关键物理基准与实测参数

- **比赛积木规格**：`50 × 50 × 50 mm` 规则正方体漆面木块（红 4、黄 3、蓝 2、绿 1，共 10 块）。
- **现场棋盘格规格**：A4 纸打印 `10 × 7` 方格（`9 × 6` 内角点），标称格长 `20 mm`；经 `C47` 激光深度反投影与实测卡尺复核，因打印页边距缩放真实平均格长为 **`19.38 mm`（`19.30 ~ 19.47 mm`）**。
- **左臂腕部关节映射验证**：左臂 `can2` 总线电机 `61..65` 为 `A7Motor`（`L1..L5_Joint`），电机 `66, 67` 为 `MotorV2`（对应 `L6_Joint, L7_Joint`，符号均为 `+1`），由 `C48` 多姿态手眼残差唯一确定。
- **左手 O6 灵巧手抓取预设（`C49`）**：总线 `can1`（ID `0x28`，序列号 `LHO6-04-322-L-Z-1-D`），50 mm 木块对侧捏取原始角度 `angles_raw = [245, 58, 246, 246, 254, 254]`（顺序：`thumb_flex, thumb_abd, index, middle, ring, pinky`）。

## 3. 安全约定

所有标定输出文件默认保持 `"approved": false, "motion_enabled": false`。标定文件仅提供几何坐标变换，不代表自动授予真机闭环运动执行许可。
