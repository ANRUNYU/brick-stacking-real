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

## 第八批：分离写盘后的真实吞吐验证与独立顶面拟合（C1-02/C1-03）

2026-11-07 16:05（Asia/Shanghai）。主机独立工具 /home/qwer/c_head_camera_probe_1280_v2.py，部署前后SHA256一致：1c2321899ee7f590ccb4739dc828eaa881d58bc0dc6b5e97f7b654eecb688706。配置1280×800 RGB/Y16 @15fps，头部CP2L863000KL，20帧最长20s，仅临时sudo相机访问，无CAN、手、臂动作。CAPTURED，无cleanup错误，pipe.stop完成后才压缩/写盘。此哈希对应现场部署版本；以后本地改动应重新计算再部署。

实现：tools/c_head_camera_probe.py缓存去畸变映射（按尺寸/K/D键），有限帧数复制后的RGB/深度在RAM缓冲，停止pipeline后写NPZ及预览。最大50帧上限延用，不是长时录包器。每帧记录wait/align/decode_depth/rectify耗时。保存失败应返回ERROR而不冒充完整录包；本轮真实保存成功。源程序和SDK未覆盖。

实测C07保存速率14.9844fps（上一版本C06约6.7787fps），20帧设备时间跨度1.267983s，帧间隔66.735—66.737ms。本样本没有时间戳缺口，不推断长期零丢帧。host span-device span差约1.205ms，仅同会话相对间隔，不是绝对延迟/时钟标定。配准耗时中位15.025ms、decode/depth2.900ms、rectify2.633ms，wait42.022ms。停流后压缩写盘3.120s。因同时后移写盘/预览并缓存映射，仅能判定组合改动改善本轮短采集，不能给各因素独立因果贡献。

几何：预览核对块仍在同一画面位置，复用C06明确ROI，不承诺现场绝对未动。高度中位50.791mm，范围50.507—51.046mm，时间标准差0.139mm。顶面/桌面像素时间标准差中位0.477/0.589mm。新增独立顶面SVD平面（不强制平行桌面），法向夹角逐帧中位0.988°，顶面平面残差RMS中位0.972mm；独立顶面求交的边长中位46.331/46.469/45.748/47.021mm，仍偏低。没有按50mm改尺度、角点或K；法向差异不能排除局部深度偏差、配准和边界定义问题。完整外参/TCP仍未知。

运行同前：c_head_camera_probe、analyze_cube_capture（ROI使用single_cube_C06_roi.json）、analyze_calibration_capture。记录源 real，原始RGB-D远端 /home/qwer/c_calibration_runs/single_cube_1280_20261107_C07，本地artifacts同名；报告和每帧SHA256见evidence/single_cube_C07_*。所有图像仍不进Git。

验证：84 passed（新增缓存结果等价、深度NaN保留、K变化不复用旧映射的回归）。真实20帧通过分离计时/几何工具；尚未对真实相机做长时/运动验收。下一步需要独立物理参考或标定板确认RGB-D空间误差；单一已知尺寸方块不建立相机到左臂base关系。实际标定采样仍需左臂模型/安装关系、基座可测参考点和现场协作。

## 第九批：逐流畸变修复与现场URDF接入（C1-01/C1-02/C1-03）

用户现场补充：左臂固定在整机上，交付时已安装，没有安装记录。不能据此推断L_arm_root相对头部/身体/桌面的变换。主机只读find找到p7__left.urdf，原SDK未修改，未构造Arm/O6对象。文件取回artifacts/c_real_calibration/robot_models，原模型不提交Git。

### URDF适配

新增localization/urdf_chain.py，复用hardware.inspect_urdf、RevoluteJoint/forward_kinematics和RigidTransform；只解析固定/转动关节明确的base→tip链，拒绝mimic/未知类型、重复父节点、断链及不完整q映射，不猜J1→L1_Joint/ID对应。示例：
`urdf_forward_kinematics(path, {f'L{i}_Joint': 0.0 for i in range(1,8)}, base_frame='L_arm_root', tip_frame='L8_Link')`。

现场文件是7个revolute+1个fixed，声明零角度末端平移[-0.000001582,0.058,-0.6082]m，与逐段原点独立累加相符。首次手算预期Z误写-0.7082，断言失败，核对原文逐项加总后修正预期为-0.6082，不修改模型来通过。审计含原文件SHA256，见evidence/left_p7_declared_model_audit.json。模型无collision元素、无手/相机/全机几何，不能执行完整碰撞检查；URDF限位/速度只是声明，不能直接成为已验收实机限制。q=0测试不是回零命令，也不是实机零位证据。

### C08真实帧几何核验与修复

2026-11-07 16:13，v3独立工具采3帧，strict SN CP2L863000KL、1280×800@15，CAPTURED无cleanup错误（原记录在主机 /home/qwer/c_calibration_runs/head_frame_geometry_20261107_C08）。逐帧读取对齐后color/depth各自profile：二者K/尺寸一致，但RGB畸变非零，aligned depth畸变全零。旧工具用RGB映射同时remap两流，因此与帧声明不一致；此前C03—C07和C08输出保留为诊断，禁止作为标定批准数据。并不声称此问题解释全部尺寸偏差。

v4修复：每流按各自frame profile畸变映射到共同K，零畸变depth复制而不再次RGB remap；缓存按各自K/D；对齐帧K/尺寸与所用K不同则拒绝。保留旧helper缺省参数仅用于既有离线调用；真实capture显式传depth参数。工厂参数与软件处理仍不代替实测空间配准验收。参考厂商SDK逐帧profile获取接口文档：https://orbbec.github.io/pyorbbecsdk/source/5_Application_Guide/ApplicationGuide.html 。

### C09真实修复验证

2026-11-07 16:15，远端独立副本 /home/qwer/c_head_camera_probe_1280_v4.py，部署与本地SHA256一致60e3b1b0210d41a84529f404ec2ae4500beb42766f8b6aca55f8760d021d2ce9。临时sudo只运行相机，20帧、最长20s、1280×800@15、SN核验，CAPTURED无cleanup错误。有效保存14.9844fps，间隔66.735—66.737ms，skew最大0.021ms。停流后写盘，已退出，无CAN/手/臂动作。

