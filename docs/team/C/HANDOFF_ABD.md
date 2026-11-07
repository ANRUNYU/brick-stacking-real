# C → A/B/D 滚动交接文档

更新：2026-11-07；本地分支 codex/c-calibration-planning。维护约定：每个可合并任务同时更新本页和 STATUS.md，并将新证据加入 evidence/。最终交接从本页进入；尚未发送给其他成员、未推送/合并。本文是滚动交接，不是全部任务完成声明。

## 当前统一事实

主臂左臂，由用户现场指定；左臂固定在整机，交付时已安装，没有安装记录。用户现场确认J6/J7及停止已验收，但A的量化日志尚未接入。左臂61–67的顺序有现场SDK源码支持，物理正方向/零位待核验。can0/can1只是当次接口名，不能固定绑定左右手；A/D须按SN/唯一身份和物理路径解析当次总线。

头部Gemini335L/CP2L863000KL，左腕Gemini2/AY6M8630086，右腕Gemini2/AY6M86300GH。腕相机角色源于交付审计，本批没有对腕机开流。头部使用1280×800 RGB/Y16@15候选配置，真实有界采集成功。普通qwer USB访问失败，临时sudo才成功；未修改udev/用户组/SDK，生产权限问题未解决。

积木50×50×50mm为用户尺量，测量不确定度未知；桌面约100×40cm，不是精确外参约束。所有几何m、角度rad、四元数xyzw，T_A_B将B映射至A。设备时钟/host_monotonic分开记录，epoch按会话变化，没有设备到主机/ROS时间映射。当前无已批准外参、TCP或真实动作计划。

## A：机械臂/执行交接（M0/M1/M2a/M3/M5/M6）

现场源码p7.py声明：左motor_ids61..67顺序L1..L7；前5轴A7Motor、后2轴MotorV2。P7构造器含模式/Flash相关调用，不得为了read_state实例化。详见STATUS第十批与 remote_sdk_coordinate_audit_C10.json 中源码哈希。

ArmKinetix有urdf/maestro两种约定；maestro除位置原点/旋转外还有输出姿态右乘，不能当单一项目world变换。默认tcp_offset=0是源码缺省，不是TCP标定。get_angles为缓存字段，不证明新鲜。必须提供带sample_id、关节名、q_rad、host_receive_stamp、device_stamp或null、clock_domain、epoch、有效性、模型/映射/限位版本的反馈。

现场p7__left.urdf的SHA256为233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce；主机Pinocchio三组数学输入与C解析FK最大矩阵差0，见remote_left_p7_fk_C10.json。无collision元素，无手/相机/整机模型，不能用来宣称全机避碰。实际安装/零位/正方向仍未知。

C输出c-trajectory-1：joint_names、expected_start_rad、segments(start_rad/end_rad/start_s/duration_s)、五次插值、模型/场景/标定版本、clock_domain/epoch及state_stamp。插值在每路点速度/加速度归零，A不可替换成另一插值后沿用限制检查。样例：`PYTHONPATH=src python tools/c_motion_sample.py <新输出.json>`；全部SYNTHETIC。接收方需验证许可、设备身份、新鲜起点、实测限位/速率/停止能力。当前motion_enabled始终false。M3/M5/M6真实联调尚未进行。

## B：相机/标定交接（M0/M1/M2a/M3/M4/M6）

真实C08/C09核验对齐帧profile：RGB与depth的K一致，但RGB畸变非零、aligned depth畸变全零。原工具两流共用RGB remap不符合帧声明；C03–C08保留诊断，禁止批准标定。v4按各自D处理到共同K，对齐帧K/尺寸不符则拒绝。C09是修复后记录；SDK执行D2C不等于空间配准精度验收。

tools/c_head_camera_probe.py为独立副本，未改原SDK；真实使用v4部署哈希见STATUS第九批。20帧/最长20秒，明确SN和profile，不自动降级；RAM有界缓冲，停流后压缩保存，不是长时录包器。缓存映射/后移写盘后C07/C09保存约14.98fps，之前C06仅6.78fps。短采样连续不证明长期性能。

高分模式K约fx609.669/fy609.770，不用旧640×480的368px K。report含profile/K/D、时间域、SN、深度scale；NPZ含rgb/depth_m/k/metadata。B需继续提供原始depth尺度、空间处理依据、时间映射与延迟、profile版本、图像索引；不要把device stamp作为host stamp。

修复后C09局部高度中位50.324mm、短时std0.168mm，手选角点边长45.920–47.229mm，仍与尺量50mm不符。只作诊断，不反向调scale/K以对齐真值。tools/analyze_cube_capture.py记录ROI、平面/角点假设和敏感性；独立顶面拟合也不能替代外部标定板/量测。外参点对求解见tools/solve_calibration.py和calibration/examples/synthetic_pairs.json，训练与验证ID分离，输出永远未批准。

