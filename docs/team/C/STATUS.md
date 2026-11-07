# C 离线交付状态（2026-11-07）

远程 main 基线 1acbee0d51faf4d321a36d2cb105cfd9d6ee0fc5；独立克隆 .worktrees/c-calibration-planning，分支 codex/c-calibration-planning。未发现 AGENTS.md。保留原仓库与其他成员代码。已读取统一交付包指定九份资料。契约 v0.1 尚待 M0 冻结；以下为增量离线 API，不覆盖公共 Protocol。

|任务|已有且通过|本批补充|未实现/待实测|
|---|---|---|---|
|C1-01|TF 方向、单位、动态时刻与反投影测试|复用 RigidTransform|FK/关节模型、选侧安装待 A|
|C1-02|原有数学基础|点对求解、独立点误差、枢轴 TCP 平移、JSON 工具及拒绝测试|采集适配器、图像角点提取、现场采样|
|C1-03|无真机通过|采样方案|安装/头部/TCP 实标定全部待测|
|C1-04|无运动规划|固定方向笛卡尔路点、扫掠 AABB 诊断|IK/关节轨迹/全机碰撞/限位未知|
|C1-05|原有 Mock 执行流程|无真实联调|M2a/M3 待 A/B/D|
|C2-01|参数化槽位和支撑 DAG|复用既有实现|实测尺寸/释放接触模型|
|C2-02|无|T_world_tcp=T_world_block inverse(T_tcp_block)|真实偏移估计/有限修正|
|C2-03|无|路径障碍诊断|接近候选排序/IK/可达性|
|C2-04|无|独立验证点统计工具|M5/M6 整场证据|

## 使用与版本

在独立克隆根目录：`python -m pytest -q --basetemp=.test-tmp-final`。
CLI 使用 `PYTHONPATH=src`（PowerShell：`$env:PYTHONPATH='src'`）或 editable install 后运行：
`python tools/solve_calibration.py calibration/examples/synthetic_pairs.json calibration/candidate.json`。
输出拒绝覆盖既有文件，永远 approved=false/motion_enabled=false。误差单位 m；界面展示 mm 时乘 1000。不是手眼 AX=XB 求解器。点对要求同一物理点在两个坐标系中的独立坐标。

## 修改与验证记录

- C1-02 / M1：localization/calibration.py、tools/solve_calibration.py，新增点对刚体与枢轴 TCP 求解。源为合成点对，使用现有 RigidTransform。测试覆盖已知旋转平移、5mm 独立误差、退化/非有限数据、时钟/profile/epoch 和样本泄漏拒绝。
- C2-02 / M4：同模块持物偏移反解，测试 0.1m 偏移方向。不是实测估计结果。
- C1-04 / M1：planning/cartesian_diagnostics.py 提供固定朝向路点和连续平移 AABB 检查；可检出端点之间障碍。仅给定工具/持物包络对已提供静态障碍，不检查整臂，不产生关节轨迹、IK 结果或安全许可。接触面未建模时相交按失败，不自动豁免。
- 基线 53 passed；第一批 61 passed，最终结果见本次验证记录。全部 synthetic/mock；无硬件动作、无 SDK 修改。

## 交接与采样请求

|方向/合并点|最小输入与调用|验证与缺项|
|---|---|---|
|A→C M0/M2a|JointState 需关节名 J1…J7、q_rad、sample_id、host_receive_stamp_s、clock_domain、epoch、source；控制限值和映射版本单独提供|现有 ArmAdapter 仅 tuple，不能推断时间和身份；请 A 增量适配。没有新鲜反馈不做真实规划|
|B→C M1/M2a|synthetic_pairs.json 是点对数据完整样例；每点附 profile、host_stamp_s、clock_domain、epoch|真实采样补原图索引、K/D、尺度、配准、时间映射误差和设备 SN；profile 不同拒绝|
|D→C M1/M4|world_pick/world_place 为现有 RigidTransform；tcp_block 为 TCP→物体关系；scene_version、clearance_m、half_extent_m 和 obstacles 显式传入 offline_pick_place|全部几何单位 m，禁止用抓握预设名称猜手部包络；当前仅固定方向单臂诊断|
|C→A M1/M2a|当前不产生关节轨迹；A 不得执行笛卡尔路点|待 A 提供限位/模型后，输出将含 joint_names、time_from_start_s、positions_rad、预期起点、模型版本。当前 IK UNKNOWN，joint_trajectory NOT_GENERATED|
|C→D M1/M4|offline_pick_place 返回分段位置、scene_version、碰撞局部结果和缺失项|mock 使用；不得将 collision_aabb PASS 转为可执行 PlanResult；真实有效期/标定版本未知，拒绝执行|