图像核对块仍在ROI范围，使用明确C06手选ROI，仅诊断对照：高度中位50.324mm、范围50.055—50.659mm、时间std0.168mm；四边46.528/46.716/45.920/47.229mm，仍偏低。高度与C07变化不能全部归因修复（非同步对照、存在传感器变化），边长问题仍待独立验证。无外参/TCP输出，无motion许可。

原始数据本地artifacts/c_real_calibration/single_cube_1280_20261107_C09、远端同名目录；evidence/single_cube_C09_*保存报告/每帧SHA256/分析，包含真实逐流K/D。原图不纳入Git。工具运行命令沿用上一批，c_head_camera_probe为v4。测试86 passed：新增逐流畸变不混用的回归及URDF固定末端/RPY/断链/映射测试。真实3帧核验和20帧修复后重采均成功。

剩余依赖明确：A需核验所选左臂URDF到真实关节名、正方向、零位、限位及base原点定义；C需以可重复识别的物理基准测量base→相机/桌面，或用已标定刚性指针及受控多姿态采样建立点对；D需实际工具/TCP几何。没有安装记录时先建立测量基准，不用躯干外壳/桌面近似尺寸或单块尺寸代替未知基座变换。实体标记/指针安装及任何机器人运动须先确定具体方案与现场授权。

## 第十批：SSH现场坐标链与SDK行为确认（C1-01/C1-03/M0-M2a）

用户要求现场信息优先SSH读取。本批直接在主机读取SDK源码/配置，并在主机p7_sdk_venv运行纯Pinocchio FK；没有用离线样例冒充设备状态。为验证项目解析器才对同哈希文件做本地数值对照。无机器人动作、无CAN访问、无相机开流、无sudo。

### 已从现场源码确认（非实机运动验收）

- src/linkerbot/arm/p7/p7.py：左侧motor_ids=61..67，前5个A7Motor，后2个MotorV2，源码注释对应URDF L1..L7。关节名映射属于源码事实；物理标签、角度正方向、零位偏置仍待A核验。
- P7默认world_frame='urdf'；ArmKinetix加载p7__left.urdf，默认tcp_offset=[0,0,0]只表示模型末端无额外偏移，不代表实测TCP。
- ArmKinetix的maestro约定：对模型第一关节placement左乘Rz(90°)和原点到J2的平移，并在FK输出rotation右乘Rz(90°).T。位置/姿态处理不可未经审查当项目单一T_world_base套用。C公共坐标继续使用明确URDF frame，接收方必须提供world_frame字段；不猜Maestro就是world。
- P7.__init__会建立CAN dispatcher、构造motor对象、调用_ensure_v2_ptm_mode及read_initial_state/start_polling。源码明确_ensure_v2_ptm_mode会对MotorV2调用ensure_ptm_mode，注释描述Flash Control Mode 0x02写入。因此“只实例化P7再读get_pose”不是允许的只读路径；本批未执行或导入linkerbot。
- get_angles返回缓存motor.angle.angle；get_pose/FK不可自行证明反馈新鲜，需A额外提供设备/主机时刻、epoch和有效性。

### SSH数学交叉验证

在主机 /home/qwer/p7_sdk_venv/bin/python 只import pinocchio/numpy，用pin.buildModelFromUrdf读取现场文件，输出L8_Link的三组FK（零角度和两组非零测试q）；从未构造真实P7、没有命令角度下发。主机保存 /home/qwer/c_calibration_runs/left_p7_fk_reference_20261107_C10.json。

URDF SHA256=233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce；P7.py和kinetix.py哈希见evidence/remote_sdk_coordinate_audit_C10.json；三组输出见remote_left_p7_fk_C10.json。项目FK与三组Pinocchio矩阵最大元素差均0（判据1e-12）。这验证同一声明模型的实现一致性，不证明物理安装或关节零位正确。

可重跑现场工具 tools/remote_p7_model_reference.py（只在主机p7_sdk_venv执行；包含本次确切SDK路径，换部署需先核对路径/哈希；输出文件采用x模式，已存在则拒绝覆盖）。重跑数值用例不占机器人动作预约；仍不得用P7对象替代该路径。

### 搜索范围与缺失

通过SSH查过 /home/qwer/ros2_ws/src、下载目录，以及vision_candidate_20261106_02/config、vision_candidate_20261106_04/config的URDF/xacro/标定/安装相关文件与extrinsic/T_world/T_base/camera_to/maestro/tcp_offset字段，未返回所需头部→左臂base安装变换。其他目录未穷举，不声称整台主机绝对无文件。SDK的两侧臂URDF只到单臂root，不能补出头部/躯干安装外参。已有相机报告内参不是外参。

### 当前结论与交接

C1-01：现场声明模型可加载，并与主机Pinocchio三组输入一致。C1-03：物理base原点/轴向、机身到头部/左肩关系、真实TCP未知，依旧WAITING_FOR_MEASUREMENT。A→C优先提供带时戳/epoch的七轴反馈及零位/方向核验，明确URDF或Maestro约定；C→A禁止默认TCP=0或仅凭get_pose返回就批准。需要厂家整机安装图/校准记录，或建立已知刚性标记/指针与独立测量约束。先从软件读到的值不能替代这项物理测量。

本批新增主机可复跑数学脚本和两份可追溯证据；没有改SDK、没有推送。已有最近全套86 passed；本批新增验证为远端Pinocchio与项目FK三组1e-12数值对照全部通过。

## 第十一批：候选评估与多层释放几何（C1-04/C2-01/C2-03/M1/M4）

用户要求持续维护三方交接，建立HANDOFF_ABD.md统一入口，汇总全部现场有用发现、最新处理修复、SDK构造副作用、身份/坐标/时钟约束、API样例和M0–M6依赖。每批更新本页及交接入口，最终冻结后交付；当前未发送消息给成员、未推送。

