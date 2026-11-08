# 左O6首次空载食指试动提案（2026-11-08，C1-04/C1-05，M1/M2a）

用户确认可以清空左手并保持机械臂可靠支撑，尚未确认已经清空、左手物理停止方法或允许本次食指动作。本轮只准备工具/方案和实际只读预览，不执行运动。

## 可审查的具体动作

实际只读预览：can1，SN LHO6-04-322-L-Z-1-D，六路位置hardware_raw_u8=[253,175,253,253,254,254]；速度寄存器读回六路均0，六fault0。速度读回0不能等同物理停止功能或证明其是可恢复的目标速度配置，因此工具不自动恢复这些值。

拟议目标=[253,175,245,253,254,254]，仅食指通道index=2目标减8raw计数（归一化约99.22→96.08，非度/rad）；试验速度食指10%归一化（raw26，非实测rad/s），其他五路速度使用预览/执行前读数。该步幅/速度是待现场确认的试验设定，不是已验收安全参数或抓握预设。

执行前重新核对左SN、读六路位置/速度/fault；当前起点与本提案偏离任何通道超过2raw则拒绝，不追逐改变后的姿态。完整6路帧协议决定五路同时传当前读数，不能承诺其他手指物理绝对不动。只发一次速度帧及一次角度目标；无机械臂、右手、使能/Rest、回零、清故障或Flash指令。

目标发出后只读角度/fault，最多3s的反馈观察窗口；连续3次目标±2raw仅报告TARGET_FEEDBACK_OBSERVED，不等于实际运动验收。故障、读超时、非食指反馈变化、Ctrl-C等均不盲目回位或补动作。**软件退出/超时不等于电机停止；原目标/试验速度可能继续生效。** 异常必须由现场用已确认可停左O6的物理方式处理。未核验该停止条件前禁止执行，不用SDK.stop_polling/close冒充手指停止。

不自动回位、不恢复速度；正常结束仍需现场确认确实只有食指按预期方向小幅移动、无异常，再另定下一动作。此工具只用于空载辨向，不可拿积木或人的手作为接触试验对象，不能直接用来反复闭合。

## 工具与命令

tools/c_o6_index_probe.py是独立标准库工具，不导入或修改第三方SDK。只允许候选手总线can0/can1、左ID0x28、SN匹配。默认READ_ONLY_PREVIEW，不写入速度或目标，不创建SDK映射配置。不会操作其他CAN ID。若接口重排须先重新只读识别左手，不能认为本次can1永远为左。

只读预览（机器人主机，经审核后部署独立副本；本轮经SSH stdin执行相同源码的run_trial，execute=false）：

```text
python3 c_o6_index_probe.py <新预览.json> --interface can1 --expected-serial LHO6-04-322-L-Z-1-D --delta-raw -8 --speed-percent 10
```

以下是**待现场明确授权、清空/支撑/无夹碰和左手物理停止全部确认后**才允许的执行形式，本轮未运行：

```text
python3 c_o6_index_probe.py <新实测.json> --interface can1 --expected-serial LHO6-04-322-L-Z-1-D --delta-raw -8 --speed-percent 10 --expected-start-raw 253 175 253 253 254 254 --execute --empty-hand --arm-supported --clearance-confirmed --physical-stop-confirmed --authorization-ref <具体本次授权记录>
```

缺任何现场条件/授权、错身份/故障/起点变化/非法raw/步幅速度均拒绝控制写入。命令行布尔确认只记录现场陈述，不会验证真实物理停止能力，不能当生产动作许可。输入/输出schema c-o6-index-trial-1，全部实际命令尝试/反馈/失败原因保留；中断/错误已写目标后stop_confirmed=false，控制程序不能默默报成功。

## 已完成验证与交接

14项单元回归：默认只读无写、缺现场条件拒绝、SN/fault/起点/范围/NaN拒绝、只改变食指目标/速度、无自动回位/速度恢复、故障/超时/中断不伪造stop。全套206 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c28-final；CLI异常提示改进后针对14项再次通过（.test-tmp-c28-exit）。Mock不会计真实运动成功。

实际只读预览已成功，主机/home/qwer/c_calibration_runs/left_index_preview_c2098212-e1b9-410e-b500-32944102069a.json；下载SHA256 6fb9f6366781a1e5450270e6c2f13d7773c1bfb671acfa2b753855931109e9b8一致，证据evidence/left_index_readonly_preview_20261108.json。控制帧0，真实食指试动0。A/D可审阅协议/现场停止/实际辨向结果，C此后据实测构造抓握预设；尚无preset、rad映射、接触力或夹持稳定性验收。
