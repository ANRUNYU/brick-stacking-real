# 左臂状态采集审查（2026-11-07，C1-02/C1-03/M2a）

现场用户提供：左臂can2，J1…J7为61…67。主机已上电、无状态程序；现有控制进程是右手，保留不动。设备对应关系不是当前七轴反馈或标定验收。

## 已通过SSH读取的历史测试脚本

|主机文件|SHA256|实际内容|
|---|---|---|
|/home/qwer/p7_test_v1_joints.py|55aa0f2c22698dd0620fcfc9eb5d6d2de2828daca9541f1ce5ad9ddb37f362ee|LEFT只列J2…J5；另外包含RIGHT J1…J5。无参数选择；执行到确认后会设置模式/速度/目标并可能使能，不可import来读取状态。|
|/home/qwer/p7_j67_verified.py|0cb59850bc03f0ba49ca65d83d4445f41e1f8963d44752bb0831867ab5806f1c|选择左J6或J7；先读Flash模式，再read_initial_state发Rest，之后使能、心跳、5度/6秒/Kp12运动，最后解除使能。不是纯读取脚本。|

用户陈述这些关节此前已验证可通信/运动；本轮未重新执行测试脚本，不能把历史成功等同于当前新鲜状态。源码审查证据来自SSH读取，不依靠离线猜测。

现场SDK src/linkerbot/arm/a7/motor.py:124–156确认J1…J5为标准CAN ID、单字节06查询，返回命令字节后float32 little-endian rad。src/linkerbot/arm/p7/motor_v2.py:498–502确认read_initial_state发送FF×7+FD的Rest状态切换；start_polling是控制心跳。未找到经核验的V2纯实时角度查询，因此不猜协议、不将缓存当新鲜数据。

## 本轮独立工具

tools/c_left_arm_readonly_probe.py仅标准库，固定can2、仅允许61…65的06查询；66/67只被动接收原始反馈。无SDK构造、无使能/解除使能/回零/模式/Flash写入；剔除本机TX、扩展/RTR/error/无效数据。V2量化尚未实测确认，因此保留raw、不套默认范围换算。输出始终calibration_sample_valid=false，不对公共ArmAdapter接口增加不兼容要求。

在Linux机器人主机的经审阅源码副本上运行：`python3 c_left_arm_readonly_probe.py <新输出.json>`。输出目录须已存在，文件必须不存在。原始工具本轮经SSH stdin运行，未修改原脚本或SDK。

结果：5个查询写入SocketCAN成功，2.254秒窗口内收到0个合格响应。send成功表示内核接受请求，不能当作驱动应答或物理执行证据。can2当时UP/LOWER_UP、1Mbps、ERROR-ACTIVE、tx/rx错误计数0；不能仅据此判定设备断电、接线错误或SDK错误。无CAN接口配置改变，无右臂/手命令。

原始报告：/home/qwer/c_calibration_runs/left_readonly_C22_9b6c0c59-88a1-40c3-abb2-48c45b10a479.json；SHA256 52f73c33b56fb5afb8c45067ced2b1126909317b559d854afe34dbcff4c1e01f。本地内容副本evidence/left_readonly_capture_C22.json。时间是host_monotonic收取/出队时间，并非设备采样时间；epoch仅本会话标识，不与其他会话时钟合并。

## A/C交接及下一入口

M2a需要A或经现场审核的状态入口提供：左设备/总线绑定版本、七轴具名rad值、每轴接收时间与原始帧、clock domain/epoch、反馈模式/故障、新鲜度与跨轴时差；并锁定原始角度→模型符号/零位版本。不能用零或历史值补缺轴。

若取得V2纯查询协议，先审源码和字节再复用本工具；若厂家仅支持Rest触发或使能后反馈，则下一轮须准备机械支撑、当前状态/模式检查、退出方案及明确现场操作授权，再改变状态。此轮不执行Rest获取角度。固定点接触和8组姿态采集必须等完整可靠状态入口；不要为采样自行搬动已上电机械臂。

验证：7项工具回归（只允许5个read ID、拒本机回显/控制帧/非标准帧/NaN、V2不默认量化、窗口约束）；全套161 passed，命令 `artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c22-final`。软件测试与本轮真实CAN查询分别报告，不代表TCP/完整避碰或执行验收。
