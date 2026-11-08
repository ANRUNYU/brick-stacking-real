# 实际抓取坐标链（2026-11-08，C1-03/C1-04/C2-02）

用户同意暂停笔尖TCP采集，优先头部→左臂基座外参及实际抓握的积木→法兰关系。不得再把笔尖TCP当抓积木TCP，也不继续索取笔尖姿态。本轮没有任何新CAN指令，左腕保持此前Rest、没有自动使能。原两次raw采集保留；第2组66/67计数与第1组完全一致，其余五轴变化最大约3.20e-5rad，未证明新增朝向，不充作独立姿态。

## 直接复用的关系

令world为显式选定的左臂基座或其他已标定公共系，末端为SDK的L8_Link。实际固定抓握待估计量为：

`T_flange_block = inverse(T_world_flange) @ T_world_block`

给定实际放置目标后：

`T_world_flange_goal = T_world_block_goal @ inverse(T_flange_block)`

这直接规定法兰目标，不需要先定义一个虚构的零偏移TCP。若现有规划接口仍叫tcp，可使用明确版本化的规划工具系转换；不得静默将flange改名成tcp。固定厂家P7→O6掌根安装可用于几何和碰撞，不能替代接触后的积木偏移。

新增tools/solve_grasp_offset.py包装已有localization.held_offset.estimate_held_offset及RigidTransform，无第二套坐标或求解算法；输出c-flange-grasp-candidate-1，target_frame为实际flange、source_frame为积木。训练及独立验证各至少3组，误差不裁掉，始终approved=false/motion_enabled=false。PASS仅表明输入位姿对的一致性，不证明上游外参准确、真实夹持稳定或碰撞安全。

## 可运行样例

PowerShell工作树内：

```powershell
$env:PYTHONPATH='src'
artifacts/planning_venv/Scripts/python.exe tools/solve_grasp_offset.py calibration/examples/grasp_offset_synthetic.json <新输出.json>
```

样例所有身份/位姿/时钟均synthetic；已实际运行，3训练+3独立验证通过。它不是实机预设，不能上传为真实动作输入。JSON字段及行格式直接见样例；不会为缺失真实矩阵自动生成单位矩阵。

## A/B/D输入及验收

|来源/合并点|输入与单位|时间与采样|通过条件/当前缺项|
|---|---|---|---|
|A→C，M1/M2a|具名七轴rad、模型/符号零位映射版本，或T_world_flange 4×4 m|原始帧与逐轴时刻；host_monotonic+boot epoch；同步重采样由生产方提供依据|七轴完整、源可追溯、量程已核验；V2 Theta范围仍缺。不得为采集实例化会写Flash/发模式的P7|
|B→C，M2a/M3|T_camera_block及头部→公共系的实测外参版本，或直接T_world_block；m、SO(3)|RGB-D原帧、内参/畸变/scale/profile、相机SN、时间映射；必须和法兰对应同一采样时刻|外参及配准复验、积木中心与方向有证据；50mm立方体仅中心/颜色不能消除立方体朝向歧义。当前无批准外参，不直接求实际grasp偏移|
|D→C，M1/M3/M4|左手身份绑定版本、固定抓握预设/单位/版本、50mm积木ID/物体坐标轴，实际接触/手几何|每条样本同一grasp_version、block_id；预设改变要另建组|稳定抓握、朝向定义一致。单指测试或SDK默认手姿态不等于已验证整手抓握|
|C→D/A，M3/M5|T_flange_block候选、独立平移m/旋转rad残差、全部输入版本、失败原因|持续夹持漂移与重新抓握重复性分开trial_kind；ID隔离|一致性FAIL仍输出误差；缺姿态/时钟/版本/朝向直接拒绝；候选不能变成运动许可|

工具要求flange_stamp_s与block_stamp_s完全一致；如需插值，须上游先证明映射和插值依据，不能直接把两个不同时间字段改成同值。pose_basis_version描述共同坐标位姿来源（例如某版本实测头部外参，或独立量测）；单独有该字符串不证明它有效。

## 下一次现场工作

先核实现有整手稳定抓握预设；未验证时不让用户随意摆一个手势充当预设。随后确定外参实测方案及积木可观测坐标轴。持续夹持采样可检查物体相对法兰是否滑移；重新抓握多次才评估复现误差，不能混在同一平均值中。当前尚不执行抓握、使能或自动轨迹。

已测188 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c26-grasp；8项新增回归验证法兰命名、独立验证滑移、缺失姿态/朝向、时钟/预设变化及样本泄漏拒绝。仅软件验证，未新增真实抓取验收。

## 无预设时继续规划（2026-11-08）

用户确认目前无抓握预设，C先承担候选设计，不再要求用户提供既有预设或摆路径。GRASP_CANDIDATES.md记录实际左手只读身份/六路反馈/配置映射核验，以及新增两组立方体对面接触几何与可运行CLI。手能否实现0.05m方块夹持、模型rad映射和接触稳定性仍待现场核验，未执行任何手指动作。
