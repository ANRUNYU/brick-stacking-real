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

## 最新补充：持物偏移与版本失效（第十三批，116 passed）

C2-02/M4-M5：`estimate_held_offset(training, validation, candidate_id=..., grasp_version=..., max_translation_residual_m=..., max_rotation_residual_rad=...)`，每行(sample_id,T_world_tcp,T_world_block)，各至少3样本，ID不重用，位姿在同一capture时刻/同一epoch时钟域。返回未批准RigidTransform和fit/validation一致性报告；不丢异常点，不自动修正。B方向未知时拒绝构造假姿态；A需提供图像时刻插值后的FK（插值误差另报告）。样例/验证：tests/unit/localization/test_held_offset.py。真实采样仍缺，尚无持物误差改善结论。

C2-04/M3-M6：`validate_plan_context(planned,current,created_stamp_s=...,expires_stamp_s=...,now_s=...)`。CONTEXT_KEYS列出13项设备/标定/工具/场景/时钟依赖；任何缺失或变化使计划失效，时间需同域。A/D需要在执行前调用并拒绝FAIL；它不代替实物身份、新鲜反馈、停止和全机碰撞校验，不生成permit。样例tests/unit/planning/test_context_validation.py。真实重装/夹持变更后仍须独立测点复验。

九项C任务最新完成度见TASK_STATUS.md；本批未连接设备，未有真实运动。最终交付仍需实际标定、M3/M5/M6证据，不能冻结为全部完成。

现场最新确认：机械臂已确认P7，不再重复索取型号；左肩第一轴旋转中心可见、无外壳遮挡，可开始物理安装尺寸核对。零位/轴正方向及相机安装仍独立未知。首先采肩部中心间距三次原始读数，名义约328mm只作厂家模型一致性检查，不作为已批准外参。

## 最新补充：用户实测安装确认、平台差异与路径串接（第十四批）

用户明确所有机械安装数值已实测与厂商一致，不再重复请求这些尺寸。记录calibration/installation/user_confirmed_vendor_geometry_20261107.json，清楚区分用户实测确认、厂商模型及未提供矩阵的相机/TCP关系。Rabokit五章已审阅，见RABOKIT_REVIEW.md：base_link位姿、冗余IK选解差异、理想仿真传感器时钟、整机/独立O6反馈通道不可混用。未启动平台或设备驱动。

C→A/D新增plan_pose_path：顺序TCP目标通过局部IK后生成从当前起点开始的明确关节轨迹，任一失败不提供部分可执行路径。A应保留插值/关节解，不能转位姿move_to后让控制器重新选肘部姿态却沿用碰撞报告。full_collision UNKNOWN、motion_enabled=false。最新全套119 passed；尚无真实完整碰撞/执行闭环验收。

## 最新补充：碰撞采样与轴向模型转换（第十五批）

A/C必读：厂家P7碰撞URDF与现场SDK的七轴axis全反，J2限位反号换序。不是尺寸不符；用户实测安装一致的记录不变。`q_vendor=-q_sdk`三组FK及全部限位变换吻合，但这仅是模型约定转换，不是重新电机校准。使用config/planning/p7_sdk_to_vendor_collision_candidate.json和JointConventionMap时严格核对两侧哈希，不可静默混用角度。当前现场SDK哈希已再次SSH核对。

C→D：sampled_capsule_check实现明确半径胶囊对平面/球/自碰撞的轨迹中间姿态检查；每个self排除需名称和原因，缺几何/半径/版本拒绝。碰撞FAIL，采样点无接触则完整status UNKNOWN，不能申请permit；输出覆盖、缺失、采样间隔与首个接触。它可作为evaluate_candidates的碰撞回调，UNKNOWN将拒绝选择。没有加载厂家网格、没有全机或连续认证。

厂家8个mesh引用及轴向差异证据见vendor_p7_collision_audit_C15.json和vendor_sdk_axis_mapping_C15.json。最新全套126 passed，现场只有源码/哈希读取，无设备动作。后续仍需解析mesh、工具/相机/持物/环境及接触约定。

