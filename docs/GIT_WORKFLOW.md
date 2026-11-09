# Git协作与目录归属
## 1. 建议布局
沿用现有目录，按文件职责分工：
- models/与hardware/protocols.py：公共模型/Protocol；D协调薄接口，生产者与使用者共同审查，不新建重复contracts实现。
- hardware/中的机械臂适配、对应Mock/测试、臂配置：A。
- hardware/中的相机适配、vision/、verification/及相关模型/回放/测试：B。
- localization/、calibration/、标定工具、planning/中的运动规划与碰撞部分：C。
- hardware/中的O6、scene/、planning/task_scheduler.py、execution/与app/task_runner.py：D。A拥有设备执行实现，D拥有上层编排与门控，双方先明确边界。
- tests/沿用既有unit/integration/e2e结构；每个模块自带样例与Mock，D不代写所有测试。
- 共享入口/配置schema/模型变更先登记；真实标定由C出报告、B核对profile、A核对关节映射。

可按实际需要新增hardware/arm、camera、hand子包，但本次文档提交不创建实现。禁止覆盖已有models/protocols或集中改一个巨大入口。旧handoff逻辑暂不扩展，现成代码不代表双臂能力通过。

## 2. 分支和PR
main保持可运行的离线入口，真实硬件默认关闭。建议分支codex/a-arm-readonly、codex/b-head-perception、codex/c-single-arm-planner、codex/d-hand-task-fsm；更推荐每个小任务单独分支/PR。
每个PR引用A1-01等任务ID和M点，说明输入/输出变更、验证来源、设备动作情况、未通过项。A/C、B/D配对审查；跨接口变更另加实际使用者审查。通过审查与适用检查后合并，不等一个人做完一整个阶段才提交。
不得把合并main、打标签或CI绿色理解成真机动作授权。

## 3. 共享文件与联调
公共模型/Protocol、公共配置schema、入口文件的改动提前登记，避免并行大改；任务模块目录由负责人维护。调试时在各自分支或工作树，真实主机使用记录过commit/配置的部署快照。
真实测试前声明唯一动作所有者；其他开发者只用回放/Mock。未经协调不得启动会初始化/使能/写模式的厂商示例或launch。
每次集成保存commit、依赖锁定、配置hash、校准hash、设备SN、run_id。程序重启先自检和重观察，不恢复旧队列。
建议.gitignore排除venv、日志、原始大图/录包、临时文件及凭据。大数据集放独立受控存储，Git保留索引、哈希和可复现说明。上传Git前不将SSH密码写进任何配置。

## 4. 任务看板
任务卡至少：ID、owner、阶段、点数、输入、输出、验收、依赖、当前阻塞、关联PR和证据。
允许WAITING_FOR_MEASUREMENT但必须写清需要的设备/数据/人员；同时推进自己的其他离线任务。任务交接需要接收方用提供样例跑通，不能只发“接口写好了”。
