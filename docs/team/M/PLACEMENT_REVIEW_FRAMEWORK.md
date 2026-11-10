# 摆放检查与有界纠偏：离线框架

状态：首轮离线策略与会话记账；不是可执行控制器。2026-11-10。

## 本轮范围

保持现有 V 检测、校准与公共 contracts 不变。新增 M 侧局部草案数据类和纯函数，用于后续 V/M/执行负责人共同核对输入输出。类名不是已冻结的生产 schema。所有 Proposal 都是建议，不调用硬件、不产生 permit、不请求执行；也不能绕过现有定位、时钟、完整碰撞、Gate 和 T1–T5 验收。

当前支持：

1. 根据测量误差及其显式误差界，选择 ACCEPT、补充观察、短推建议、重新抓放建议或 HALT。
2. 时间预算保留剩余必做工作及收尾余量；比较已经验收的推/抓策略完整周期耗时，不只比较接触动作时间。
3. 初次检查使用 trigger，纠偏会话使用更紧的 stop，避免阈值附近来回触发；最终 acceptance 与这两者区分。
4. 只有底层、孤立、侧面可接近、接触控制已验证、碰撞已检查、仅需平移，且有推移响应模型与接触计划版本引用时，才允许提出单指短推建议。
5. 每次纠偏必须重新观察，核对观测版本、时间、稳定、手已退出、邻块未动等证据。无明确改善、姿态恶化、超行程、执行失败或证据未知均停止，不自动反向补推。
6. 次数、累计预留行程、总时限和观测重放检查。阶段处于 WAITING_FOR_RESULT 时不能并行提交另一次动作。

## 文件与入口

- `src/brick_stacking/planning/placement_review.py`：数据草案、判定、候选策略选择和纠偏效果比较。
- `src/brick_stacking/execution/correction_session.py`：离线尝试记账、版本绑定与停止逻辑，不是运动执行器。
- `config/planning/placement_review.template.json`：待测参数模板，几何/接触阈值均为 null，不能直接运行真机。
- `tools/placement_review_demo.py`：仅合成数据的影子演示，输出独立 JSON。
- `tests/unit/coordination/test_placement_review.py`：策略与状态边界检查。

已安装本项目及测试依赖后，在 Windows PowerShell 或 Linux 终端运行：

```text
python -m pytest -q tests/unit/coordination
python tools/placement_review_demo.py --output artifacts/placement-review-demo-01.json
```

JSON 输出拒绝覆盖已有文件。演示阈值标记 SYNTHETIC_ONLY，不能抄入现场配置；它没有测量或拟合真实推移模型。源码目录运行时需将 `src` 加入 PYTHONPATH，或者按项目安装说明安装包。

## 草案输入契约及用途

| 输入 | 生产方与语义 |
|---|---|
| Context | 状态机给出对象/层、frame、scene、calibration/profile hash、epoch、clock_domain；前后必须完全一致 |
| Inspection | V 提供误差值及其界、颜色、支撑、稳定、可见、手已退出及邻块状态；M 不由单张图伪造接触/稳定结论 |
| ErrorBound | 非负绝对偏差 value 与显式 bound；区间为 max(0,value-bound) 到 value+bound；不是程序假设的高斯置信区间 |
| ReviewPolicy | 经审查的 stop/trigger/acceptance、步长/总行程/次数/时限/有效期；单位固定为 m、rad、s |
| TimeBudget | 调度器提供 remaining、mandatory_work、reserve，以及 observe/push_cycle/regrasp_cycle 实测保守耗时 |
| PushEligibility | 接触规划方提供响应模型/接触计划 ID 与已验证事实；布尔值不是代替完整碰撞报告的生产认证 |
| Proposal | 返回类别、原因、绑定的输入版本和短推行程上限；不含可下发方向/轨迹或动作许可 |

Inspection.stamp_s 与 now_s 必须已转换到同一单调时钟域，不能直接传相机硬件时间或 wall clock。转换误差与曝光延迟界须由生产接入层验收；本模块只检查调用方提供的时间差，未实现跨时钟同步。

xy 为桌面内位置误差，height 为桌面法向误差，yaw 为已处理物体对称性的角误差。这些量由 V/localize 提供，不能默认基座 Z 为桌面法向。当前不从图像估计这些量。