## 最新补充：8份厂家STL的锁定和FK放置（第十六批）

已下载/解析P7左臂8份真实STL，URDF哈希固定，STL的Git LFS SHA256及长度全部校验；锁清单p7_collision_asset_lock_C16.json。git commit API证书失败未绕过验证，当前以内容hash锁版本。原文件在artifacts，不放入源码/SDK。

mesh_envelopes对每link全部三角顶点生成保守胶囊，urdf_capsules使用明确SDK→vendor角度映射把它们置于L_arm_root。实际网格接入synthetic短轨迹后首帧包络重叠FAIL；这不是实物碰撞结论，不能通过扩大安装排除来掩盖。padding0仅资产诊断，没有真实安全余量。模型范围仍缺手/相机/机身/持物/环境与连续检查。

复现：`python tools/fetch_p7_collision_assets.py <新资产目录>`，需网络；读取函数load_p7_capsule_envelopes(dir,padding_m=...)和MappedUrdfCapsules(...).at_source_q(q)。API用例tests/unit/planning/test_mesh_envelopes.py、test_urdf_capsules.py。C15显式映射配置必须匹配两侧hash。采样无接触status仍UNKNOWN，不允许申请真实permit。

第十六批最新全套131 passed；本批不需现场协助。后续自主继续几何后端改进，当前不申请真实执行。

## 最新补充：FCL已配置（第十七批）

主机/home/qwer/c_planning_venv已安装python-fcl0.7.0.11/numpy2.2.6/Cython3.3.1，主机基本sphere/triangle-mesh相交与距离assert、pip check通过；原控制/相机环境没改。Windows独立项目测试环境全套134 passed。重建见FCL_SETUP.md和requirements-linux-fcl.txt，依赖可选extra planning。

C→A/D：新增FclMeshChecker，真实厂家8mesh BVH的两个模型姿态均发现6pair表面相交（未排除安装接缝），报告p7_fcl_mesh_audit_C17.json。不是实物碰撞结论，也不是避碰通过；无接触仍UNKNOWN，需补体积包含、连续关节路径、手/相机/机身/持物/环境。默认模型符号映射与所有hash约束仍必须保留，不允许因FCL已安装放开动作。

## 最新补充：厂家接缝与连续表面判据（第十八批，138 passed）

7个相邻link接缝排除有厂家arm.mjcf原文依据及SHA256锁定，不是从碰撞结果猜测。配置p7_vendor_installation_seams.json，load_vendor_exclusions会拒绝来源变化/未审pair/重复。两个静态姿态在此模型规则下无非排除三角相交。

check_trajectory已接quintic关节路径→具名link变换→FCL，能检出中间姿态接触。50ms/58sample合成路径最小距离13.046mm，但连续速度界推算下界为负，仍UNKNOWN。细化20ms结果和条件式连续表面证据见p7_fcl_certificate_fine_C18.json。速度/间隙界方法见FCL_SETUP.md，不把FCL首尾刚体CCD当真实关节轨迹。full_collision UNKNOWN、motion_enabled=false不变；未覆盖手/相机/机身/持物/环境、体积包含和标定误差。

第十八批细化证据：142sample、最大gap19.967ms，固定基座/刚性臂mesh/明确接缝/所声明quintic下，连续表面距离下界约6.402mm，条件式continuous_surface PASS。它不覆盖完整实体/环境，不能等同full_collision PASS。复现沿用tools/audit_p7_fcl.py，追加`--vendor-exclusions <arm.mjcf> --exclusions-sha256 <配置锁定hash> --path --sample-dt-s .02`，报告必须新路径。fetch_p7_collision_assets已同时锁定该MJCF。

## 最新补充：O6独立模型覆盖（第十九批，144 passed）

