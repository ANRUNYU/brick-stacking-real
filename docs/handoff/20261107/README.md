# 单臂自主垒砖：统一项目交付包
版本1.0，2026-11-07。此包统一保存团队开发计划和完整硬件接口审计；后续分发以本包为入口。

## 当前开发范围
只有两个阶段：单臂视觉单块抓放闭环；单臂自主完成红4、黄3、蓝2、绿1的十块阶梯结构。双臂协作暂不开发。

## 推荐阅读顺序
1. [当前范围、分工与工作量](team_plan/docs/TEAM_PLAN.md)
2. [完整硬件接口文档](interface_audit/HARDWARE_INTERFACES.md)
3. [模块接口契约](team_plan/docs/CONTRACTS.md)
4. [合并与联调计划](team_plan/docs/MERGE_PLAN.md)
5. 各人细分任务：[A机械臂](team_plan/docs/team/A.md)、[B视觉](team_plan/docs/team/B.md)、[C标定规划](team_plan/docs/team/C.md)、[D灵巧手与任务](team_plan/docs/team/D.md)
6. [任务看板](team_plan/docs/TASK_BOARD.md)及[验收条件](team_plan/docs/ACCEPTANCE.md)
7. [与现有Git仓库的对应关系](REPOSITORY_INTEGRATION.md)

## 包内目录
- team_plan/：两阶段分工、36项任务、每人合并点、接口契约、验收及Git协作规则。
- interface_audit/：完整设备接口、CAN/14电机/左右O6/三相机、序列号角色绑定、参数JSON、遮挡统计、只读探针及证据。
- REPOSITORY_INTEGRATION.md：现有代码结构与分工的对应，避免重复创建另一套模块。
- SHA256SUMS.json：本包全部文件的校验清单。

team_plan/docs/hardware和team_plan/config/hardware_observed.json是分工包内附带的同次审计快照；完整接口资料统一从interface_audit进入。device_map.json是实测快照，所有运动许可仍关闭，不能直接作为已验收生产配置。

## 文档优先级与未完成项
当前项目范围以team_plan的两阶段方案为准。interface_audit/DESIGN_REVIEW.md保留较早的完整路线评审，其中双臂/交接内容仅作未来参考，不是本轮任务。实测身份/设备参数以接口审计及证据为准；未来实现契约以M0全员确认并适配现有代码后的版本为准。

已确认：can0右手、can1左手、can2左臂、can3右臂；左腕Gemini2/AY6M8630086、右腕Gemini2/AY6M86300GH、头部335L/CP2L863000KL。
仍待验收：主臂选择、腕轴运动质量、普通用户相机权限、RGB-D配准、外参/TCP、限位与停止行为、实际抓放及完整自主运行。

本包不含现场相机图像或SSH密码；competition_page1.png是用户提供的一页赛规PDF的渲染。没有创建或推送远程分支，没有更改现有仓库代码。Git上传应按REPOSITORY_INTEGRATION.md选择合并位置，保留现有README和实现。
