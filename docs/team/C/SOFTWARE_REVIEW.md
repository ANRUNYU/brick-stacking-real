# C 软件审阅与运行入口

此页用于本地审阅，不代表M3/M5/M6已完成。所有运动开关仍关闭，未推送或合并。

## 运行

本机在项目独立克隆根目录，PowerShell设置`$env:PYTHONPATH='src'`；完整测试：
`artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=<新临时目录>`。
已配置本地独立FCL环境与主机/home/qwer/c_planning_venv，见FCL_SETUP.md。重建时使用独立venv安装`.[dev,planning]`；原有SDK不改。

可运行样例（输出路径必须尚不存在）：
- `python tools/c_motion_sample.py <七轴synthetic轨迹.json>`。
- `python tools/c_ten_slot_sample.py <十槽位synthetic释放目标.json>`。
- `python tools/solve_tcp_pivot.py calibration/examples/tcp_pivot_synthetic.json <TCP候选.json>`。
- `python tools/solve_calibration.py calibration/examples/synthetic_pairs.json <外参候选.json>`。
- `python tools/c_validation_report.py calibration/examples/mock_trials.json <分组报告.json>`。

以上全部输入为synthetic/mock，不用其版本、角度、clearance/速率或矩阵驱动真实机器人。报告器只描述数据，acceptance INCONCLUSIVE，不自行声明实验验收通过。

## 厂家模型审计

固定厂家提交d0224b8da58802fe7cb2e35dcc9771693c4543b6的P7/O6装配与现有组件hash一致；独立臂SDK与厂家模型七轴符号全反，使用具名/版本化转换，不改SDK。P7→O6左安装关系见p7_o6_left_mount_candidate.json（机械安装，不是TCP）。碰撞资产内容hash锁清单在evidence；下载脚本可重建，第三方原文件留artifacts不进源码包。

组合审计命令：
`python tools/audit_arm_hand_fcl.py <P7资产目录> <O6资产目录> config/planning/p7_sdk_to_vendor_collision_candidate.json config/planning/p7_o6_left_mount_candidate.json <新报告.json> --path`。
20份真实厂家网格，两个synthetic固定手势和quintic臂路径无非排除三角相交。手内/臂内/臂手安装排除皆有厂家来源；不含机身、相机、持物、外部环境、体积包含或实机误差。C18连续表面证据只覆盖8link臂，不能自动扩展到20mesh组合。

## 接口链

现有BlockPose/CameraFrame/Slot/RigidTransform保留。新增C函数复用这些类型：generate_approaches→plan_pose_path→具名quintic轨迹→FCL checks；evaluate_candidates按独立IK/限位/碰撞结果排序。所有输入世界/工具关系必须明确，不能以生成成功当执行成功。validate_plan_context负责版本/时钟变化失效，不替代SafetyGate。

D的build_stacking_slots增量兼容加入gap_m=0，已有默认几何不变；要求gap<edge保证几何重叠，支撑DAG和颜色归属不改。正重叠不证明稳定性/物理承载，实际间隙需配置来源。

## 资料入口

TASK_STATUS.md为最新九项状态，STATUS.md为逐批验证和来源；HANDOFF_ABD.md为交给其他三人的入口，NEXT_FIELD_SESSION.md为下一次实际标定所需输入和现场配合。字段未知不以默认值补批准结果。
