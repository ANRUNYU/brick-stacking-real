# 公共接口契约 v0.1（待M0全员确认后冻结）
已有CameraFrame、BlockDetection、BlockPose及hardware/protocols.py优先复用；下表是语义要求，不要求平行新建全部类。

这些名字是本项目建议接口，不声称厂商SDK已有同名API。M0由D维护薄类型文件、C核对几何字段、A/B核对设备字段，全员确认。各模块自行提供实现和Mock。

## 1. 公共数据约定
- 长度m、角度rad、时间s；hand raw_u8与percent显式区分，禁止隐式当rad。
- 关节顺序J1…J7，并附SDK索引/真实ID映射，不能靠列表长度猜顺序。
- T_A_B将B系坐标映射到A系；平移m，四元数xyzw。公共坐标至少world/table/active_arm_base/active_tcp/head_color_optical；运行时映射到具体左右角色。
- 所有状态包含sample_id、source（mock/recorded/real）、设备SN/ID、frame_id、device_stamp（可null）、host_receive_stamp、clock_domain、epoch、validity和reason。
- 设备时钟不直接当主机或ROS时间；重置epoch后旧图像/TF不可复用。有效期由已测时延确定，阈值未配置则禁止真实动作。
- 配置/标定以不可变版本hash关联；不在动作中途静默替换。

## 2. 模块间数据
|类型|必要内容|生产者|使用者|
|---|---|---|---|
|ArmState|关节名、q_rad、dq_rad_s（可未知）、使能/故障（可未知）、时间和有效位|A|C/D|
|HandState|角色/SN、六通道原始值、映射版本、故障/温度/触觉能力有效位|D|C/任务逻辑|
|RGBDObservation|相机SN、RGB/depth引用、K/D、原始尺度、profile、空间配准标志和时间差|B|B感知/C标定|
|BlockObservation|observation_id、camera frame位姿、颜色、尺寸来源、质量/协方差或未知、可见性|B|C/D|
|LocalizedBlock|observation_id、world位姿、输入TF/校准版本、误差/有效性|C|D|
|SceneSnapshot|scene_version、持久block_id、槽位/持物/支撑状态及观测证据引用|D|B/C|
|GraspPreset|手角色、预设版本、数值单位/速度、几何假设和适用物体|D|C/执行流程|
|PlanRequest|block_id/slot_id、scene_version、目标、preset、起点状态与配置版本|D|C|
|PlanResult|可行性、拒绝原因、轨迹/抓放分段、校准/碰撞模型/scene版本、有效期|C|D/A|
|VerificationEvidence|检查对象、阶段、PASS/FAIL/UNKNOWN、误差、图像/观测引用及时间|B|D|
|ExecutionResult|command_id、状态、实际反馈、开始结束时间、取消/故障原因|A或D手模块|D任务逻辑|

B负责单次观测及短期关联线索；D拥有持久block_id、持有者和任务场景唯一真相。B不直接把slot提交为成功。C负责坐标转换，B不写机械臂外参，D不重算另一套TF。

## 3. 建议方法
A：read_state()、validate_trajectory()、execute_trajectory(trajectory, permit)、cancel(command_id)、get_execution_result()、request_stop(policy)。
B：get_observation()、detect_blocks(observation)、verify(request)、replay(recording)。V 线门面见 `brick_stacking.vision.service`（`VisionSession.get_observation` / `detect_blocks` / `verify` / `replay`）；`control_ready` 在时钟误差界与标定 hash 就绪前保持 false。
C：localize(observation, transforms)、plan_pick_place(request)、validate_plan(plan, context)。
D手：read_hand_state()、execute_preset(preset, permit)、get_hand_result()、request_hand_stop(policy)。
D流程：run(task_spec)、cancel(task_id)、get_task_state()。

执行状态统一为PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED/UNKNOWN。只有实测满足到位/完成判据才SUCCEEDED；驱动发送成功只是ACK。
stop返回请求已发送、反馈已确认、保持能力和未确认原因等信息。停止轮询、关闭连接、断使能和保持位置有不同物理后果，不统一伪装为成功。

## 4. SafetyGate和职责
D实现执行前SafetyGate并生成短期permit，关联设备、轨迹hash、配置/校准/scene版本和有效期。A独立检查硬件身份、当前起点、时间、数值、速度/加速度/关节限位与许可；D手模块也独立检查。
C负责完整路径的几何/碰撞与可达性证据，B提供图像质量和时序证据，A提供新鲜设备状态与StopPolicy能力。
permit不是安全硬件，不能替代物理急停或已验证的控制能力。首次动作需现场受控授权；正式自主运行经一次合法启动后不逐动作等人点确认。
调用cancel/stop后无自动盲目撤退，依据现场已验收策略处理；反馈未知时不得假定可安全断使能。

## 5. 最小样例集与兼容性
M0固定：正常积木观测、无效深度观测、过期状态、7轴样例轨迹、不可达规划结果、正常执行、取消未确认、视觉UNKNOWN。
D保存样例索引；A提供执行/反馈样例，B提供观测/复检样例，C提供几何/轨迹样例。每份Mock由其接口生产者维护。
接口变更先改本文和样例，生产者+使用者审查；破坏性变更升级schema_version，在同一组PR更新调用方。不能只改自己模块后让别人追着适配。

### V/M H0 草案观测与复检

- `ObservationBundle` 以 `schema_version`、`profile_hash` 和采集会话关联现有 `RGBDObservation`、`BlockObservation`。旧录包缺主机接收时间或原始深度尺度时以 null 表示。已配准、去畸变的数据使用有效 K 与空 D，原始参数如有保存在 `timing.raw_intrinsics`。
- 位置估计通过 `b_extensions` 交换，`camera_pose` 保持 null 直到可提供完整观测姿态。顶面采样或中心、模型块中心、实测跨度、标称尺寸、未知方向和未知协方差各自保留。该草案由 C/D 审查后冻结。
- `clock_domain` 描述帧时间，主机接收时钟域单独存于 `timing.host_clock_domain`。SDK global 映射原始读数用于诊断，需另有曝光参考与误差界才能认可曝光时间。V 输出 `control_ready=false`。
- `VerificationEvidence` 的 `observation_refs` 保留 FSM 前帧与最终帧引用，`supporting_observation_refs` 保存额外稳定帧。缺帧的 UNKNOWN 允许主机时间为 null。

[V 线交接及 H0/H1/H4 样例](team/B/V_LINE_HANDOFF_20261110.md)
