# 单臂自主垒砖：四人开发计划
版本 1.0，2026-11-07。供 A/B/C/D 上传独立真机 Git 仓库后共同执行。

当前范围只有两个开发阶段：
1. 单臂视觉引导单块抓放闭环（固定目标先通过，再接视觉随机位置）。
2. 单臂自主完成红4、黄3、蓝2、绿1的十块、单块厚度四层阶梯结构。

本包是计划、接口约定与审计快照，没有实现运动控制程序。先选择并验收一侧机械臂+同侧O6，另一侧保持已验证的安全状态；双臂交接、并发控制和整机双臂标定不在当前范围。

- [总体计划与工作量](docs/TEAM_PLAN.md)
- [接口契约](docs/CONTRACTS.md)
- [合并与联调点](docs/MERGE_PLAN.md)
- [A：机械臂](docs/team/A.md)
- [B：视觉](docs/team/B.md)
- [C：标定与规划](docs/team/C.md)
- [D：灵巧手与任务流程](docs/team/D.md)
- [Git协作与文件归属](docs/GIT_WORKFLOW.md)
- [验收清单](docs/ACCEPTANCE.md)
- [可勾选任务看板](docs/TASK_BOARD.md)
- [任务看板JSON](tasks.json)：可据此手工创建Issues；本包未创建远程仓库或Issue。
- [已测硬件接口](docs/hardware/HARDWARE_INTERFACES.md)
- [设备实测快照](config/hardware_observed.json)：不是可直接执行的生产配置。

开始开发前先共同完成 M0 接口确认，之后四条开发线并行。M0—M6 是两个阶段内的合并/验收点，不是增加七个开发阶段。

Git落库：将本包内容放入团队指定的独立真机仓库，保留已有代码再按目录归属合并；先创建M0及各任务卡，再让每个人阅读总体计划、接口契约、自己的个人计划和合并计划。此包没有建立Git仓库、分支、CI或远程Issue。
