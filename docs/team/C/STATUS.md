# C 离线交付状态（2026-11-07）

远程 main 基线 1acbee0d51faf4d321a36d2cb105cfd9d6ee0fc5；独立克隆 .worktrees/c-calibration-planning，分支 codex/c-calibration-planning。未发现 AGENTS.md。保留原仓库与其他成员代码。已读取统一交付包指定九份资料。契约 v0.1 尚待 M0 冻结；以下为增量离线 API，不覆盖公共 Protocol。

|任务|已有且通过|本批补充|未实现/待实测|
|---|---|---|---|
|C1-01|TF 方向、单位、动态时刻与反投影测试|复用 RigidTransform|FK/关节模型、选侧安装待 A|
|C1-02|原有数学基础|点对求解、独立点误差、枢轴 TCP 平移、JSON 工具及拒绝测试|采集适配器、图像角点提取、现场采样|
|C1-03|无真机通过|采样方案|安装/头部/TCP 实标定全部待测|
|C1-04|无运动规划|固定方向笛卡尔路点、扫掠 AABB 诊断|IK/关节轨迹/全机碰撞/限位未知|
|C1-05|原有 Mock 执行流程|无真实联调|M2a/M3 待 A/B/D|
|C2-01|参数化槽位和支撑 DAG|复用既有实现|实测尺寸/释放接触模型|
|C2-02|无|T_world_tcp=T_world_block inverse(T_tcp_block)|真实偏移估计/有限修正|
|C2-03|无|路径障碍诊断|接近候选排序/IK/可达性|
|C2-04|无|独立验证点统计工具|M5/M6 整场证据|

## 使用与版本

在独立克隆根目录：`python -m pytest -q --basetemp=.test-tmp-final`。
CLI 使用 `PYTHONPATH=src`（PowerShell：`$env:PYTHONPATH='src'`）或 editable install 后运行：
`python tools/solve_calibration.py calibration/examples/synthetic_pairs.json calibration/candidate.json`。
输出拒绝覆盖既有文件，永远 approved=false/motion_enabled=false。误差单位 m；界面展示 mm 时乘 1000。不是手眼 AX=XB 求解器。点对要求同一物理点在两个坐标系中的独立坐标。

## 修改与验证记录

- C1-02 / M1：localization/calibration.py、tools/solve_calibration.py，新增点对刚体与枢轴 TCP 求解。源为合成点对，使用现有 RigidTransform。测试覆盖已知旋转平移、5mm 独立误差、退化/非有限数据、时钟/profile/epoch 和样本泄漏拒绝。
- C2-02 / M4：同模块持物偏移反解，测试 0.1m 偏移方向。不是实测估计结果。
- C1-04 / M1：planning/cartesian_diagnostics.py 提供固定朝向路点和连续平移 AABB 检查；可检出端点之间障碍。仅给定工具/持物包络对已提供静态障碍，不检查整臂，不产生关节轨迹、IK 结果或安全许可。接触面未建模时相交按失败，不自动豁免。
- 基线 53 passed；第一批 61 passed，最终结果见本次验证记录。全部 synthetic/mock；无硬件动作、无 SDK 修改。

## 交接与采样请求

|方向/合并点|最小输入与调用|验证与缺项|
|---|---|---|
|A→C M0/M2a|JointState 需关节名 J1…J7、q_rad、sample_id、host_receive_stamp_s、clock_domain、epoch、source；控制限值和映射版本单独提供|现有 ArmAdapter 仅 tuple，不能推断时间和身份；请 A 增量适配。没有新鲜反馈不做真实规划|
|B→C M1/M2a|synthetic_pairs.json 是点对数据完整样例；每点附 profile、host_stamp_s、clock_domain、epoch|真实采样补原图索引、K/D、尺度、配准、时间映射误差和设备 SN；profile 不同拒绝|
|D→C M1/M4|world_pick/world_place 为现有 RigidTransform；tcp_block 为 TCP→物体关系；scene_version、clearance_m、half_extent_m 和 obstacles 显式传入 offline_pick_place|全部几何单位 m，禁止用抓握预设名称猜手部包络；当前仅固定方向单臂诊断|
|C→A M1/M2a|当前不产生关节轨迹；A 不得执行笛卡尔路点|待 A 提供限位/模型后，输出将含 joint_names、time_from_start_s、positions_rad、预期起点、模型版本。当前 IK UNKNOWN，joint_trajectory NOT_GENERATED|
|C→D M1/M4|offline_pick_place 返回分段位置、scene_version、碰撞局部结果和缺失项|mock 使用；不得将 collision_aabb PASS 转为可执行 PlanResult；真实有效期/标定版本未知，拒绝执行|

现场方案：先由全员选择主臂；A 提供固定时刻的 T_base_flange 和物理关节映射/零位来源，B 提供已配准头部 RGB-D 与时间映射，D 提供工具和持物几何。头部点对覆盖多个 XY 区域及高度，至少 4 个非共线训练点和 4 个独立验证点，建议更多点并重复采样；ID 不重用。TCP 枢轴需至少 4 个绕不同轴的姿态，独立接触点复核平移；方向另行量测。工具求解并不验证物理接触成立。

验收阈值须在采样前由团队冻结：XY/Z、姿态、P95/max、时间偏差、停止行为。未给阈值不批准。改变相机安装/TCP/夹持方式后旧版本失效，重采独立点。主臂、J6/J7、限位、安全停止、另一臂停放仍待实测。现场开流/采样和任何动作均需单独现场授权；本批未连接设备。

## 统一交付包

尚未上传：包内含设备序列号、内网地址与原始 terminal evidence，需完成逐文件公开内容审查后才能判定“没有问题”。本分支不把整个包覆盖进代码根目录。原始资料路径与 SHA256SUMS 保留在用户提供的交付目录。远程上传仅针对后续审查通过的交付资料，不包含本批未审查开发代码；本次未推送或合并。

最终验证：`python -m pytest -q --basetemp=.test-tmp-final`：63 passed（53 基线 + 10 新增）。CLI 合成点对样例实际运行成功；第一次样例生成因 PYTHONPATH 未设置失败，设置 src 后重跑通过。`git diff --check` 通过。输出候选不属于 approved 目录。全部验证来源 synthetic/mock，不是实机记录。