scope=layer 只允许对上游已形成的整层汇总报告做检查/补看/停止，**不自动选择一块来纠偏，也不允许整层推移**。上游应保留逐块及支撑关系，不可用均值隐藏某块超差。

## 决策规则

- 上界全部在 trigger 内：初次检查通过，无需精修。
- 区间跨过 trigger 且没有其他确认超差：请求补看；最多两次顺序补看，实际次数由配置确定。
- 确认超差：只在已验证且时间足够的策略中选择完整周期较短者。
- 时间不足或无可用策略，但仍在 acceptance 内且支撑/稳定等成立：允许跳过可选精修。
- 超出 acceptance 且无有效策略：HALT，不将时间不足解释成合格。
- 纠偏后进入 stop 带：完成；不追求零误差。
- 纠偏后位置改善必须超过前后误差界与 min_progress；同时不能有可确认的高度/角度恶化。未到 stop 且没有明确改善则停止。

补看输出只有 view_number 和上下文，表达“需要新的证据”。尚未计算具体腕部相机位姿、轨迹、视场或共享区锁；未来观察规划必须先验证可达/碰撞，并默认单腕顺序进入，不能把 OBSERVE 当作允许双臂同时运动。

## 会话与生产安全边界

CorrectionSession.stage 仅为 Mock 尝试预留预算：READY → WAITING_FOR_RESULT。finish 后为 READY、COMPLETE 或 HALTED。重复旧观测、时间倒退/超限、上下文不一致被拒绝。失败尝试也消耗次数与预留行程，不退款。

actual_push_m 表示执行端报告的推杆/指腹推进行程，不是积木平移距离；后者由新的 Inspection 测量。接近/退出轨迹、速度、力/电流、接触高度、接触点、响应模型适用范围、完整碰撞和实时急停不在这个记账器内。当前只输出行程上限，不能直接转成末端运动。

Python 数据类可被调用者自行构造，故它们不是安全认证或生产执行入口。未来执行端必须重新核对当前状态、时间预算和有效证据，再经过独立 Gate/Permit。进程重启后不恢复旧会话或未完成动作。

## 五分钟与冻结预算

比赛总预算为 300 s。调度器必须提供当前剩余时间，以及基于实测高分位值的剩余必做工作/动作耗时；本轮没有这些现场统计，演示仅使用合成值。不能靠该演示证明五分钟能完成比赛。

原 H0 放置位置 ≤15 mm、颜色正确及定位/时钟等门槛不变。当前政策模板保留 null，生产接入前需对照 H0 审核；本模块未自动读取 H0，不能自行批准另一组阈值。新加的角度、支撑和分层要求需要联合验收。

## 离线验证及下一步

本轮新增32项检查，连同已有15项共47项通过。覆盖误差带、观测不确定、时间不足、推/抓策略选择、能力缺失、旋转/高度拒绝短推、层级禁止推移、支撑/稳定/邻块异常、滞回、过期/未来观测、版本与重放、无改善/过调/执行失败/未撤手、累计行程及次数上限。

影子演示输出：正常通过、补看、PUSH_PROPOSAL、跳过可选精修、超差停机、不稳定停机；“无明确改善”会话结果 HALTED。全部为 synthetic，commands_sent=0，platform_tested=false。

仍待完成：V 的实际检查报告适配与层级汇总；腕机外参与观察位规划；真实推移响应数据和模型；带接触约束的轨迹；真实 Gate/执行/FSM 接入；现场阈值、时间估计及每一阶段验收。先在底层孤立单块上比较不纠偏/短推/重新抓放，再逐步扩大到邻块与上层，不直接开展双手接触纠偏。

参考依据（用于设计，不代表本设备已验证）：

- [MIT Pusher–Slider 实机反馈控制](https://arxiv.org/abs/1611.08268)：点式推移与接触模式约束。
- [Diffusion Policy 真实 Push-T](https://www.roboticsproceedings.org/rss19/p026.pdf)：推后退出遮挡区，按最终状态验收。
- [Visual Pushing and Grasping 原作者实现](https://github.com/andyzeng/visual-pushing-grasping)：按场景选择推或抓。
