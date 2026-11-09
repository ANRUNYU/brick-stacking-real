# C37 棋盘格及左腕相机（2026-11-09）

C1-02/C1-03，M1/M2a。用户新增打印棋盘格，声明每格20mm，纸平放桌面。头部相机实际检测9×6内角点，共54点；第一张RGB平面PnP重投影RMS0.141px、max0.299px。平面两解的中心差2.21mm。已实现tools/observe_checkerboard.py，保留两解，以棋盘中心作为无永久面编号的标定点，复用现有CameraFrame及点标定流程。prepare_fixed_camera_point_sample兼容显式target_id/target_geometry，原方块默认保持不变。

单次实际运行结果：RGB按20mm格长估计的距离与RGB-D深度中位差25.894mm，超过10mm诊断门槛，quality=FAIL。没有调深度尺度/格长来强行通过，也没有覆盖C35用户接受的旧外参。0.141px不是机械臂毫米精度。误差来自哪里尚未确定。

用户提出桌面棋盘格+腕相机路线，后续按此准备。无需将棋盘格绑前臂：眼在手上方案要求棋盘格相对桌面/基座固定、相机随所选参考段运动；固定头相机方案才需要目标随臂刚性运动。两种方案不能混用安装假设。

左腕Gemini2 AY6M8630086已实际开流，1280×720@15 RGB，原图未去畸变；其内参与8系数畸变保留，不套用头部335L配置。当前看到左手和桌下，尚未看到棋盘格。等待现场确认相机固定在前臂参考段还是活动手腕/手掌，决定需要哪些关节；不把相机光心当手掌/TCP。对应左腕位姿尚未求解。

原图：主机/home/qwer/c_calibration_runs/c37_checkerboard_view01和c37_left_wrist_view01；本地artifacts/c_real_calibration/同名目录。当前证据evidence/checkerboard_C37_initial.json。只做了相机开流和配置读取，无CAN/使能/Rest/动作。未扩大测试或重复哈希检查，仅运行实际帧检测。