新增planning/candidate_evaluation.py：连接已有五次轨迹校验，支持注入IK与完整路径碰撞证据提供者，按版本验证并独立报告失败，符合提供模型者按总时长排序。没有真实IK/碰撞后端时使用明确mock，不虚构可达性。碰撞scope/missing必须显式给出，full_collision固定UNKNOWN，全部motion_enabled=false。公共Protocol不变。测试覆盖无解、越限、硬碰撞失败/未知、旧模型/状态/缺标定、排序与独立状态。

新增planning/slot_release.py：复用Slot、RigidTransform和tcp_target_for_block，提供world目标、TCP释放/接近/撤退；沿table法向而非worldZ，支撑DAG不改，未检查物理接触/IK/全机碰撞。十块红4黄3蓝2绿1的四层测试验证层高、支撑数和旋转桌面下TCP偏移方向。

全套91 passed，命令python -m pytest -q --basetemp=.test-tmp-c11-final；来源synthetic/mock，未连接设备，无硬件动作。C2-01补齐槽位到释放目标数学链但实测table/TCP未知；C2-03补齐候选评估调度，真实IK/全机碰撞后端仍未实现。C1-03/C1-05/C2-02实际估计改进/C2-04真实复验仍待测，不标完成。

## 第十二批：厂家资产线索、数值IK与测量准备（C1-01/C1-03/C1-04/C2-03）

用户提供三个厂家仓库：linker-bot/linker-sim-assets、linkerbot-python-sdk、linkerhand-ros2-sdk，并确认毫米刻度直尺/卷尺。已通过浏览读取三库入口及sim-assets的P7 torso/arm meta、base.urdf和相机装配说明。网络限制：本地git ls-remote连接超时；在机器人主机尝试GitHub API目录读取，响应IncompleteRead，未保存完整目录/commit。以下为main页面候选，尚未锁定commit，不导入生产配置。

厂家来源：
- https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/src/linker_robot_assets/assets/components/bases/p7_torso/meta.yaml
- https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/src/linker_robot_assets/assets/components/bases/p7_torso/variants/default/base.urdf
- https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/src/linker_robot_assets/assets/components/arms/p7/meta.yaml
- https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/docs/camera-assemblies.zh-CN.md

模型声明：P7组件源A7V2_50_4.27；base_link→arm_left_mount xyz=[0,.164,0]m、rpy0；右侧[.0000332,-.164,0]m。arm_root通过固定装配连接mount。L8_Link是tool0，固定在L7之后45.5mm。它们是源模型声明，不是现场安装测量。torso_root→base_link的1.2m明确为仿真摆放高度，禁止当实际离地高度。腕机335L/顶部ZED资产描述与现场头335L/腕Gemini2不一致，不套相机安装值或其他臂法兰尺寸。实体基准仍需识别。

新增planning/numerical_ik.py：只numpy的有界阻尼数值IK，注入FK，显式位置/旋转容差、姿态权重、阻尼、步长/迭代次数，逐步限位与回溯，返回独立IK状态和局部失败原因。不收敛不是全局不可达证明；不生成轨迹、不计算碰撞、不许可运动。没有默认实机参数。

本地全套95 passed（新增已知姿态反算/FK独立回代、不可达局部失败、越界种子、坐标不符、180度旋转测试）。同哈希现场P7模型的两组反算本地通过。

首次包含SCP的组合操作被auto-review拒绝（认为具体私有源码上传未明确授权），未执行、未绕过。之后先完成本地代码/测试/哈希，用户明确批准将该单文件上传/home/qwer/c_numerical_ik_v1.py并执行纯数学验证。SHA256 e26a011b985be18764a932de5fd7fb2df00ce9ae7b94ed9f83fb39ffd2f9179f在主机断言一致。主机p7_sdk_venv只import pinocchio/numpy并runpy该无硬件文件；未import linkerbot、未构造P7。两组模型目标均6次迭代收敛，位置数值残差2.78e-6/5.34e-6m，旋转约1.67e-6/3.77e-6rad。这些不是实机精度。remote_pinocchio_ik_C12.json为真实SSH运行的模型验证证据，源不是关节反馈，motion_enabled=false；主机报告/home/qwer/c_calibration_runs/remote_ik_C12.json。

现场测量模板calibration/measurement_templates/installation_survey.json：记录操作者/时间/run_id、工具分辨率与不确定度分开、物理基准是否已识别，所有未测坐标链/TCP为null。用户复量外廓50×50×50mm；没有提供顶面平整区/倒角或三次重复值，保留未知，不推断倒角解释尺寸差异。量尺刻度1mm不是±1mm已验证准确度。

本批没有相机开流、CAN访问或机器人动作。C1-04/C2-03新增可运行模型IK；完整碰撞后端、真实轨迹与C1-03仍待安装/零位/工具约束。下一现场动作只先核对铭牌、肩部轴/安装基准与厂家候选图，再制定可重复测量，不能用卷尺猜隐藏轴心或仿真高度补外参。

## 第十三批：持物偏移候选与标定依赖失效（C2-02/C2-04/M4-M6）

新增localization/held_offset.py：输入至少3训练+3独立验证的(sample_id,T_world_tcp,T_world_block)，必须有capture stamp，调用现有RigidTransform合成检查同一时刻、坐标和clock_domain（调用者将epoch纳入域）。相对T_tcp_block对平移平均、旋转SVD投影；所有样本保留，无自动丢异常点，拟合与验证各报告最大平移/角度残差。阈值、grasp_version、candidate_id显式给出；不合格返回FAIL但保留未批准候选供诊断。不提供物理外参准确度保证、不自动应用修正、approved/motion_enabled始终false。真实B若方向不可观测，不能用identity补成完整位姿。

新增planning/context_validation.py：检查arm_role、binding、模型、关节映射、相机SN/profile/安装、标定、TCP、grasp、scene、clock_domain、epoch；未知/变化以及过期/未来时间均拒绝。只做上下文一致性，不验证实物身份/急停/碰撞、不生成许可。A/D必须在执行前和重规划时接入，不能把它当D SafetyGate替代。所有time输入应先属于已声明同一主机时钟域。