现场方案：先由全员选择主臂；A 提供固定时刻的 T_base_flange 和物理关节映射/零位来源，B 提供已配准头部 RGB-D 与时间映射，D 提供工具和持物几何。头部点对覆盖多个 XY 区域及高度，至少 4 个非共线训练点和 4 个独立验证点，建议更多点并重复采样；ID 不重用。TCP 枢轴需至少 4 个绕不同轴的姿态，独立接触点复核平移；方向另行量测。工具求解并不验证物理接触成立。

验收阈值须在采样前由团队冻结：XY/Z、姿态、P95/max、时间偏差、停止行为。未给阈值不批准。改变相机安装/TCP/夹持方式后旧版本失效，重采独立点。主臂、J6/J7、限位、安全停止、另一臂停放仍待实测。现场开流/采样和任何动作均需单独现场授权；本批未连接设备。

## 统一交付包

尚未上传：包内含设备序列号、内网地址与原始 terminal evidence，需完成逐文件公开内容审查后才能判定“没有问题”。本分支不把整个包覆盖进代码根目录。原始资料路径与 SHA256SUMS 保留在用户提供的交付目录。远程上传仅针对后续审查通过的交付资料，不包含本批未审查开发代码；本次未推送或合并。

最终验证：`python -m pytest -q --basetemp=.test-tmp-final`：63 passed（53 基线 + 10 新增）。CLI 合成点对样例实际运行成功；第一次样例生成因 PYTHONPATH 未设置失败，设置 src 后重跑通过。`git diff --check` 通过。输出候选不属于 approved 目录。全部验证来源 synthetic/mock，不是实机记录。

## 第二批：C1-01 / C1-04 / C1-05 离线增量

### 身份绑定修正（用户现场补充）

can0/can1 可能随启动/插拔变化；旧审计映射只是 2026-11-07 的快照。禁止把总线编号当左右手身份。A/D 以设备唯一身份读取结果和物理路径解析当前绑定，记录 binding_version、SN、bus、核验时刻和来源，未知/重复/不一致时拒绝动作。C 不新增 CAN 探测/发送代码。本批检查 C 新增源文件，无 can0/can1 固定角色逻辑。设备映射变化不意味着相机/TCP 已重验。

### 实现与接收方适配

- C1-01 / M1：localization/forward_kinematics.py，RevoluteJoint(name, origin, axis_xyz) 复用 RigidTransform。origin 是零角度 T_parent_joint；轴在该关节系，位置输入必须按名字完整匹配，单位 rad。返回 T_base_last_joint，TCP 需另外显式 compose。通用数学实现通过，不代表实际 P7 FK 通过。需 A 给所选侧 URDF/关节原点/轴、零位和映射版本后核对；未读取远端 SDK 或控制设备。
- C1-04 / M1：planning/joint_trajectory.py，JointLimits 要求逐关节上下限、速度/加速度、模型版本与来源；无默认值。build_offline_trajectory 要求起点、场景/标定、时钟/epoch 和状态时间/新鲜度。生成分段五次多项式，每路点速度和加速度归零，解析峰值决定时间。仅支持这些分段的插值；不能改为厂商默认插值后沿用本校验结果。
- C1-05 / M2a：tools/c_motion_sample.py 给 A/D 七轴合成样例。运行：设置 PYTHONPATH=src 后 `python tools/c_motion_sample.py output.json`。输出文件不得已存在。所有限值、起点和版本均为 SYNTHETIC，不可用于真实机器人。样例不提供虚构执行成功反馈。
- C→A：schema c-trajectory-1 输出 joint_names、expected_start_rad、segments(start_rad/end_rad/start_s/duration_s)、插值、模型/场景/标定版本和时钟域/epoch。sample_segment 求 q/dq/ddq。相对时间从 0 起；适配器应在执行前重新读取状态并核验全部上下文，不能用样例时间或单纯 tuple 反馈代替。现有 ArmAdapter 不变，不新增 execute 方法。
- C→D：trajectory_limits PASS 仅表示所提供关节路点的五次插值符合所提供数值限制。ik NOT_CHECKED、full_collision UNKNOWN、motion_enabled=false。没有真实有效期、设备绑定和完整碰撞证据，不得申请执行许可。

### 验证与剩余依赖

