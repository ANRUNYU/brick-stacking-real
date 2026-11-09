# 离线任务框架 v0.2

> **当前范围**：[单臂两阶段](PROJECT_PLAN.md)。本页保留离线代码事实；已有handoff逻辑暂不扩展。身份/取流实测不改变Mock与真实执行的边界。


```text
CameraFrame -> BlockDetector -> diagnostic localization   [M1 原型]

Synthetic SceneSnapshot -> SafetyGate -> TaskScheduler
        -> SceneManager reservation -> OfflineExecutionManager
        -> MockTaskWorld step -> new snapshot -> verification
        -> slot commit / bounded reobserve / SAFE_HALT
```

两条线路尚未接通：视觉候选还没有稳定实例 ID、已验收方向/标定和可执行质量证据，因此不把合成十块任务冒充视觉闭环。MockTaskWorld 只是可控场景替身，不计算 IK、碰撞、接触、摩擦或执行时长。

## 模块职责

| 模块 | 当前作用 | 后续接入 |
|---|---|---|
| models | 场景快照、块状态、槽位、阶段/结果 | 可序列化 ROS 消息桥接 |
| vision/localization | 上轮 RGB-D 原型与空间数学 | 标定、实例跟踪、真实多视角 |
| scene | 槽位、支撑 DAG、预留/已放未验/验收提交 | 场景关联、遮挡/占用证据 |
| planning | 参数化目标、V1 单臂供料选择 | 抓法、可达性、IK/碰撞、路径 |
| execution | 离线事务、有限失败重试、门控 | Linux 硬件执行器（独立实现） |
| verification | 新观察后的颜色/XYZ/撤手、位置稳定窗口 | 方向/支撑/接触、真实抓起/释放证据 |
| handoff_fsm | 串行交接纯逻辑，异常保留所有权 | 全机互斥协调、真实撤离与占用证据 |
| hardware | Mock 和只读 URDF 解析；真实适配未实现 | P7、O6、Orbbec 官方接口适配 |

`OfflineExecutionManager` 在每次 Mock step 前检查配置/场景时效；拒绝 backend!=mock。虽然方法签名便于后续设计，不能将硬件对象改个标签就接进本执行器。真机必须另建执行器并完成安全审查。

## 状态语义

- 上层只有在两块下层 `PLACED_VERIFIED` 后可分配。
- SDK/Mock 命令成功不直接提交槽位；释放后是 `UNVERIFIED`，新观察通过再提交。
- 重试只在新观察确认仍在供料、手空且撤离时进行；超过次数 SAFE_HALT。
- 抓后位置未知/已释放错位时停止，保留未验槽位/占用，不无条件清锁或推积木。
- 比赛模式不包含 WAIT_FOR_HUMAN；日志记录模式和人工介入数，Mock 零人工不是实机自主成功。
- 最终位置窗口验证仅检查颜色/中心/撤手与位移，不是物理稳定、方向或真实支撑的验收。
- HandoffFsm 的 RLock 只协调同进程调用，没有分布式租约、硬件互锁或控制器仲裁；故障不自动释放 owner/token。单臂任务 runner 尚未接入交接流程。

## 运行

```bash
python -m brick_stacking.app.task_runner
python -m brick_stacking.app.task_runner --fault one_grasp_failure
python -m brick_stacking.app.task_runner --fault grasp_exhaustion
python -m brick_stacking.app.task_runner --fault misplaced
```

后两种应 SAFE_HALT，CLI 以 FAIL/非零返回表示任务未完成；pytest 单独检查其故障响应是否符合预期。产物包含配置快照、源码摘要、阶段日志、槽位/重试统计，hardware_tested=false。

## 已确认部署与尚缺内容

部署目标 Ubuntu 24.04 + ROS 2 Jazzy，日常 Windows Python；见 DEPLOYMENT.md。没有自动 SSH/CAN 连接，没有默认机器人地址。运动规划器/真实驱动/手眼与 TCP 标定/场景跟踪/腕部修正均为明确未完成项，不填假值。