测试python -m pytest -q --basetemp=.test-tmp-c13：116 passed（新增21项）；偏移方向在变化世界姿态下恢复、独立验证异常不隐瞒、样本ID泄漏/时钟不符拒绝、13项版本逐项变更/未知拒绝、未来/过期/NaN时间拒绝。来源synthetic，未连接硬件，无动作。真实持物位姿仍依赖A/B同步和已标定工具，不把本批视为C2-02真机精度改进。

新增TASK_STATUS.md提供九项C任务的最新状态，避免仅靠早期表格推断当前完成度；HANDOFF_ABD同步本批API。现场正在询问可见厂家铭牌和左肩轴心，不拆卸/不移动机器人。C1-03仍待物理基准、标定点与TCP实测。

## 现场确认补充：P7与可见肩部基准

用户再次确认机械臂为P7，左肩第一关节旋转中心可见、无外壳遮挡。后续不重复要求型号确认；采用现场P7 URDF作为声明模型继续核对。该确认不自动证明关节零位/正方向、厂家候选机身或相机安装吻合。

下一项无运动测量：如左右第一关节中心均可接近观察，用尺/卷尺量两可见旋转中心的直线距离，记录3次原始mm读数；量中心而非外缘，不转动/推压手臂，右侧无法清楚识别则记未知。厂家候选模型的肩部名义间距约328mm，仅作模型安装尺寸核对，不以结果自动求相机外参。随后再定义左肩基准相对桌面的点/轴测量，避免把单一距离当完整六自由度变换。

## 第十四批：接受实测安装确认、Rabokit审阅与完整位姿路径接口（C1-04/C1-05/C2-03）

用户确认全部安装数值已实测与厂商一致，不再重复索取这些尺寸；新增installation/user_confirmed_vendor_geometry_20261107.json，source为用户实测确认，记录vendor_base_link→L_arm_root厂商声明+用户核验关系，与world/相机/TCP未知分离，不默认运动许可。后续不以仍待独立日志为由重复要求用户量同样尺寸。

Rabokit/manual直接web读取失败，urllib得到前端HTML；读取公开脚本识别其公开手册API，成功读取目录与五份相关章节。第一次终端输出emoji被GBK编码拒绝，设置PYTHONIOENCODING=utf-8后重读成功。没登录、无控制操作。结论及适配差异见RABOKIT_REVIEW.md；不把文档描述当当前主机ROS节点，也不把理想仿真相机替代实机参数。

新增planning/pose_path.py：顺序TCP目标→沿前一解继续IK→带当前起点的关节路点→既有五次时间参数化。任一目标无解，不返回可执行部分路径；IK成功和起点时效/限位失败分开报告；full_collision UNKNOWN，motion_enabled=false。现有models/ArmAdapter和D调度器不变。A接收明确关节轨迹，避免控制器在位姿接口内另选冗余解导致先前碰撞结果失效。

测试python -m pytest -q --basetemp=.test-tmp-c14：119 passed；新增完整顺序目标FK回代、当前点到首目标段、第二目标无解不交部分轨迹、IK通过但状态过期独立拒绝。来源synthetic，本批无SSH设备访问、无相机开流、无运动。接口用法见tests/unit/planning/test_pose_path.py，调用plan_pose_path(fk,targets,seed_rad,limits,ik_settings=...,trajectory_context=...)。

剩余重点：真实碰撞模型装配/覆盖验证、场景导出的实际相机外参/工具关系、与A新鲜状态/执行结果接通；仅手册base_link名称不能猜世界矩阵或TCP数值。完整M3/M5/M6尚未通过。

## 第十五批：采样胶囊碰撞后端与模型轴向约定（C1-04/C2-03）

新增planning/capsule_collision.py：明确名称/坐标/端点/半径的Capsule，轨迹按既有quintic插值采样，检查胶囊对静态半空间平面、球障碍及胶囊自碰撞。自碰撞排除必须给有序具名pair和原因；拒绝未知半径、空几何、坐标/模型/场景不匹配、拓扑变化、超样本预算。碰撞检测在首个接触采样时提前结束，输出段/时间/接触对/间隙；不是整条路径全部接触统计。触碰计FAIL，无接触仅sampled_status PASS，而status/full_collision UNKNOWN，所以不能被候选评估当完整通过。覆盖缺失/间隔/模型版本显式返回。没有推断臂/手/相机半径或真实桌面位置。

核对公开厂家P7左臂碰撞URDF（main未锁commit，文件本身SHA256已固定）：
https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/src/linker_robot_assets/assets/components/arms/p7/variants/left/arm.urdf
SHA256=b898b9597d7d075cc5e7114d76a90d0ec514c387a5fd59411555455a6d722daa。含8个mesh collision引用，尚未解析网格/验证实体覆盖。与现场SDK URDF连杆原点一致，但L1…L7轴全部取反，J2限位也反号换序。不是机械尺寸不符，不要求重复量尺寸。

通过SSH现场重新sha256sum及读取axis，SDK仍为233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce，确认此前版本未变；没有import机器人库/访问CAN/开相机/运动。三组模型验证q_vendor=-q_sdk后FK最大矩阵差0，未转换的非零样例差显著。所有轴限位经[-upper,-lower]变换与厂商一致。

新增localization/joint_conventions.py显式具名符号/偏移/两侧版本映射；版本错或不完整关节拒绝。config/planning/p7_sdk_to_vendor_collision_candidate.json仅用于两份数学模型之间转换，非电机零位/方向标定，不自动启用。证据vendor_p7_collision_audit_C15.json与vendor_sdk_axis_mapping_C15.json；原厂家URDF留artifacts，不修改第三方文件。

全套126 passed，命令python -m pytest -q --basetemp=.test-tmp-c15-final。新增端点无碰撞但中段接触、无接触仍UNKNOWN、self接缝排除必须理由、退化/平行/交叉距离、空几何/未知半径/旧模型拒绝，以及轴反号与J2非对称限位/版本拒绝测试。来源synthetic+源模型比较；不宣称全机/连续/物理碰撞验收。

