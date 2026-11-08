# C35 手托固定方块现场标定会话

2026-11-08，C1-01/C1-02/C1-03，M1/M2a。本轮6组求解已完成。用户保持50mm块在L5候选金属框刚性固定；只在相机前方、可靠人工支撑和无阻力范围换姿，不能要求背面盲区或大于45°转向。

## 当前结论

用户明确停止新增独立验证组，并接受10mm以内误差。6组拟合RMSE3.751mm、P95为6.018mm、最大6.724mm，符合用户10mm拟合门槛。原5mm诊断未通过的事实保留；10mm为看到结果后用户确认的标准，不倒填成预先声明。求解结果是OPERATOR_ACCEPTED_FIT_ONLY，独立验证未做、时间误差界未知，motion_enabled=false。不把这些限制扩展成重复采样要求。

结果：[候选参数](../../../calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json)；复算输入[evidence/fixed_camera_C35_fit_inputs.json](evidence/fixed_camera_C35_fit_inputs.json)。候选点偏移约(5.78,6.45,-34.34)mm，是临时固定方块中心相对L5的位置，**不是手部抓握TCP**。

```bash
python tools/solve_fixed_camera.py docs/team/C/evidence/fixed_camera_C35_fit_inputs.json artifacts/C35_recomputed.json
```

默认求解接口仍要求独立验证。新增显式diagnostic_fit_only=true仅输出拟合候选：validation=null、independent_validation=NOT_PERFORMED、consistency=INCOMPLETE；不会把同组残差冒充独立误差。304项软件回归已通过；此后按用户要求不继续扩大测试/哈希检查。

输入模型从实际主机重新读取，SHA233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce，与既有SDK FK版本一致。未修改/提交SDK。安装版本left_L5_cube_mount_operator_confirmed_C35_v1，来源为用户逐组“可以采”对保持固定的指示的答复及照片复核，不复用之前未知/可能拆下的安装偏移。

## 当前记录

|逻辑姿态|三帧视觉检查|候选选择|分类|
|---|---|---|---|
|训练1|PASS/FAIL/PASS|第一帧|几何通过，时间PROVISIONAL|
|训练2|PASS/PASS/PASS|第一帧|几何通过，时间PROVISIONAL|
|训练3首次|FAIL/REJECTED/REJECTED|不选|保留失败，不计入求解|
|训练3重采|FAIL/PASS/FAIL|第二帧|几何通过，时间PROVISIONAL|
|训练4|PASS/FAIL/PASS|第一帧|几何通过，时间PROVISIONAL|
|训练5首次/首次重采|未同时通过视觉和曝光配对|不选|失败保留，不跨帧拼接通过项|
|训练5靠近重采|PASS/FAIL/FAIL|第一帧|几何通过，时间PROVISIONAL|
|训练6|PASS/FAIL/PASS|第一帧|几何通过，时间PROVISIONAL|

6组设计矩阵秩15/15，条件数1244.19。原计划6组求解+4组独立验证，用户后续明确取消新增验证组；同一姿态重复帧没有冒充独立姿态。选择规则是**求外参前按采集顺序选择首个同时通过视觉和曝光配对的帧**，不能看标定残差挑图。

静止整段FAIL原样保留；当前采用SDK映射曝光时刻配对五轴，原设备时钟、SDK时钟、host桥接和各轴前后读数保留。此方法不把device或arrival换名成曝光，SDK映射/插值误差尚未独立定界，故仍不是有效标定验收样本。

## 工具与预先声明的诊断门槛

新增tools/prepare_fixed_camera_point_sample.py：复用已有五轴曝光插值、pinned URDF FK、RigidTransform和三面中心输出，生成一组求解输入候选。核对raw来源/epoch、相机原时间、原帧SHA、模型SHA、安装和训练/验证组；不补腕角、不创建TCP、不生成许可。坏帧决定全部保留，源真实/合成分类不改变。

```bash
python tools/prepare_fixed_camera_point_sample.py CAPTURE_DIR CENTERS.json PINNED.urdf PREPARED.json --group training --operator-evidence "现场固定安装证据" --max-bracket-gap-s .1 --max-bracket-step-rad .01 --max-rgb-depth-skew-s .02
```

三面检查max误差3mm；配对读数间隔0.1s/轴角差0.01rad/RGB-D曝光差0.02s。在尚未拟合外参前，声明点映射诊断残差5mm、设计矩阵条件数上限1e6，用于候选报告；**不是团队物理验收或运动安全限值**，仍不允许真实规划执行。

完整软件回归：`artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c35-final`：297 passed（新增7个候选装配/失败保留/来源时钟模型与安装拒绝测试）。实际训练1/2/3重采已运行CLI；输入/候选和失败索引见evidence/fixed_camera_C35_session.json。原帧留主机/home/qwer/c_calibration_runs/和本地artifacts/c_real_calibration/，不上传完整人物画面。

本批硬件行为只有头部相机开流和左can2/61–65位置READ06。无Rest/使能/角度目标/回零/清故障/Flash；相机每次已停止。

## 与其他成员对接

A的远程a1-04分支cb4abca已阅读：Trajectory使用J1…J7+time_from_start_s/q_rad，Mock最终反馈必须新鲜且晚于末目标；文档确认仍为Mock，不当作真实执行能力。C已有quintic分段，而A契约只表达离散点，后续对接必须保留插值语义，不能把端点原样交出就宣称动态限制成立。

D的d1-02只读适配文档已阅读：SN核验、percent/raw分开；仍不能推断无触觉设备的接触或把percent转换为rad。未合并/覆盖其他成员源码。

A/B/D当前可用交付包括具名L5参考、相机中心、原始时钟/拒绝原因，以及用户接受的fit-only相机→左基座参数。实际抓握关系和M3/M5/M6真实闭环仍未完成。A的实接口Mock已用C的41点合成样例跑通：外部新鲜反馈成功、缺反馈过期失败、取消保持取消；证据C_A_mock_integration_C35.json。连续quintic语义没有因离散点重放而自动验收。
