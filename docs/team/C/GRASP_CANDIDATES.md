# 无既有预设时的抓取规划（2026-11-08，C1-04/C2-03）

用户确认目前没有稳定抓握预设，并指出C负责动作规划。C负责抓取朝向、接近/抬升/转移/放置/撤退及几何检查，不让用户先摆行进路线；D原分工是手预设/几何和场景输入，C可先生成候选并协助实测，不以等待预设停止规划。当前不执行手指闭合或机械臂运动。

## 本机只读确认

SSH读取现有left_robot_motor_menu.py、SDK hand/o6/{angle,version,fault,speed}.py和hand/angle_mapping.py，未运行单指测试/未实例化O6、未修改SDK或配置。独立SocketCAN仅对can0/can1的左手ID0x28发SN READ；仅在SN明确含-L-的响应接口读固件/角度/故障。未向右手0x27发送任何请求。

本轮左O6在can1，SN=LHO6-04-322-L-Z-1-D，固件回应C2 03 00 04（3.0.4），六故障码均0。六通道硬件raw=[253,175,253,253,254,254]，顺序由SDK声明thumb_flex/thumb_abd/index/middle/ring/pinky。按SDK百分比换算约[99.22,68.63,99.22,99.22,99.61,99.61]；这不是rad/度，也不是已确认的open或grasp预设。

实际配置/home/qwer/.config/linkerbot/hand_angle_mappings.toml中的o6:left:can1为6×256 identity，SHA及原始回应在evidence/left_o6_candidate_inputs_20261108.json。identity仅说明standard raw→hardware raw，没有证明URDF rad关系；SDK按side+CAN接口命名配置，CAN重排后不能仅凭名字选择，仍须SN绑定。SDK声明较大百分比使弯曲通道伸展，此轮未通过动作独立核验方向。SN/固件/六路读数/故障可作为下一次候选设计起点，不能当实时执行起点。

主机摘要/home/qwer/c_calibration_runs/left_o6_candidate_inputs_20261108.json，下载SHA256=04faa05f0c5fe0399ed48497fbd87da52d04ed0bf9a14cf33cd10cf51bb90c21，与主机核验一致。本轮总共5个单字节READ请求（两接口SN、确认左手后固件/角度/故障），0个控制目标/速度写/使能/Rest/Flash写入。无右手进程干预。

## 已实现的物体抓取几何

planning/block_grasps.py使用现有RigidTransform生成相对立方体面的接触中心、外法线、所需物理开口、期望抓取系与预抓系。期望抓取系原点=物体中心，+X沿相对接触面连线，+Z为显式提供的向外接近方向，实际进入方向为-Z。这是任务几何系，不是默认机器人TCP。

例如水平立方体、沿其顶面法线接近时，生成X/Y两组侧面夹取候选；Z面夹取与该接近方向不垂直而拒绝。世界朝向变换和非world+Z方向均有测试。倾斜方向不与任何面法线垂直时明确列拒绝，不悄悄修改用户的接近方向。

50mm方块的面间距离为0.05m。样例的单侧5mm余量得到0.06m所需开口，仅为显式synthetic设计值，不证明实际手能达到、不卡桌面或有足够摩擦。当前候选不绑定食指/拇指、不提供臆造六路闭合目标；flange_goal/hand_preset为空，IK=NOT_CHECKED、trajectory=NOT_GENERATED、full_collision=UNKNOWN。

运行（工作树，PowerShell）：

```powershell
$env:PYTHONPATH='src'
artifacts/planning_venv/Scripts/python.exe tools/plan_block_grasp.py calibration/examples/cube_face_grasp_synthetic.json <新输出.json>
```

输出schema c-cube-face-grasps-1，已实际跑CLI得到两候选。保留source/edge_source/pose_source/版本；样例世界位姿和接近/余量均synthetic，不是本台外参。真实输入必须来自已核验坐标链，不从桌子大致尺寸推算。

## 接入与下一次现场工作

M1/M3：C→D交接几何候选、接触面/法线、所需开口及失败原因；D/A手接口提供经验证的SN绑定、模型rad/实际命令关系或可重复经验抓握预设。取得实际T_flange_grasp后，使用现有RigidTransform组合成法兰目标，再接generate_approaches/pose_path/candidate_evaluation；不把逻辑grasp_frame直接作为已标定工具。M3/M5仍分别报告IK、时间轨迹限制、碰撞及真实抓放成功。

下一现场先做空载单指通道/方向确认，再验证50mm积木的开口与稳定闭合，形成版本化候选；用户只需协助清空左手/保持支撑/观察，不负责设计路线。当前已询问能否取下可能干涉的笔杆附件，没有授权并执行任何新手指动作。具体试动字节、速度/步幅、反馈检查和退出行为须在首次运动前准备并取得相应现场授权，不直接运行旧脚本25个归一化单位的大步测试。此轮未产生可执行轨迹许可。

192 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c27-faces；4项新增回归覆盖50mm两面接触/开口、世界旋转、显式接近方向不改写、非法尺寸/单位向量拒绝。原规划/抓握偏移回归仍通过；不把几何生成当手能抓住或完整避碰。

## 空载食指一次小步测试已准备

用户仅确认可以清空并支撑，未授权本次手指动作。c_o6_index_probe.py已实现默认只读预览与独立执行门槛，当前主机真实预览成功，食指拟议253→245raw、速度10%归一化；速度读回全0不用于证明物理停止，结束不自动回位/恢复速度。原始预览和具体执行/退出行为见O6_INDEX_FIELD_TRIAL.md。全套206 passed、14项针对性行为回归通过。真实控制帧0；待实际清空/现场物理停止确认和具体本次授权，不把“可清空”当运动授权。

## SDK测试资料复用，取消重复单指验证

用户确认手指可动，并提供已部署tests/hand/o6路径。SSH已读源码及已有单指7/7通过记录，O6_INDEX_FIELD_TRIAL不再作为下一动作。测试开/半闭/全闭参考已提取至o6_sdk_pose_references_candidate.json，不等于50mm可用预设；fixture会先100%速度/加速度全开，未运行pytest。当前改为真实只读触觉接触响应确认；两轮五指均收齐10×4、目前全0，尚不证明压力响应。完整来源及下一步见O6_SDK_TEST_REVIEW.md。