下一缺项：固定厂商资产修订并解析实际mesh，再明确臂/机身/手/相机/持物/桌面碰撞体和必要安装接缝；场景与TCP尚无具体有效矩阵，仍不得执行真实路径。本批为真实碰撞后端的有限几何基础，C1-04/C2-03保持部分完成。

## 第十六批：实际厂家网格锁定、保守包络与FK接入（C1-04/C2-03）

用户要求不需介入工作自行推进。本批未连接设备或发运动指令。GitHub commits API证书验证失败，未关闭TLS校验；使用raw/media公开下载及Git LFS oid固定内容。不是git commit pin：URDF固定SHA256，所有8份STL按LFS SHA256和字节数核验，源码main改变时URDF不匹配会拒绝。锁清单见evidence/p7_collision_asset_lock_C16.json。第三方文件仅存artifacts/c_real_calibration/robot_models/vendor_collision，不修改SDK，不提交大网格。

tools/fetch_p7_collision_assets.py复现下载，4线程读取公共LFS媒体，每文件50MB预算；拒绝URDF版本改变/mesh哈希或长度不符，不覆盖已有不一致文件。完整锁清单采用x模式，不覆盖旧证据。

新增planning/mesh_envelopes.py：无新依赖，严格解析binary STL长度/有限顶点；检查URDF/所有网格hash、覆盖完整性、受支持identity collision origin/unit scale；不支持项拒绝。按PCA轴和全部顶点最大径向距离生成胶囊包络，显式padding。数学覆盖输入三角形，不等于CAD/实物覆盖。当前8link包络报告p7_mesh_envelopes_C16.json，padding=0仅用于资产诊断，不是安全余量。

新增planning/urdf_capsules.py：将网格局部包络通过既有URDF FK及显式q映射置于L_arm_root，检查源/目标hash和运行时模型变化。无默认TCP、相机外参或真实桌面。实际8mesh和synthetic [0]*7→[.01]*7轨迹已接通采样胶囊检查；在第一帧发现多组包络重叠并FAIL，见p7_mesh_proxy_path_C16.json。包络对相邻乃至间隔一link均可能保守填充，不能推断真实自碰撞；没有为了通过增加排除。采样在首次接触停止，未检查后续全路径。

验证：python -m pytest -q --basetemp=.test-tmp-c16-final 最初129 passed；补哈希/路径拒绝回归后见最终运行。新增binary STL格式/截断/LFS指针拒绝、全部角点包络覆盖/padding、模型符号旋转对应及模型变化拒绝。实际网格全部解析成功，报告保存包含link端点/半径/顶点数；来源是厂商真实资产、测试姿态synthetic，不是硬件运动测试。

下一步自主工作：细化保守代理或引入经验证的网格接触检查，并明确安装接缝策略；继续补工具/相机/持物/环境模型。完整碰撞保持UNKNOWN，不把图形资产加载成功当物理避碰通过。C1-04/C2-03仍部分完成。

第十六批最终回归：`python -m pytest -q --basetemp=.test-tmp-c16-final2`：131 passed；无新依赖安装，无硬件动作。

## 第十七批：FCL环境配置与三角网格查询（C1-04/C2-03）

用户明确授权配置所需环境。主机创建独立c_planning_venv，Python3.12.3；未改已有控制/视觉venv、不用sudo、不修改SDK。首次安装因pytest/Cython大型索引响应截断失败；--no-deps尝试仍下载慢，中断pip后在本地下载Linux wheels，通过SCP传入公共软件分发包，逐个SHA256一致后使用--no-index安装完整numpy/FCL/Cython。非源码绕过授权；没有上传控制代码。固定版本见requirements-linux-fcl.txt与wheel锁清单。

本机另建artifacts/planning_venv以测试项目FCL后端。安装FCL0.7.0.11、numpy2.2.6、Cython3.3.1和项目依赖/测试库；默认Python环境未改。最初测试因独立env缺PyYAML导入失败，补项目依赖后全套134 passed，pip check无冲突。主机最小env用assert验证sphere/mesh相交及1m分离，pip check无冲突，报告remote_fcl_environment_C17.json。没有把本地134项说成主机全套结果。

新增planning/fcl_mesh.py：可选延迟import FCL，具名三角mesh BVH、明确同系姿态、逐pair surface collision/distance、显式clearance、严格排除pair和理由。缺pose、非法indices、非有限数据拒绝。无接触status仍UNKNOWN，表面相交/距离不足FAIL，不混淆体积包含/连续路径/物理安全。新增3项FCL回归。

新增tools/audit_p7_fcl.py：读C16哈希锁资产、显式SDK→vendor符号映射，两个synthetic姿态8mesh各28pair；无任何排除，各有6组表面相交，证据p7_fcl_mesh_audit_C17.json。可能存在安装接缝/模型声明重叠，不视作实物碰撞；不自动排除使其通过。所有形状在声明L_arm_root系，无假相机/table外参。

部署/重建/故障处理/范围详见FCL_SETUP.md。可选依赖planning extra不影响默认离线安装。测试命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-fcl-full：134 passed，pip check通过；主机基础几何assert通过。无CAN访问/相机开流/机器人动作；SSH已退出。下一自主工作为厂家安装接触过滤核对、完整场景模型与连续轨迹覆盖，不等用户配置库。

## 第十八批：厂家接缝与关节路径/连续表面证据（C1-04/C2-03）

下载厂家同路径arm.mjcf，内容SHA256=7e50f11c0dd488f557e95743163824a821f4522cf8403e99e8da6d284239c2e3。contact/exclude列出7个相邻link对；C17两姿态的6个surface相交都属于这些已声明对。新增vendor_exclusions.py严格校验来源hash、reviewed pair和重复/无效排除。config/planning/p7_vendor_installation_seams.json保存具体对及来源；不是从失败结果自动扩大排除。

FCL新增check_trajectory，现有模型变换/符号映射和quintic采样串接；输出各样本、首失败对、最小采样表面距离和缺失覆盖。相邻排除后，两个静态姿态无非排除三角表面相交；第一轮合成轨迹58samples、间隔上限约49.39ms、最小采样距离约13.046mm，证据p7_fcl_path_C18.json。它是八个厂家臂mesh、空环境、合成关节输入，无真实动作。

