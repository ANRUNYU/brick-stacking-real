# 与现有仓库的对应关系
目标：ANRUNYU/brick-stacking-real。只读检查时main为1acbee0d51faf4d321a36d2cb105cfd9d6ee0fc5；本机克隆与push --dry-run通过，未实际上传。权限预检不证明main分支保护允许直接推送，实施前应重新读取最新HEAD。

仓库已有离线视觉、数据模型、定位、Mock、场景、任务与执行骨架。团队计划形成时尚未读取这些实现，因此其中建议目录不是要求重建或重命名现有工程。先复用已有模块，分析缺项后再增补。

|人员|现有目录/文件|接入原则|
|---|---|---|
|A|src/brick_stacking/hardware/；hardware/protocols.py；execution中的设备执行边界|按当前Protocol扩充真实ArmAdapter和Mock，真实I/O集中hardware；与D明确通用执行与设备执行边界|
|B|hardware中的相机入口；vision/；verification/；models/camera_frame.py、block_detection.py|保留现有CameraFrame和视觉模型，补真实相机与感知能力；不并行新增另一套perception数据类型|
|C|localization/；几何和标定工具；planning中的运动规划部分|复用既有rigid_transforms/camera_projection；补标定、工具/碰撞/运动规划；不与D的task_scheduler争同一职责|
|D|hardware中的手接口；scene/；planning/task_scheduler.py；execution/；app/task_runner.py|复用场景/任务/FSM骨架；补O6和真实单臂流程，暂不扩展双臂handoff|
|全员|models/、hardware/protocols.py、config schema、公共入口|M0共同审阅现有类型，对比CONTRACTS.md；增量迁移与升级，不能直接覆盖|

## 建议上传内容与位置
- 团队文档合并到docs/team/等约定目录，原README增加入口链接。
- 最新接口文档和可公开的实测映射合并到现有HARDWARE_INVENTORY/API_AUDIT或新增硬件审计目录，保留来源和验证状态。
- 旧设计、命名文档中的Gemini335腕机及双臂当前范围说明应同步修订为Gemini2、当前单臂两阶段；保留未来扩展信息时明确标注。
- 36项任务可转换为Issues，但应先核对已有实现，避免把已实现且经验证的功能重新开发；已有Mock不能标成真机完成。
- 报告/录包按仓库既有规则保存；不把全部计划包当代码根目录覆盖解压，不覆盖现有pyproject、README、models或protocols。

这份文件提供落库方法，尚未修改仓库或创建Issues。实际提交使用独立分支和PR，保留已有离线检查并按变更运行适用验证。