`python -m pytest -q --basetemp=.test-tmp-fk`：81 passed（本批新增 18 项）；`python tools/c_motion_sample.py .test-seven-axis.json` 已实际生成七轴样例。轨迹测试覆盖端点 q、零速度/加速度、1001 点速率抽检、未来/过期状态、缺失限位、位置越界和起点不一致。FK 用可手算两连杆 90°/-90° 位置 [1,1,0] 验证，以及轴、帧链和关节映射拒绝测试。来源全部 synthetic/mock；无真实硬件动作。

状态修订：C1-01 的通用 FK 已补充并通过；实际关节模型仍待测。C1-04 的关节路点时间参数化已补充；尚未实现笛卡尔 IK、规划器联接和全机碰撞。C1-05 仅有可调用轨迹样例，尚未与 A 执行反馈联调。C2-01/03 和实测标定不因上述数学通过而完成。

需 A：所选臂模型版本、J1…J7 到实际 ID 的核验映射、零位、限位/速率来源、新鲜状态及 epoch；需 B：同步/配准采样与独立物理验证点；需 D：工具/相机/持物包络、碰撞场景版本和接触约定。真实安全停止、J6/J7、主臂选择仍未知。本批不依赖 SSH，不连接或开流。

## 第三批：真实头部相机预检（C1-02/C1-03，未批准标定）

2026-11-07 15:26（Asia/Shanghai），用户确认主臂左臂、本人现场在位、J6/J7 与停止已验收、头部无人占用；该信息来源为用户陈述，尚未关联 A 的验收日志。无标定板或已知尺寸参考点。

通过 SSH 实际执行已审阅的 /home/qwer/orbbec_camera_probe.py：普通 qwer 两次尝试因枚举序列号为空/USB 打开失败而拒绝。第三次仅临时 sudo 相机采集，指定 SN CP2L863000KL 和当次 UID 2-3.4.3-61，10 帧、最长20秒、skew阈值20ms（仅采集阈值，不是验收门槛）。未修改权限、SDK 或设备持久参数，未访问CAN或运动。已退出，cleanup_errors为空。

结果 CAPTURED：RGB/Y16 640×480 15fps、深度尺度1mm、帧间 RGB/depth skew 最大约0.019ms；设备时间覆盖0.600624s，不是主机同步结果。每帧有效深度91.3%—91.7%。SDK执行D2C和去畸变不等于配准精度验收；输出 metadata registered=true 只表示处理流程。

原始数据本地 artifacts/c_real_calibration/head_precheck_20261107_C03，远端 /home/qwer/c_calibration_runs/head_precheck_20261107_C03。原始图像不纳入Git。可版本化报告见 evidence/head_precheck_20261107_C03.json 和 head_precheck_analysis.json，后者记录每帧SHA256。预览可见桌面和积木。

新增 tools/analyze_calibration_capture.py，实际运行命令：
`python tools/analyze_calibration_capture.py artifacts/c_real_calibration/head_precheck_20261107_C03 artifacts/c_real_calibration/head_precheck_analysis.json`。
输出全帧持续有效像素89.92%；全图时间标准差中位4.73mm、P95 82.22mm。它包括背景/边缘/场景运动，不能作为绝对精度、桌面ROI精度或外参误差。无地面真值，accuracy UNKNOWN，外参/TCP仍未知。真实采集完成，不等于 C1-03 完成。

现场下一步：用户准备平整棋盘格并实测格长、尺/卡尺，或提供已知尺寸平面参考物；固定标定板，采集工作区不同位置/高度的样本，保留独立验证点。相机到table可先独立标定；table到左臂base仍需可测几何约束和A的已验收模型/零位/安装数据。缺少这些不能用桌面平面自行确定XY原点，更不能生成有效世界到机械臂外参。任何自动运动另列具体路径和现场检查，当前没有运动授权实现。

## 第四批：50mm实测立方体真实采样（C1-02/C1-03）

用户确认块为尺量50×50×50mm，测量工具精度未知；桌面约100×40cm，不作为标定真值。用户将一块红块独立放在桌面中央后采集。主臂不运动。

2026-11-07 15:30（Asia/Shanghai）真实头部采20帧，640×480 15fps，实际设备时长1.267984s，RGB/depth skew约0.019ms，CAPTURED且cleanup_errors为空。普通用户权限未修，临时sudo运行已审查相机探针，无CAN/臂/手调用。源为 /home/qwer/c_calibration_runs/single_cube_20261107_C04，本地 artifacts/c_real_calibration/single_cube_20261107_C04。

新增 tools/analyze_cube_capture.py 复用 backproject 和 fit_table_plane；手选顶面内部腐蚀3px、邻近桌面ROI去除积木，桌面像素棋盘拆分训练/验证。RANSAC 8mm 为分析参数，不是验收容差；法向朝向相机，仅决定高度符号，不确定世界坐标。