surface_clearance.py新增固定基座刚性转动链的表面速度界和Lipschitz距离下界，方法/证明/限制见FCL_SETUP.md。模型hash必须匹配。50ms采样的连续下界约-3.389mm，因此维持continuous_surface UNKNOWN；没有以采样PASS掩盖间隔风险。随后同一轨迹细化20ms，结果见p7_fcl_certificate_fine_C18.json及本批最终记录。即使连续表面判据通过，full_collision仍UNKNOWN，motion_enabled=false，未覆盖体积包含和物理/环境/标定误差。

新增4项回归：接缝来源hash/未审pair拒绝、FCL中段相交、已知旋转点速度界、采样gap证据与margin/缺失速度拒绝。独立FCL环境全套138 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c18-final2。源码/网格均本机计算，无SSH动作/设备访问；第三方SDK未改。

第十八批最终结果：同一合成路径20ms细化后142sample，最大gap19.967ms，解析max pair表面速度界0.665520m/s，保守连续表面距离下界+6.401977mm（margin0仅诊断）。continuous_surface_status PASS，full_collision UNKNOWN、motion_enabled=false。所有外部/未建模物体、体积包含与标定误差不覆盖。下载工具同步增加MJCF锁定和复现，未知版本拒绝。

## 第十九批：左O6模型、mimic与独立手部网格检查（C1-04/C2-02/C2-03）

通过SSH只读搜索主机ros2_ws/src、现有视觉config和SDK目录内O6 URDF/xacro及grasp/TCP JSON/YAML，未返回匹配文件；不声称整个主机绝对无文件，未启动驱动或设备。不因缺D预设而停止独立手部模型工作。

厂家components/hands/linkerhand_o6/meta.yaml指向left URDF/XML；P7+O6 unit/recipe猜测路径返回404，未把别的机械臂安装参数套给P7。候选URDF SHA256 e1e42ccd1ff55a28153acb025046f42d810ac97367f7bbfdaebe042d01cd75ba，6actuated+5mimic、12collision link。XML SHA256 3d0ca932028277620c234b984d2dd570fc9d8d82311db988e53ab4618485b643，mimic系数与URDF匹配（thumb1.86、其余0.89），12个明确接触排除（11相邻+掌体/拇指metacarpals安装对）。数据源/关节/范围见vendor_o6_audit_C19.json。

新增localization/hand_kinematics.py：要求完整具名主动关节rad，显式展开mimic、验证所有主动/从动URDF限位、拒绝循环/未知引用。urdf_chain增加resolved_mimic显式入口，缺省仍拒绝mimic；启用时逐项检查所给从动值符合声明，不任意跳过约束。hand_link_poses输出掌根到各指节的未批准RigidTransform，不含臂到手安装。

新增planning/obj_geometry.py严格triangle OBJ解析，支持正/负索引与纹理字段；拒绝非法索引/非三角面、无有限几何，不隐式扇分未知多边形。tools/fetch_o6_collision_assets.py固定URDF/XML内容并下载12个collision OBJ，锁SHA256/长度（共266228bytes）；原件只存artifacts/c_real_calibration/robot_models/vendor_o6_collision，不提交SDK/大网格。锁清单o6_asset_lock_C19.json。

tools/audit_o6_fcl.py：检查全部hash、identity mesh origin/scale、XML/URDF mimic一致性、具名厂家接缝；12mesh BVH分别在全0和[.4,.2,.6,.6,.6,.6]rad两组明确synthetic关节值进行手内66pair检查（声明安装排除不查），两组均无非排除表面相交，结果status UNKNOWN、motion_enabled=false。这些不是raw_u8、不是实际open/close/grasp预设，也不表示实际手版本/手臂安装已标定；没有下发控制指令。证据o6_fcl_C19.json。

复现：PYTHONPATH=src，先tools/fetch_o6_collision_assets.py <新目录>，再tools/audit_o6_fcl.py <目录> <新报告.json>。FCL使用独立planning_venv。最近全套144 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c19-final。新增mimic方向/限位/循环、缺省拒绝mimic、OBJ索引与非三角面拒绝回归。没有硬件动作。

下一自主工作：读取可核验P7→O6固定安装来源后组合臂/手检查；D的实际预设/6通道到rad映射不可由模型限位猜。现阶段手模型覆盖是独立手内，不是已包含在C18臂轨迹连续表面判据中。相机/持物/真实环境仍缺，不申请真实动作许可。

## 第二十批：左臂手组合、报告/采样CLI、候选和交付（C1-02/C1-04/C2-01/C2-03/C2-04）

通过Windows系统证书支持的GitHub公开API读取目录后，找到正确workstation p7_i1_o6_bimanual，并锁commit d0224b8da58802fe7cb2e35dcc9771693c4543b6（此前Python对API证书失败，未绕过TLS）。固定提交下P7/O6组件URDF的SHA256与已下载锁文件完全一致。recipe/manifest/workstation URDF也已读取并互核hash，只提取左侧固定安装关系，不开发双臂。

配置p7_o6_left_mount_candidate.json保存L8_Link→lh_hand_base_link固定变换、厂商commit和recipe/装配/component hash。recipe左安装平移约Z2mm，RPY保留原文精度[3.1416,0,-1.5708]，不擅自圆整；它是机械掌根安装，不是任务TCP。tool_assembly.py复用RigidTransform按非交换链组合，拒绝名字/坐标不匹配。

工具audit_arm_hand_fcl.py串接8臂+12手=20实际厂家mesh，使用七轴符号映射、mimic展开和厂家臂内/手内/臂手安装排除。两组synthetic手势、零臂姿态及对应synthetic quintic臂路径采样均无非排除表面相交，报告arm_hand_fcl_C20.json。手姿态固定、无真实预设映射；不含机身/相机/持物/环境。组合full_collision UNKNOWN。C18连续证据只适用于8臂mesh，未扩展给20组合。无任何硬件动作；source明确为厂商资产+synthetic姿态。