D/C：新增具名rad主动关节→mimic展开→全部指节FK→FCL12mesh检查。5组URDF mimic与厂家XML equality系数匹配；默认URDF FK仍拒绝未解析mimic。12个具名安装接触排除有固定XML哈希来源，非任意去掉碰撞。两组SYNTHETIC弧度手势无非排除表面相交，status/full_collision仍UNKNOWN。

来源/关节模型范围见vendor_o6_audit_C19.json，资产锁o6_asset_lock_C19.json，FCL结果o6_fcl_C19.json。源为厂家候选，不是已读实际手关节，不把全0叫open。D仍需给实际preset版本、单位和显式6通道到模型rad映射，以及安装/适用对象信息。不能从URDF上下限猜raw归一化。

工具fetch_o6_collision_assets下载并hash锁定12OBJ及URDF/XML，audit_o6_fcl复现手内模型验证。尚未组合到P7臂路径，尚无手/相机/积木相互碰撞结论。本批SSH仅查资料文件，无设备访问。最新144 passed。

## 最新补充：组合模型和可审阅软件交付（第二十批，154 passed）

厂家正确配方p7_i1_o6_bimanual已找到，并锁commit d0224b8da58802fe7cb2e35dcc9771693c4543b6。现有臂/手URDF哈希与该提交一致。p7_o6_left_mount_candidate.json只记录左L8→掌根机械关系及来源，不是TCP。20mesh组合的两个固定synthetic手势与quintic臂路径已做FCL采样，无非排除相交；full_collision仍UNKNOWN，缺机身/相机/持物/环境。C18连续表面判据没有自动扩展到组合模型。

新增接近候选生成、兼容gap_m的十块槽位、TCP枢轴独立验证CLI和按来源/版本/人工分组的试验报告器。样例和运行入口见SOFTWARE_REVIEW.md；所有SYNTHETIC输入禁止转作真实配置。计数/误差工具不把Mock/ACK/人工计作自主真机成功。

下一现场采样要求见NEXT_FIELD_SESSION.md；不重复量安装尺寸。需要A提供无P7构造副作用的新鲜状态/时刻FK，B提供同步相机点，D提供实际预设映射；用户现场配合刚性指针/固定参考点（未安装未运动）。C所有候选仍不自动批准，任务未全验收。文档将随实际数据持续更新。

## 现场采样补充（第二十一批）

用户已确认指针固定且接触凹点，现有控制进程是右手，不使用/干预该进程。只被动监听左臂ID61…67约3秒，0接收、0发送，未改变接口/设备状态。证据left_passive_capture_C21.json，NO_FEEDBACK只描述窗口，不是故障判断。有效TCP样本0，不能凭接触条件生成标定。A需要提供新鲜左臂七轴状态出口；未启动P7对象，未发送任何控制帧。

## 状态入口核验（第二十二批，M2a）

用户提供两份历史运动脚本，SSH逐行审查及hash见LEFT_STATE_ACQUISITION.md。V1脚本实际漏左J1且包含右臂；V2脚本read_initial_state会发Rest，后续使能/5度运动/解除使能，未直接执行或import。不要让D调度器或B采集进程调用这些脚本作为无副作用状态API。

C已独立实现c_left_arm_readonly_probe.py：只允许can2左61…65的06读请求，不实例化SDK；66/67原始帧仅监听，不默认量化。主机实际5请求、0合格响应（2.254秒），未发送控制/使能/Rest/Flash写入。报告c-left-readonly-probe-1与原始证据left_readonly_capture_C22.json；完整状态和calibration_sample_valid均false，有效TCP样本0。

A→C仍需具名七轴rad值、逐轴时间/原始反馈、clock/epoch、设备/映射版本、新鲜度/跨轴时差、状态/故障；V2纯查询协议或已审核状态出口尚缺。公共ArmAdapter未变；诊断报告不是其可执行扩展。C→B/D目前没有新的有效TCP或外参，旧候选不可提升为approved。7项新增工具回归，全套161 passed；实机通信无应答独立记录，不作为测试通过。现场无需重测安装尺寸。
