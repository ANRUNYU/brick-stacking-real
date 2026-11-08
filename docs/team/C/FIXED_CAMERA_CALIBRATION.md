# 头部固定相机—左臂参考段联合标定

2026-11-08，C1-01/C1-02/C1-03，M1/M2a。此方案正在实采，尚无有效的头部→左臂基座外参。沿用现有 RigidTransform、CameraFrame、URDF FK；m/rad/xyzw，T_A_B 将 B 变到 A。

## 当前无标记方块方法

50 mm 规则立方体尺寸来自用户尺量。用户不能在方块上写字，因此不要求角点编号或标记板。将方块刚性固定在 L5_Link 外侧、J6/J7 之前的金属框，安装版本 left_L5_cube_mount_candidate_20261108_v1。位置依据现场照片与厂家连杆模型对比，背面固定仍需现场确认；不把 L5 当法兰/TCP。

每个姿态通过三个可见面的内部深度点拟合中心；棋盘式像素划分训练/检查点。保留独立平面法向与误差；可显式启用已知规则立方体的正交约束，不能修改检查阈值来追求通过。输出中心，不输出虚构的方块姿态。

关节仅读取左 can2 的 61–65，READ 0x06；用已固定 SHA 的厂家 URDF 得到 T_base_L5。未知方块中心偏移 p 与相机外参 X 联合求解：R_i p + a_i = R_X c_i + t_X。不依赖 J6/J7 量化范围或已知 TCP。至少 6 个训练姿态及 4 个独立验证姿态，建议 8+4；重复三帧只检查同一姿态的重复性。线性初值要求满秩，再投影旋转并优化；单轴/重复/退化数据拒绝。方块、相机或安装改变后重新分版本，不能混合。

## 工具与最小调用

设置 PYTHONPATH=src，使用 artifacts/planning_venv/Scripts/python.exe：

```powershell
python tools/measure_cube_center.py FRAME.npz ROI_CONFIG.json CENTER.json
python tools/prepare_calibration_reference.py RAW_READS.json PINNED_MODEL.urdf REFERENCE.json --sample-id POSE_ID --max-receive-span-s 0.01
python tools/solve_fixed_camera.py calibration/examples/fixed_camera_point_synthetic.json CANDIDATE.json
```

ROI_CONFIG 显式给 camera_serial、edge_m、edge_source、roi_source、三个不重叠凸 face_polygons_xy、erosion_px、plane_threshold_m、min_inlier_ratio、max_holdout_m、max_normal_dot、max_condition_number，可选 regular_cube_constraint。每个面至少20训练/10检查点。原始帧 SHA、设备时间与主机接收时间分别保留。

点模式输入见 fixed_camera_point_synthetic.json；真实样本须有唯一 image_id/joint_sample_id/sample_id、source=real、参考系与安装段一致、版本/时钟/epoch、中心质量和具体时间关联依据。样例不能改名冒充实测。求解只产生 approved=false、motion_enabled=false 的候选，不提供运动许可。

另有 target_pose.py / estimate_calibration_target.py 的非共面已编号点 PnP，以及 fixed_camera_calibration.py 的完整位姿联合求解，适用于将来具备可靠编号特征时；当前无标记方块不走该分支。

## 真实采集与时钟

c_static_calibration_capture.py 采用独立进程连续读取五轴，父进程打开指定头部 Gemini335L CP2L863000KL；不会实例化运动 SDK。源码锁定相机助手及关节读取助手 SHA。仅发位置 READ，没有 Rest/使能/目标/回零/清故障/Flash。

device stamp 保持相机时钟；host_receive_stamp_s 属于主机 monotonic，epoch 为 Linux boot_id。静止记录门槛在采集前设为关节跨度 0.001 rad、状态间隔 0.2 s；这只是数据质量门槛，不是安全参数。相机主机接收窗口要被状态覆盖。静止关联不能证明设备到主机延迟映射，device_host_latency_mapping 仍 UNKNOWN，calibration_sample_valid 默认 false。不能把接收时间改名成曝光时间。

## 已有实测证据及限制

- 桌面方块 c31_head_view_20261108c：三个重复帧，正交约束后两帧检查最大误差为2.822/2.169 mm，通过预设3 mm门槛；另一帧3.023 mm失败，原样保留。这不是绝对测量精度，也不是安装后的联合标定样本。
- c31_static_pose01 的旧线程记录：47组完整读数但最大间隔1.694 s，失败。相机原生初始化阻塞同进程采样，已改为独立只读进程，不降低门槛。
- c31_static_pose01_retry：98组完整五轴读数，最大间隔0.051552 s，最大关节跨度0.000191748 rad，静止采集 PASS。但复核图像中机械臂/固定方块均未入镜，因此不能生成中心或外参样本；保留为采集链验证。
- visible/settled 两次复拍仍无固定块入镜，且关节跨度超过采集前门槛，因此均失败；桌面投影变化，相机/底座是否移动尚未确认。用户请求再次拍照，继续复核，不假定安装未变。三次采集的原件SHA及清单见 evidence/fixed_camera_acquisition_C31.json。
- 正在重采入镜姿态；未生成有效标定矩阵。原始文件在机器人 /home/qwer/c_calibration_runs/ 对应目录，本地镜像 artifacts/c_real_calibration/。这些目录不进 git；对外证据应按授权和白名单另行归档。

## A/B/D 交接

|方向/合并点|输入或交付|验证与仍缺内容|
|---|---|---|
|A→C M0/M2a|五轴原始06反馈、命名/模型SHA、host时间与boot epoch；完整执行仍需七轴|prepare_calibration_reference.py核对raw与rad一致，不补腕角；不提供七轴执行状态替代品|
|B→C M1/M2a|RGB-D原帧、K/D、对齐与rectified标志、SN/profile、设备/接收时间|measure_cube_center.py保留SHA与逐面检查；设备—主机时间映射尚未验收|
|D→C M2a/M4|固定块身份、50mm尺寸来源、安装版本、固定段与无晃动确认|安装改变即失效；实际整手抓握关系仍未知|
|C→A/D M2a/M3|solve_fixed_camera.py版本化候选X、中心相对L5偏移、训练/独立验证误差及退化报告|只有数据集充分且独立验证后才交付候选；绝不将中心偏移命名为抓握TCP，不自动允许执行|

本批不完成C1-05真机单块闭环、实际抓握TCP/持物偏移或M5/M6十块验收。规划/IK/轨迹/局部碰撞分别已有离线实现，真实场景、完整碰撞覆盖和执行依赖继续保持未完成。
