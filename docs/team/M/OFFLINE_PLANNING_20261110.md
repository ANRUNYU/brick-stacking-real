# M侧离线规划与接口联调首轮

基于M H0提交6d30f73（其父为V a79e679），不改V检测、C35/C49矩阵或任何真实执行端。

## 本轮实现

- localize诊断报告+H0原预算+C35/C49输入文件hash汇总成m-first-grasp-plan-bundle-diagnostic-1，区分诊断坐标、未提供的PlanResult/法兰目标与动作许可。
- 复用RigidTransform验证C49几何组合：T_base_flange=T_base_block@inverse(T_flange_block)。必须显式声明block姿态及same-grasp假设并绑定grasp_version；拒绝错版本/框架，不使用C35临时块偏移作TCP。当前真实V样例方向未知，因此真实flange_targets仍null，不猜单位四元数。
- 避桌面参考点路径形状检查：侧方等待→上方→短下探→先竖直抬→侧向转运→放置上方→短下降→先竖直抬→侧撤。桌面法向显式输入，不假设L_arm_root的Z轴是桌面法向。
- 拒绝缺失/错序阶段、低位横移、缺微抬、侧扫和无侧方接近；只是参考点形状检查，不会把full_collision从UNKNOWN提升为PASS，不能替代全臂/手/持物/线缆/桌面mesh扫掠。

## 实际联调结果

15项软件检查通过（含前轮6项H0诊断）；两类几何样例均为合成，未执行IK、关节轨迹或设备动作。C49测试仅验证矩阵方向/版本语义，不验证实际抓握稳定。

真实12帧H0报告接入后，输出docs/team/M/evidence/first_grasp_offline_blocked_20261110.json，状态BLOCKED_FOR_EXECUTION。参考暂缺来自用户明确答复，保持待测；permit=null、permit_request_allowed=false、motion_enabled=false。

主要拒绝原因：独立尺量参考缺失；C35独立验证/批准未完成；时钟误差界/曝光延迟未知；C49实际抓取执行验收待确认；方向策略、真实七轴起点、桌面与全环境、IK/完整碰撞、真实port/StopPolicy未绑定。此清单不是新的任意门槛，是未具备输入的可追溯说明。

## 复现

python tools/m_first_grasp_offline.py --localized docs/team/M/evidence/H0_C35_single_red_20261110.json --c35 calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json --c49 calibration/candidates/C49_left_grasp_offset_candidate_20261109.json --h0 docs/team/B/evidence/first_grasp_h0_draft.json --output artifacts/m-first-grasp-rerun.json

python -m pytest -q tests/unit/coordination

输出目录/文件须未存在。诊断PlanBundle是供审查的草案封装，尚未接入既有OfflineSafetyGate/生产Gate或真实任务FSM；没有签发permit的方法，更不能直接下发。生产PlanBundle schema仍需在#16/#20共同确认，不能假装此草案已是执行唯一入口。

## Issues及下一步

#17：真实定位与独立参考，planar≤10mm、桌面高度≤8mm，C35拟合与独立验证分开；缺参考时不做虚假验收。
#18：真实执行薄层/反馈/取消/停止、版本绑定Gate及T1空跑；先离线负例，真实动作另行现场授权并过安全门。
#19：T1后逐级T2–T5，持握/释放/撤离/稳定证据，UNKNOWN不当成功，放置≤15mm且颜色匹配。
#20：当前侧向模板形状检查→实际C49姿态绑定→复用plan_pose_path的IK/关节轨迹→完整场景碰撞，再进入PlanBundle/执行适配。

本轮无SSH、ROS、CAN或SDK硬件访问，不扩大到双臂实测。此前双臂框架不纳入首次单臂抓放T1–T5验收。
