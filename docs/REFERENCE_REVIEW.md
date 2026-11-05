# 旧仿真仓库的功能流程参考审查

来源标签 `simulation_example`，仅审查设计流程，未复制其源码/数据契约/阈值/SDK 适配。

2026-11-05 经 GitHub 读取：

- main: `74657f1c4de91e1bdd925097a87d14dbf0548fa0`。
- codex/d-task: `3e701aa715a0dbe235d43e0f9bd423d838fa0b16`。
- 读了该固定版本的 task/planner.py、task/recovery.py、task/verifier.py、runtime/ownership.py。

| 可借鉴的流程 | 在新项目中的独立实现/差异 |
|---|---|
| 槽位与支撑顺序 | scene/stacking_slots.py 按输入边长/方向生成；使用设计规定 L0_0 编码，不继承旧固定 0.05 与旧编码 |
| 新鲜图像与验后提交 | execution/verification 重新设计 synthetic SceneSnapshot 与事务；不引用 common.stacking |
| 未知占用先重观察 | 未验槽位保留；错误放置不当作空槽立即补放 |
| 控制权/共享区域互斥 | 当前仅 HandoffFsm 同进程逻辑，未复制旧 OS 锁或宣称跨控制器互锁 |
| 故障停止与恢复 | 明确有界供料抓取重试，其余保守停机；不套用仿真 O6 指令 |

算法和硬件接口依据仍为本项目设计、正式规则及匹配设备的官方资料/实测。旧仓库的 10 块演练、阈值、ros_sim 时钟、真实反馈能力均不作为本项目验收证据。
