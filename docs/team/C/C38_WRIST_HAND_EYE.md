# C38 左腕眼在手上标定，2026-11-09

对应 C1-02/C1-03，M1/M2a。用户已授权左臂关节运动，但本批没有发送位置目标或使能命令。用户随后明确左臂当前无人支撑。

## 实际输入和结果

- 头部 CP2L863000KL，1280×800@15；左腕 AY6M8630086，1280×720@15。两路同时开流，顺序取帧，并非硬件同步。设备时间、SDK system/global 时间、主机接收 monotonic 分别保留；没有把接收时间冒充曝光时间。
- 20 mm 棋盘格，9×6 内角点。当前头图检测到中央棋盘54点，像素中心约(661.84,513.36)，PnP中心[0.0263565,0.1836518,0.9485667] m；RGB重投影RMS 0.147889 px，max 0.268927 px。仅RGB几何候选，未验证深度，不代表毫米级机械臂精度。
- 左腕图朝向机身下部，手掌和机身遮挡，没有完整棋盘；结果 BOARD_NOT_VISIBLE，未建立配对观测。头图还有右侧另一张棋盘，后续须固定使用同一物理目标，不混合两块中心。
- 七轴反馈已读取，can2，61–67。快照 q_rad=[-0.0110734245,-0.00275637186,0.17845310271,-0.06514092535,0.15784023702,-0.04062714580,0.09365224689]，七轴enabled均false，腕部fault均0。腕部读取用了2次Rest（改变状态），不是纯只读；腕角解码沿用SDK厂家默认Theta量程，不冒充本机参数新读回验收。
- 用户的p7_test_v1_joints.py含右臂测试，不能整套执行；p7_j67_verified.py为单腕测试。未运行它们。本批无Flash写、回零、清故障、右臂控制。

原始资料：机器人/home/qwer/c_calibration_runs/c38_dual_current/{head,left_wrist}.{png,json}，/home/qwer/c38_seven_axis_start.json；本地artifacts/c_real_calibration/c38_dual_current，以及此前c38_wrist_board01。相机流已关闭。

## 可运行交付

tools/observe_wrist_checkerboard.py IMAGE METADATA OUTPUT --columns 9 --rows 6 --square-mm 20。

输入使用捕获profile的K及k1,k2,p1,p2,k3,k4,k5,k6原始八系数，先去畸变再IPPE，原始像素重投影，保留正深度两解。输出c-wrist-checkerboard-observation-1，明确RGB_CANDIDATE/BOARD_NOT_VISIBLE，depth_validation及robot_pose_association保持NOT_PERFORMED，不发动作。

localization.wrist_camera_calibration.solve_wrist_camera复用既有点标定求解器和RigidTransform：固定桌面棋盘中心b，已知FK姿态A=T_base_reference，未知X=T_reference_camera，观测c，满足 A X c=b。用inverse(A)转换到现有求解接口，返回X与基座中的固定中心，不需要给对称棋盘虚构永久方向。不把X当抓握TCP。

验证：tests/unit/localization/test_wrist_camera_calibration.py，1 passed，已知合成安装变换及固定点恢复正确；这是算法验证。新RGB入口实际处理两路真图，头部RGB_CANDIDATE、左腕BOARD_NOT_VISIBLE。没有新的真实标定矩阵或抓放验收。

## 接下来需要的现场条件

先在可靠支撑、无明显阻力下把左前臂置于桌面上方，使腕相机看到中央棋盘；相机/底座/棋盘保持固定。未使能且无人支撑时不能用单关节试动脚本代替受控整臂抬起。若采用电控整臂到位，需要A的七轴协调保持/反馈入口和已验收的初始到位路径；当前两个单关节测试不是此接口。

进入视野后取得不同位置/朝向的七轴及棋盘配对样本，检查姿态可观测性后求解。头部同棋盘观测可计算跨相机关系并辅助复核；不能仅凭头图推断被遮挡的腕相机安装外参。10 mm为用户指定坐标误差接受标准，RGB像素残差不能代替此标准，训练拟合与独立验证继续分别报告。

给A：本机七轴可读、当前快照与单关节脚本边界；给B：两相机profile/八系数/时间原值及棋盘可见性；给D：尚无新的腕相机TF或执行许可。公共接口未变。
