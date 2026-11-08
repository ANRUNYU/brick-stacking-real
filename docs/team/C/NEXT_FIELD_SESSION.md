# 当前现场入口（2026-11-08 C31）

以下早期笔尖流程暂停。当前执行 [FIXED_CAMERA_CALIBRATION.md](FIXED_CAMERA_CALIBRATION.md) 的无标记固定块方案，已准备并实跑独立进程相机+五轴READ采集。方块保持同一L5候选框刚性固定；每姿态先复核照片三面入镜，再检查状态稳定、中心和版本。至少6训练+4独立验证，不把同姿态三帧计作三个姿态。无有效外参前不下发抓放路径。只需可靠支撑下人工摆姿，遇阻力停止，不要求重新测量已确认的安装尺寸。

# 下一次真实标定：准备与输入，不重复量安装尺寸

2026-11-08当前方向：用户同意暂停笔尖采样，转入实际抓取坐标链。优先入口ACTUAL_GRASP_CALIBRATION.md；下文笔尖方法仅保留历史，不是当前现场动作请求。左腕保持Rest及可靠支撑，本轮不发任何CAN命令。无需继续维持笔尖接触。

现有P7机械安装与厂家一致已由用户实测确认，左肩轴心可见；不再要求重复量。当前有厂家固定提交的P7→O6机械安装模型，注意这不是任务TCP。头335L已实际取流；源相机处理版本以C09及以后为准。

## 当前真正缺少的量

1. T_flange_tcp的真实平移/方向与版本。
2. T_left_arm_base_head_color_optical（或经明确world/table中转）的实际矩阵。
3. 同一图像时刻的新鲜关节/FK及其时间映射；实际手预设到模型rad的版本化转换。

前两项没有在手册/厂家固定装配中找到本台实际头部安装值；不能把约100×40cm桌面、相机内参、P7→掌根或仿真stand当作它们。

## 已暂停：笔尖TCP枢轴标定

用户准备：可刚性固定、轻且不松动的细指针，以及稳固的固定参考凹点。仅先确认物品，不在未明确安装方式前动臂。指针尖端作为候选TCP，旋转方向另有约束；普通手指接触点不能默认为刚性TCP。

A/C状态入口现已可用：C已实读左61…65位置与66/67模式，并经用户授权在可靠支撑下各发一次Rest取得腕部原始反馈。全七轴通信正常，未实例化P7、未写Flash/使能/发送目标。后续每条样本保留sample_id、原始帧/逐轴收取时间、model/mapping版本、设备ID、clock_domain/epoch。不是等待A完成新驱动；A仍需提供实际轴向/零位/安全与执行依据。

受控采样方案：首组原始反馈已采，用户确认全程同点接触、笔杆未松。其余姿态尚未采。保持尖端在同一凹点，至少4个绕不同轴的训练姿态和4个独立验证姿态。由现场动作负责人执行已确认安全的小范围姿态变化；不得强推有阻力/制动/已使能的关节。C不自动发送运动目标；当前左腕Rest，须可靠支撑。每组新的Rest采集要在相应现场支持和授权范围内，不自动复用旧的一次性授权。

仍缺V2实际CAN COM Theta MIN/MAX及其设备特定证据；这是原始位置计数到rad的量程，不是要求重测机械安装尺寸。measurement_templates/left_wrist_theta_ranges.json保持null/verified=false，收到读回/厂家本机参数确认后才填。可以继续收集明确接触的raw候选，不能用默认值提升有效性。

转换入口tools/prepare_tcp_pivot_sample.py（PYTHONPATH=src）：输入原始capture、已核验range_profile、SDK p7__left.urdf和新输出文件，加--sample-id、--contact-confirmed、--contact-evidence、--max-receive-span-s。模型SHA固定233a0fd9…f7edce，输出复用既有sample_id/clock_domain/epoch/host_stamp_s/T_base_flange行格式；无TCP求解或自动批准。单行生成后再按实际会话装入原pivot输入schema；训练/验证仍各至少4组，静止/接触/范围/时钟证据均需保留。10ms等软件示例门槛不是已验收的真机安全参数，现场需预先明确。

后续采集epoch使用Linux boot_id标识同一host_monotonic启动周期，capture_id独立UUID。首组旧格式epoch是采集UUID，原件保持不改；若和后续多姿态合并，必须有明确时钟绑定依据，不能直接统一字符串。

输入模板：calibration/examples/tcp_pivot_synthetic.json（严禁将source/device改名当实测）；真实记录按同schema另建文件，operator/版本/时钟均必须实填。运行tools/solve_tcp_pivot.py生成candidate和独立验证统计，结果approved=false，TCP旋转null。训练姿态退化/模型错/epoch错/复用sample ID拒绝。独立验证误差门槛需采样前冻结，不能看结果后调整。

## 然后做头部到臂基的点对标定

TCP可复验后，以指针接触分布在工作区不同XY/高度的可视参考点：A给该时刻T_base_flange，B给相机坐标下同一点及原始帧/profile/K/D/深度尺度/配准质量/时间映射；C得到base点并配对。训练与独立验证点分开，避免仅检查同一块中央点。需要明确可视尖端/参考物的识别方法，不能只凭50mm立方体标称尺寸生成坐标。

现有tools/solve_calibration.py已准备，训练验证ID分离；输出不自动批准外参。头部固定标定不要求腕相机；当前不额外发展双臂/交接。

## 软件与现场责任边界

C软件已提供求解、独立误差报告、mimic/模型转换、规划/碰撞及失效检查；A负责执行/停止，B负责真实相机证据和时间，D负责实际预设/手状态/场景。C已执行获准的两次左腕Rest，有实际状态转换，不能继续称完全无硬件操作；无使能/运动目标。用户不需重复安装环境，主机FCL已配好。