## D：任务/手/场景交接（M0/M1/M3/M4/M5/M6）

D拥有block/slot及支撑唯一状态。C复用scene.build_stacking_slots与Slot，不重建场景或调度器。真实尺寸输入edge_m=.05仍须带来源；table到world必须明确，近似桌面尺寸不用于标定。

新增slot_release_geometry：Slot、T_world_table、T_tcp_block、yaw_rad、clearance_m、scene_version → world_block及approach/release/retreat TCP变换。撤退方向沿table +Z，不假定world +Z；版本/坐标不符拒绝。样例与10块四层测试见tests/unit/planning/test_slot_release.py；支撑DAG仍由既有生成器维护，不额外创建并发/双臂功能。

新增evaluate_candidates：注入solve_ik(candidate)和check_collision(trajectory)，各候选分别报告IK/trajectory_limits/collision/full_collision。回调IK None视为无解；碰撞未知/失败、版本不符、过期状态或越限拒绝选择；只在所提供模型内通过者按总时长排序。输出schema c-candidates-1，包含候选原因、分段轨迹、模型/场景/标定版本。full_collision仍UNKNOWN、motion_enabled=false。测试中的IK/碰撞回调是SYNTHETIC，不是已经实现真实IK/碰撞规划器。

D需提供手角色/SN/预设/版本/单位、实测手与相机/持物包络、场景版本、允许接触模型、目标block/slot及支撑状态。手预设不能默认映射到已知TCP。AABB-only通过不得生成真实permit。当前没有真实执行结果，不得由规划通过提交PLACED_VERIFIED。

## 所有成员共同的未完成依赖

|依赖|提供方|最小证据/单位|完成前行为|
|---|---|---|---|
|关节零位/正方向/限制/停止|A|七轴映射、rad/rad_s/rad_s2、时间/epoch、验收run_id|不生成真实轨迹许可|
|头部/桌面/左臂base约束|C+现场/厂家|基座物理原点/轴，安装图或独立量测点，m、来源/时间；分离验证点|外参未知|
|TCP/工具/持物偏移|C+D+A|刚性工具几何、多姿态采样、独立接触验证；TCP方向另测|不以零偏移默认通过|
|RGB-D绝对精度/配准|B+C|标定板或可测参考，跨位置/高度，K/D/profile、原图和时间域|尺寸验收INCONCLUSIVE|
|全机碰撞|A/C/D|臂/手/相机/机身/桌面/另一臂停放几何、验证方法与缺失|full_collision UNKNOWN|
|真实阶段一与多层验收|全员|M3固定点→视觉；M5两层→十块；M6多轮与人工介入记录|不宣称阶段完成|

## 证据与复验入口

STATUS.md保存每批任务ID、文件原因、输入版本、测试、现场动作边界和依赖。evidence/保存哈希/报告/ROI；原始RGB-D在主机/home/qwer/c_calibration_runs和本地artifacts/c_real_calibration，不纳入Git。数学参考不标real joint feedback。工具/夹持/相机安装改变后标定需失效重验；原报告不可静默覆盖。

本批最新全套：`python -m pytest -q --basetemp=.test-tmp-c11-final`，91 passed。只证明对应软件/Mock用例；真实验收见逐批记录。所有C任务尚未全部完成，本页将随进展更新，最终交付时再冻结版本。

## 最新补充：厂家资产与IK（第十二批）

厂家P7组件可提供机身/肩部候选基准：base_link到左肩mount的声明平移(0,.164,0)m，L8_Link为tool0；源称A7V2_50_4.27。torso_root离地1.2m是仿真设置，不是实测。厂家腕部335L/顶部ZED装配与现场头335L/腕Gemini2不同，禁止套用其相机安装外参。来源链接、未锁定commit及读取网络失败均记录在STATUS第十二批。

新增solve_pose_ik为C1-04/C2-03的数值后端：显式求解参数，返回c-ik-1，局部失败不宣称全局不可达，collision UNKNOWN、trajectory NOT_GENERATED。用户明确批准单文件上传后，已在主机Pinocchio完成两组数学验证，见remote_pinocchio_ik_C12.json；不调用P7、不访问CAN，数值残差不是实机精度。最近全套95 passed。

用户具备毫米刻度直尺/卷尺，外廓复量仍50mm；顶面平整区域/倒角/重复测量未给，保持未知。installation_survey.json已准备，记录物理基准、操作者/时间和量具分辨率；未知外参/TCP为null。A/B/D后续统一从此页及STATUS读取最新证据，旧采样不能绕过逐流畸变修复限制。尚未向成员发送，最终交付前冻结。