新增planning/approach_candidates.py，显式世界系unit方向与clearance生成6阶段TCP目标，无默认world-up或可行性；复用TCP偏移反解，输入capture stamp保留供上下文校验。候选可交给pose_path/候选评估链，方向未知/非单位/重复拒绝。生成目标不约束实际Cartesian直线，仍须完整关节路径碰撞。

C2-01兼容增量：build_stacking_slots增加gap_m=0.0，原调用结果保持一致；正gap保持居中层和双支撑DAG，gap>=edge/负值/非有限拒绝。几何正重叠不代表实际稳定性。c_ten_slot_sample.py已实际生成十槽位/释放目标SYNTHETIC样例。

C1-02新增solve_tcp_pivot.py：完整metadata、最少4训练+4独立验证样本、ID分离、clock/epoch和矩阵校验，求平移及留出残差；输出旋转null/approved false，拒绝缺项。已生成tcp_pivot_synthetic.json并实际运行CLI；它不是实测数据。

C2-04新增validation_report.py及c_validation_report.py：按stage/source/assisted/config/calibration/scene/clock/epoch分组，保留失败/UNKNOWN/缺误差样本数，ACK不是SUCCEEDED，mock/回放/人工不计无人工真机成功。输出仅描述统计、acceptance INCONCLUSIVE。mock_trials.json与CLI实际运行通过，无虚构真实成功。

源码打包工具增量纳入calibration examples/templates/installation及精确FCL requirements/lock，排除calibration approved真实数据、虚拟环境、原图、SDK/mesh与无关txt；有回归验证。SOFTWARE_REVIEW.md集中可运行入口，NEXT_FIELD_SESSION.md列下一次实际标定需要的输入与现场物品，HANDOFF_ABD同步。用户已实测确认安装尺寸，不再重复要求量尺寸。

全套154 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c20-freeze。Mock十块既有e2e、所有原模块及新增回归均覆盖；未推送/合并/创建Issue。剩余实机依赖：真实TCP/头部→base矩阵、A时刻对齐新鲜状态、D实际手预设映射及真实场景/安全限值/停车证据。未宣称九项C任务或M3/M5/M6全部完成。

## 第二十一批：现场接触确认与左臂被动反馈检查（C1-02/C1-03/M2a）

用户授权开始采集，随后明确确认笔杆已刚性固定、笔尖轻触固定凹点。用户纠正现有Python控制进程是右手，不能用于本轮左臂采样；保留其进程，不读取/注入TTY、不关闭或重启。左任务是左臂J1…J7的61…67反馈配左手工具；手指状态不能代替臂关节。

SSH只读核对进程/监听端口/资料：未发现可直接使用的关节状态文件/服务。只读现场A7Motor/MotorV2解析源码；SDK构造模式写入风险仍存在，未实例化。参照Linux SocketCAN文档recvmsg MSG_DONTROUTE含义过滤本地主机生成帧：https://www.kernel.org/doc/html/latest/networking/can.html 。

执行独立被动CAN RAW receive socket，在所有当前CAN接口上只接收标准ID61…67，3秒有界窗口，无send调用，收到0帧。report remote /home/qwer/c_calibration_runs/left_passive_probe_1b03710c37634b1f8b3df054705d0a14.json，本地摘要left_passive_capture_C21.json。发送帧0，无使能/停止/回零/清故障/Flash写入/运动命令；不改变CAN接口状态。现场仅监听，不以NO_FEEDBACK诊断故障或未上电。

第一有效pivot样本数仍0，未写任何虚假T_base_flange/关节角，未生成标定矩阵。待A/现场提供已验收、无构造副作用的新鲜左臂状态出口；已询问是否有实时角度显示程序/路径。即便接触条件成立，没有七轴反馈也不能计为TCP样本。

## 第二十二批：历史脚本核验与实际只读查询（C1-02/C1-03/C1-05，M2a）

用户说明左臂已上电但无状态程序，并给出p7_test_v1_joints.py/p7_j67_verified.py。SSH读取、锁SHA，发现旧V1脚本漏左J1且含右臂；V2脚本会Rest/使能/运动/解除使能，未执行两份脚本。只读SDK确认A7的06查询与V2初始读取的Rest副作用。

新增tools/c_left_arm_readonly_probe.py及tests/unit/test_left_readonly_probe.py，仅固定can2左61…65各一次06，V2只接收raw，无SDK实例化/控制命令。真实主机运行2.254秒、5查询、0响应，七轴完整状态false、有效TCP样本仍0。没有更改CAN配置/第三方SDK/右手进程。真实设备操作仅寄存器读请求；运动/使能/解除使能/回零/Flash写入均0。不能再将本轮描述为完全不发送CAN帧。

文档LEFT_STATE_ACQUISITION.md记录源文件hash/行号、运行方式、M2a输入要求与剩余V2状态依赖；evidence/left_readonly_capture_C22.json保存主机报告内容，原始路径/hash见文档。HANDOFF_ABD与TASK_STATUS同步。输入接口版本c-left-readonly-probe-1，未修改公共协议；7项新回归，全套161 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c22-final。没有产出有效标定矩阵或真机规划验收。

## 接口根因修复（2026-11-08，C1-02/C1-03/M2a）

用户指出电机已有运动能力，应查接口。对照python-can无过滤接收与原生socket、硬件RX计数，并行同一次请求的两个接收socket，确定C代码0xE00007FF错误订阅了内核错误帧列表。修复为0xC00007FF，真实读回J1…J5；按SDK已核验READ协议读J6/J7模式，两者均返回2。七个电机通信确认，原先窗口的0接收不代表电机问题，本次直接修复并纠正文档，不继续积累暂时无应答日志。

修改tools/c_left_arm_readonly_probe.py及回归：明确标准帧过滤、V2精确模式READ及回应匹配、通信完整性与角度完整性分开。全套163 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c23-final。输入c-left-readonly-probe-1兼容增加mode读及missing_position_ids；无公共接口改动。HANDOFF_ABD/TASK_STATUS/LEFT_STATE_ACQUISITION纠正。无硬件运动；仅位置/模式READ。V2腕部状态采样仍需明确Rest操作的支撑/授权，未以当前五轴和模式构造TCP。

