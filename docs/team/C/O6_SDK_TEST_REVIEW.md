# 已部署O6测试可复用内容（2026-11-08，C1-04/C1-05/C2-02）

根据用户给出的真实路径，通过SSH只读读取tests/hand/o6/及其fixture、现有tests/reports。没有执行pytest目录、没有运行任何单指/整手动作。用户确认手指均可运动，已有单指交互报告7/7记为通过，取消把“手指能否动”作为下一步重复验证；上一轮单指8raw提案从未执行，不再请求该动作授权。

## 有用信息与来源

|内容|已读源码/记录|可复用范围|
|---|---|---|
|六路顺序|test_angle.py:192及SDK angle.py|thumb_flex/thumb_abd/index/middle/ring/pinky；不是URDF rad映射|
|开/半闭/全闭参考|test_angle.py:84/122/135|[100]*6；[50,100,50,50,50,50]；[0,100,0,0,0,0]。归一化百分比，不等于开口mm|
|速度分档|test_speed.py:136|10/30/100是测试标签，没有因此得到实际rad/s或安全速度|
|力矩分档|test_torque.py:114|10/50/100是SDK归一化值，没有Nm/夹持力标定|
|触觉读取|test_force_sensor.py、SDK force_sensor.py|五指B1…B5+A4 READ；每指10片、10×4 uint8，片索引在byte1高4bits；不是已标定N/Pa|
|单指历史交互|tests/reports/test_individual_finger_movement_20261106_142907.json|7步骤记为通过，与用户陈述一致；报告本身缺SN/side/interface，不伪造本机身份绑定|
|速度历史交互|test_speed_affects_movement_20261106_213101.json|记录1通过5未通过，但备注含shell命令，输入可能混杂，不能据此证明5个机械故障或速度验收通过|

源码SHA和原报告内容见evidence/o6_sdk_test_audit_20261108.json；历史时间戳没有时区，保留原样，不拼接到host_monotonic。可复用的姿态/分档已提取为config/planning/o6_sdk_pose_references_candidate.json，approved/execution_enabled/validated_for_50mm_block均false。thumb_abd=100是测试选择；单指交互又测试该通道0，不能把注释当本机实测限位。

## 用户给的pytest命令的实际行为

tests/hand/o6/conftest.py的o6_hand fixture在yield前无交互地设置六路speed=100、acceleration=100、angles=100，再等待2s。因此即使-k只选读取/故障/版本用例，也可能先动作；-o addopts=''不会关闭fixture副作用。整目录还含全闭合、速度/力矩最高档、多次循环和压力交互，不能当抓50mm积木的一键流程。

CAN_INTERFACE决定连接的总线，O6_SIDE=left仅决定左ID0x28，不会自动发现实际左手。近期实读左手在can1，用户示例can0是历史/当次待核验值，使用前须按SN LHO6-04-322-L-Z-1-D重新识别。测试isolate_hand_config隔离临时配置，不能因测试通过推断现场持久映射已验收。_move_until_settled停止流/轮询，O6.close关闭通信；这些不等于机械停止。

## 已实际完成的只读触觉采集

新增tools/c_o6_tactile_probe.py复用已有标准库SocketHand，只发送SN和B1…B5 A4读取，不使用pytest fixture，不选择开合姿态或写速度。重新按SN识别左手后，五指各读两轮，10组均完整10×4，全部raw0。原始文件保留主机和artifacts，SHA核验一致；精简证据evidence/left_o6_tactile_summary_20261108.json。实际接触条件未独立确认，不能把全0称为已校准空载值，更不能证明触觉对压力有效。

调用：`python3 c_o6_tactile_probe.py <新输出.json> --interface <SN核验后的can0或can1> --expected-serial LHO6-04-322-L-Z-1-D`。需要独立的c_o6_index_probe.py位于同目录（仅复用只读连接类，不运行其main/run_trial）。source real、raw units、host_monotonic+Linux boot epoch；不会加载/修改SDK或SDK配置。

3项新回归覆盖完整片段/新frame0重置、错误手指/索引、冲突片段拒绝；全套209 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c29-final。

## 接下来真正需要验证的内容

先在不发手指目标时轻触食指指腹传感区，对比前后原始矩阵；不把人的手放在夹缝，也不运行任何开合动作。若无响应，仅报告本次接触条件下未检测到变化，排查配置/硬件，不能默认存在可用接触反馈。之后由C结合50mm物体生成开口/朝向/渐进闭合候选，并与实际接触/相对法兰位姿及独立夹持复验建立版本关联。SDK全闭合目标不是积木夹持目标；无需用户先摆路线，仍不直接执行整套测试。