运行（PYTHONPATH=src）：
`python tools/analyze_cube_capture.py artifacts/c_real_calibration/single_cube_20261107_C04 docs/team/C/evidence/single_cube_C04_roi.json output.json`

最终结果：高度中位50.54mm、范围50.10—50.71mm、高度时间标准差0.151mm；顶面像素深度时间标准差中位0.497mm，桌面0.592mm。相对尺量50mm高度差约+0.54mm。以上是同一静态位置约1.27秒的重复性，不能当绝对精度保证。

首版原图手选角点估计边长40—42mm；放大8倍按可见面交界重新选角点后为47.28、48.85、42.75、47.17mm，与50mm仍有明显差异。不以50mm反调深度尺度、内参或角点。两版原始分析均保留在artifacts，最终ROI与结果纳入 evidence。尺寸校验未通过预定验收（尚无冻结阈值），状态 INCONCLUSIVE：低分辨率角点、配准、顶面平行假设及系统偏差需要进一步分辨。像素留出同源，不能替代外部真值验证。

camera_report、每帧SHA256、ROI与逐帧分析均保存在 docs/team/C/evidence/single_cube_C04_*。原始图像仍不纳入Git。`python -m pytest -q --basetemp=.test-tmp-c04`：81 passed；新增工具已在20帧真实数据上运行。C1-03仍未完成，不输出相机→臂外参或TCP，无动作许可。下一步需要多个工作区位置的同块重复采样，评估视角/分辨率/深度偏差；完整外参仍需与左臂基座关联的物理参考点或标定板，不能仅靠立方体尺寸求解。

## 第五批：第二位置真实采样与角点敏感性（C1-02/C1-03）

2026-11-07 15:42（Asia/Shanghai），用户平移同一实测50mm块后确认放好。具体平移距离/方向未量测，不能当已知10cm位移约束。画面中块位置和朝向发生变化。采集C05：20帧，头部SN/配置不变，设备跨度1.267984s，skew最大0.019ms，CAPTURED、无cleanup错误。独立时钟epoch，不跨会话拼接设备时间。临时sudo仅相机开流/停止，无CAN/机器人动作。

复用analyze_cube_capture；新ROI见 evidence/single_cube_C05_roi.json，手选可见顶面交界，无以50mm调角点。结果：高度中位49.985mm、范围49.679—50.436mm、时间标准差0.181mm；顶面像素深度时间标准差中位0.572mm、桌面0.600mm。与C04高度中位50.545mm相差-0.559mm。桌面空间留出绝对残差P95逐帧中位约3.56mm。两位置的近50mm高度只是局部几何一致性证据，不证明全工作区绝对精度。

边长中位48.59/41.86/50.80/44.90mm，未收敛为尺量50mm。工具新增每边两端角点各坐标±1px的16种组合敏感性；第一帧四边范围41.59—55.60、35.41—48.44、44.01—57.62、38.53—51.32mm。这不是统计置信区间，且不包含配准/深度/平面假设偏差。像素分辨率和手选角点不足以据此验收边长；不能把所有差异归因于像素误差或反向调整尺度。

运行真实工具：
`python tools/analyze_cube_capture.py artifacts/c_real_calibration/single_cube_20261107_C05 docs/team/C/evidence/single_cube_C05_roi.json output.json`（PYTHONPATH=src）。
`python tools/analyze_calibration_capture.py artifacts/c_real_calibration/single_cube_20261107_C05 output_capture.json`。
结果、每帧SHA256与采集报告已保存 evidence/single_cube_C05_*；原始图像/深度留artifacts和远端，不提交Git。
`python -m pytest -q --basetemp=.test-tmp-c05`：81 passed。新增敏感性计算已对本轮真实20帧运行，不宣称单独新增回归覆盖。

下一实验优先核对设备支持的更高分辨率profile，并按对应K/D重新采集而非插值放大。若提高分辨率仍有不一致，需使用标定板/独立量测验证空间配准和形状。当前停止重复相同低分辨率位置采样作为验收；外参/TCP及运动许可仍未知。

## 第六批：335L高分辨率profile实机枚举（C1-02）

用户指出视角改变像素尺寸；确认这一点，并区分像素外观与透视修正后的三维边长。C04/C05使用RGB手选角点射线与局部平行平面求交，不是直接比较像素宽度；其假设与角点误差未独立验证，不能把差异简单归因于分辨率或视角。