## 支撑下真实Rest反馈采集（2026-11-08，C1-02/C1-03，M2a）

新增tools/c_left_wrist_rest_capture.py及tests/unit/test_supported_rest_capture.py，复用已修复只读帧工具，具体字节/模式核验、故障取消/无退出恢复和现场支持/授权检查。本轮用户明确允许可靠支撑下两腕各一次Rest。实机执行，七轴原始反馈齐全、两腕status0/fault0、收取跨度4.456ms；额外只读61…65使能位均false。没有使能/目标/回零/清故障/Flash写入，左腕最终Rest。动作/依赖/摘要同步LEFT_STATE_ACQUISITION/HANDOFF_ABD/TASK_STATUS及evidence/left_supported_rest_20261108.json。

接口c-left-supported-rest-1，仅原始采集、非公共控制API；不批准标定。固定点接触现场答复和V2量化来源待补，不能从一组数据或默认量程得出有效TCP。原始数据下载SHA核验通过；全套171 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c24-final。没有重复Rest或自动规划运动。

## 第1组接触确认与原始数据转换（2026-11-08，C1-01/C1-02/C1-03，M2a）

用户明确确认首组全程同一点接触、笔杆未松，并确认左腕在可靠支撑下可轻松手动调整。首组成功原始反馈保留为fixed-point raw candidate 1；没有将其提升为有效TCP输入。证据left_supported_rest_20261108.json仅补关联现场确认，原始主机文件/hash保持不改。

新增tools/prepare_tcp_pivot_sample.py：离线将raw→具名SDK关节→锁SHA SDK URDF FK→已有pivot sample行，复用既有urdf_forward_kinematics及sample_id/clock/epoch/T_base_flange。要求接触证据、逐腕已核验Theta范围及来源、显式接收跨度阈值；拒绝缺轴/重复/故障/时钟错误/NaN/过大时差/模型hash错误/原始字节与解码值不符。没有默认量程，不使用另一套几何类型，不自动批准。示例调用见NEXT_FIELD_SESSION.md。真实raw加unknown量程模板已运行拒绝，未写FK或TCP矩阵。

calibration/measurement_templates/left_wrist_theta_ranges.json明确null/verified=false。A/厂家需提供每台66/67实际CAN COM Theta MIN/MAX（rad）、对应设备/固件/配置版本、读取/确认时间及证据；优先从本机参数读回或本机出厂参数记录获取，不盲猜寄存器索引，不改Flash，不把通用手册默认值当实测。未要求重测安装几何。

后续Rest采集工具将capture_id与Linux boot clock epoch分开，仍兼容原schema字段。首组旧epoch为capture UUID，未经绑定证据不得直接重命名后混合；原始样本不丢弃。此轮没有连接/发送新的CAN命令；179项后又补原始字节一致性拒绝，最终全套180 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c25-final。

## 实际抓取坐标链入口（2026-11-08，C1-03/C1-04/C2-02）

用户询问笔尖TCP意义后同意暂停，保留raw、转实际抓取优先级。中断前第2组真实raw已成功采下；归档本地并核验主机SHA256 26d07a04ac16c091a6f65aa29114edfd15c8e371133498fc09ff723de9751a07，腕部位置与第1组相同，五轴仅微小变化，不当独立朝向。此次暂停后无任何CAN命令，关闭残留SSH会话。

新增tools/solve_grasp_offset.py（复用localization.held_offset/RigidTransform），calibration/examples/grasp_offset_synthetic.json，tests/unit/test_grasp_offset_cli.py及ACTUAL_GRASP_CALIBRATION.md；输出c-flange-grasp-candidate-1，T_flange_block明确命名，公共接口未变、没有假设零TCP或默认世界姿态。版本/身份/时钟/预设/物体朝向必须显式，持续夹持与重新抓握分组；独立验证滑移保留为FAIL。CLI样例实际运行并输出到artifacts，source synthetic。

8项新增回归，全套188 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c26-grasp。NEXT_FIELD_SESSION/HANDOFF_ABD/TASK_STATUS同步；A/B/D输入和M2a/M3/M4/M5的格式、单位、时间和验收依赖见新文档。已询问现场稳定整手抓握预设，不需要用户为软件工作随意摆路线/手势。真实外参、V2 Theta量程、实际grasp预设及共同坐标6D观测仍缺，无真实抓放验收。

## 无预设时的候选与左O6实际接口（2026-11-08，C1-04/C2-03，M1/M3）

用户确认无预设并指出C负责规划，C先实现物体侧面接触/期望朝向候选，不以D未交预设停工。新增planning/block_grasps.py、tools/plan_block_grasp.py、cube_face_grasp_synthetic.json、4项回归和GRASP_CANDIDATES.md；复用RigidTransform，未修改公共模型/SDK。world姿态、接近方向显式，几何grasp frame与真实flange/TCP分开，无默认零偏移。CLI已实际输出两候选（sample仅synthetic）。

SSH读取本机O6源码/手动菜单与配置；原生SocketCAN按SN识别左手，5个READ（两接口SN，左身份后固件/角度/故障），当次can1/0x28，SN LHO6-04-322-L-Z-1-D，固件3.0.4、六fault0、raw[253,175,253,253,254,254]。本机映射o6:left:can1为identity standard→hardware raw，不是模型rad标定。证据left_o6_candidate_inputs_20261108.json下载hash与主机一致。无右手查询/进程操作，无控制/速度写/使能/Rest/Flash写入；未执行既有单指脚本。

192 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c27-faces。HANDOFF_ABD/TASK_STATUS/ACTUAL_GRASP_CALIBRATION同步，M1/M3输入输出、单位与限制见新文档。后续依赖是实际空载通道/方向/开口/稳定抓握、V2量程/头部外参及完整碰撞覆盖，未产生动作许可或真实抓取成功。只询问现场清空左手条件，不要求用户提供已有预设。
