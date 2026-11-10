# 摆放检查与纠偏成员交付清单

代码基线：M `d7af506`，[Draft PR #21](https://github.com/ANRUNYU/brick-stacking-real/pull/21)。88项相关测试通过，真实执行未验收；control_ready=false，设备指令0次。

| 任务 | 建议负责角色 | 交付与关联 |
|---|---|---|
| [#10 摆放复检证据](https://github.com/ANRUNYU/brick-stacking-real/issues/10#issuecomment-6763815798) | V，M共同审查 | 目标/槽位关联、有界误差、支撑/稳定/撤手/邻块证据、版本时钟与正负样例 |
| [#22 单指有界短推](https://github.com/ANRUNYU/brick-stacking-real/issues/22) | M+灵巧手/执行，V供测量 | 接触计划、响应模型、推/抓/不调对比、300s时间预算、阈值与停止验收 |
| [#23 腕部多视角观察](https://github.com/ANRUNYU/brick-stacking-real/issues/23) | M规划/互斥，V可见性，相机/标定成员供参数 | 观察请求与位姿候选、外参/视野、路径碰撞、顺序共享区和负例 |
| [#8 帧语义适配](https://github.com/ANRUNYU/brick-stacking-real/issues/8#issuecomment-6763722364) | V+M | 确认旧 head 帧与 C35 光学帧关系，禁止隐式改名 |
| [#17 独立基座对尺](https://github.com/ANRUNYU/brick-stacking-real/issues/17#issuecomment-6763723722) | M/标定，V供尺量 | 十字→基座独立变换与误差、J1关系、高度差异核对，原10mm/8mm预算不变 |

上述角色是建议归属，尚未自动指派个人账号，请成员在对应Issue认领。#22/#23为首抓后扩展，不阻塞#15首个单臂抓放；现场试验仍须完成相应前置验收与当次授权。

本地与远端均使用同一离线框架；本清单不代表合并main或批准真实动作。
