# Git协作与目录归属
## 1. 建议布局
项目仓库根目录下：
- src/brick_stacking/contracts/：公共薄类型，D维护；所有破坏性变更须生产/使用双方同意。
- src/brick_stacking/arm/、tests/arm/、config/arm/：A。
- src/brick_stacking/camera/、perception/、verification/，tests/vision/，config/vision/：B。
- src/brick_stacking/geometry/、calibration/、planning/，tests/planning/，config/planning/：C。
- src/brick_stacking/hand/、scene/、task/、execution/，tests/task/，config/hand/：D。
- tests/integration/：按接口链共同维护，M2a归A/C，M2b归B/D，整场用例四人各交模块断言。
- docs/、runs/说明、启动入口：按当前合并点轮值协调；D不负责替所有人修文档/CI/测试。
- calibration/<version>/：C出具标定，B核对相机profile，A核对关节映射；未经验证的矩阵不进有效目录。

这些是建议开发目录，本计划包没有实现这些模块。禁止四个人同时修改一个巨大main.py。CLI只装配依赖；厂商SDK用适配/受支持扩展接入，不直接在site-packages里各改各的。

## 2. 分支和PR
main保持可运行的离线入口，真实硬件默认关闭。建议分支codex/a-arm-readonly、codex/b-head-perception、codex/c-single-arm-planner、codex/d-hand-task-fsm；更推荐每个小任务单独分支/PR。
每个PR引用A1-01等任务ID和M点，说明输入/输出变更、验证来源、设备动作情况、未通过项。A/C、B/D配对审查；跨接口变更另加实际使用者审查。通过审查与适用检查后合并，不等一个人做完一整个阶段才提交。
不得把合并main、打标签或CI绿色理解成真机动作授权。

## 3. 共享文件与联调
contracts、公共配置schema、入口文件的改动提前登记，避免并行大改；任务模块目录由负责人维护。调试时在各自分支或工作树，真实主机使用记录过commit/配置的部署快照。
真实测试前声明唯一动作所有者；其他开发者只用回放/Mock。未经协调不得启动会初始化/使能/写模式的厂商示例或launch。
每次集成保存commit、依赖锁定、配置hash、校准hash、设备SN、run_id。程序重启先自检和重观察，不恢复旧队列。
建议.gitingore排除venv、日志、原始大图/录包、临时文件及凭据。大数据集放独立受控存储，Git保留索引、哈希和可复现说明。上传Git前不将SSH密码写进任何配置。

## 4. 任务看板
任务卡至少：ID、owner、阶段、点数、输入、输出、验收、依赖、当前阻塞、关联PR和证据。
允许WAITING_FOR_MEASUREMENT但必须写清需要的设备/数据/人员；同时推进自己的其他离线任务。任务交接需要接收方用提供样例跑通，不能只发“接口写好了”。