官方Gemini330系列Datasheet V1.6列335L/336L RGB及深度1280×800模式：https://www.orbbec.com/wp-content/uploads/2025/06/Gemini-330-series-Datasheet-V1.6.pdf 。厂商商店页面摘要/表格存在不一致，因此以设备实际枚举为准，不混淆335和335L。

通过SSH临时sudo仅创建SDK Context和Pipeline并查询stream profile list（未start、未开流、无CAN或动作）；严格按SN CP2L863000KL打开。实机输出包含：
- COLOR 1280×800 RGB：30/15/10/5fps；MJPG也有60fps。
- DEPTH 1280×800 Y16：30/15/10/5fps。
- 两者也列出1280×720等模式。仅枚举不证明任意组合开流成功、配准精度或性能达标。

首次远程命令因Windows引号转义SyntaxError未查询设备；改为准确传递同一只读Python代码后成功exit0。未修改SDK或持久参数。

下一采样候选为RGB+Y16 1280×800@15fps，需显式选择profile并分别读出对应K/D，验证D2C输出/时间戳和深度单位；不得复用640×480内参、ROI或直接缩放旧图冒充高分辨率。1280×800的纵横比/视场也可能变化，不能承诺物体像素数恰好翻倍。本批只确认配置支持，尚未高分辨率采集。

## 第七批：1280×800@15高分辨率真实采集（C1-02/C1-03）

2026-11-07 15:58（Asia/Shanghai）。用户授权更好的配置，头部SN CP2L863000KL，20帧、最长20秒。新建 tools/c_head_camera_probe.py，来源为已审阅的主机 /home/qwer/orbbec_camera_probe.py，保留采集/清理流程，改为严格1280×800@15，格式优先RGB/Y16，缺模式报错不降级；增加接收时刻host_monotonic字段，不将其写成设备时钟。无SDK修改。副本部署 /home/qwer/c_head_camera_probe_1280_v1.py，未覆盖原工具。

部署前后SHA256均b719e5f495cf10e18fdf2c8ac05112711ea0449aab0ab0479d658345d6a66e83。首次SCP连接被远端关闭，重试成功并核对哈希。临时sudo仅运行相机工具，真实CAPTURED、cleanup_errors为空，无CAN/臂/手动作，相机已停止。

实际报告RGB+Y16均1280×800@15fps；K焦距fx609.669/fy609.770px（不能使用旧368px内参），按当前profile读D并执行D2C/去畸变。20帧设备跨度2.802912s，有效保存速率约6.78fps（不是设备实际输出帧率测定），不能声称15fps稳定接收。主机接收跨度3.454330s；相对间隔累计差约0.651418s，仅提示接收/处理积压或调度变化，未建立设备到主机时间映射，不据此计算绝对延迟。首尾host接收定义为wait_for_frames返回后，尚无transport时戳。

新ROI由原生高分图独立选取，不放大旧图冒充新采集。分析结果：局部高度中位50.831mm、范围50.368—51.171mm、时间标准差0.206mm；顶面像素时间标准差中位0.539mm、桌面0.622mm。手选角点边长中位46.423/46.658/45.825/47.185mm，四边较一致但相对尺量50mm仍偏低2.8—4.2mm。第一帧角点各坐标±1px边长范围约42.16—50.67、42.61—50.70、41.66—49.97、43.27—51.09mm。这些是敏感性范围而非置信区间；不能据此断言角点误差解释全部尺寸差异。

与C05相比，视场/ROI/profile改变，且两会话间没有外部固定位置证明，比较只作诊断，不作为受控精度改进验收。高分辨率降低单像素尺寸敏感性，但完整标定仍未知。外参/TCP不生成，motion_enabled=false。

运行：`python tools/c_head_camera_probe.py --capture --serial CP2L863000KL --uid <当次核验UID> --frames 20 --seconds 20 --output <新目录>`（现场先确认相机无人占用；本机工具需Linux相机环境）。source real原始数据在远端 /home/qwer/c_calibration_runs/single_cube_1280_20261107_C06、本地 artifacts/c_real_calibration/single_cube_1280_20261107_C06。报告、ROI、每帧SHA256与分析见 evidence/single_cube_C06_*。原始图像不提交Git。

测试：新增精确profile/缺模式拒绝回归，全部83 passed。analyze_cube_capture和analyze_calibration_capture在实际20帧运行成功；后者补有效保存速率和设备帧间隔，不把配置帧率当实际吞吐。

后续先保留此配置为静态诊断候选；生产配置尚未冻结。需定位采集链吞吐、独立验证RGB-D配准/角点/顶面假设，并取得与左臂base关联的物理参考约束。仅提高分辨率不代替外参/TCP标定。
