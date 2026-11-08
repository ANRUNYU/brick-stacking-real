# 左臂状态采集审查（2026-11-07，C1-02/C1-03/M2a）

现场用户提供：左臂can2，J1…J7为61…67。主机已上电、无状态程序；现有控制进程是右手，保留不动。设备对应关系不是当前七轴反馈或标定验收。

## 已通过SSH读取的历史测试脚本

|主机文件|SHA256|实际内容|
|---|---|---|
|/home/qwer/p7_test_v1_joints.py|55aa0f2c22698dd0620fcfc9eb5d6d2de2828daca9541f1ce5ad9ddb37f362ee|LEFT只列J2…J5；另外包含RIGHT J1…J5。无参数选择；执行到确认后会设置模式/速度/目标并可能使能，不可import来读取状态。|
|/home/qwer/p7_j67_verified.py|0cb59850bc03f0ba49ca65d83d4445f41e1f8963d44752bb0831867ab5806f1c|选择左J6或J7；先读Flash模式，再read_initial_state发Rest，之后使能、心跳、5度/6秒/Kp12运动，最后解除使能。不是纯读取脚本。|

用户陈述这些关节此前已验证可通信/运动；本轮未重新执行测试脚本，不能把历史成功等同于当前新鲜状态。源码审查证据来自SSH读取，不依靠离线猜测。

现场SDK src/linkerbot/arm/a7/motor.py:124–156确认J1…J5为标准CAN ID、单字节06查询，返回命令字节后float32 little-endian rad。src/linkerbot/arm/p7/motor_v2.py:498–502确认read_initial_state发送FF×7+FD的Rest状态切换；start_polling是控制心跳。未找到经核验的V2纯实时角度查询，因此不猜协议、不将缓存当新鲜数据。

## 接口问题已定位并修复（2026-11-08）

问题是C原生SocketCAN采集工具的接收掩码错误，**不是电机不能运转**。旧掩码0xE00007FF误含CAN_ERR_FLAG；SocketCAN据此选择错误帧接收列表，普通反馈不进入该socket。应为CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_SFF_MASK，即0xC00007FF。官方说明：https://www.kernel.org/doc/html/latest/networking/can.html#can-filter-usage-optimisation 。

SSH主机同时建立旧/新掩码两个socket，对同一次左J1只读06请求，只有新掩码收到实际反馈（flags=0）；旧socket没有收到。另用成功脚本环境p7_sdk_venv的python-can、不带过滤器，也读到同一关节角度。这确定了工具接收问题，之前的无应答窗口不能用于诊断电机/接线/上电或要求A新建驱动。

修复后在can2实读J1…J5（61…65），依次约[-0.007167,-0.004650,2.649036,0.000128,-1.290078]rad，五轴反馈收取间跨度约2.86ms。它们是此次姿态、SDK符号约定的实读值，不是目标值/零位/完整七轴状态，也不自动套用到未来采样。

J6/J7分别在0x642/0x643发送670b000000000476（Flash控制模式READ），收到420b0200000000ff、430b0200000000ff，均模式2。**全部七个电机通信已确认**，没有写Flash或发送状态/运动命令。模式2并不等于当前已使能，也不是腕部实时角度。

tools/c_left_arm_readonly_probe.py现仅发送左J1…J5位置读和左J6/J7模式读，分开missing_motor_ids与missing_position_ids，不把模式回应当角度。原始V2运行反馈仍只保存raw，不套未验证量化。没有SDK构造/使能/解除使能/回零/模式写入。输出仍非有效完整TCP样本；公共ArmAdapter不变。

Linux调用：`python3 tools/c_left_arm_readonly_probe.py <不存在的输出.json>`。目录须存在。已在主机用审阅后的源码通过SSH stdin运行，未修改SDK、旧脚本或右手进程。新增回归覆盖内核过滤语义、7个read-only请求精确字节与严格回应匹配；全套163 passed。此次无需另写暂时无应答日志，直接纠正原因。

## A/C交接及下一入口

M2a需要A或经现场审核的状态入口提供：左设备/总线绑定版本、七轴具名rad值、每轴接收时间与原始帧、clock domain/epoch、反馈模式/故障、新鲜度与跨轴时差；并锁定原始角度→模型符号/零位版本。不能用零或历史值补缺轴。

若取得V2纯查询协议，先审源码和字节再复用本工具；若厂家仅支持Rest触发或使能后反馈，则下一轮须准备机械支撑、当前状态/模式检查、退出方案及明确现场操作授权，再改变状态。此轮不执行Rest获取角度。固定点接触和8组姿态采集必须等完整可靠状态入口；不要为采样自行搬动已上电机械臂。

验证：`artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c23-final`，163 passed。

## 已授权并执行的腕部Rest采样（2026-11-08）

用户明确允许在可靠支撑下，对左J6/J7各发一次Rest获取反馈。本轮工具c_left_wrist_rest_capture.py先只读核对两轴模式2，随后各一次FF×7+FD，均返回status=0、fault=0。66原始位置32462、67为33376；J1…J5角度已读齐，七轴接收时间跨度4.456ms。随后额外只读2B寄存器，61…65均返回2b00（未使能）。这是当次时刻读回，不等于可手推/制动器释放或后续状态不变。

本轮不再属于“无状态转换”：实际发了2个Rest、2个模式READ、5个角度READ，之后另5个使能位READ。无使能、目标、回零、清故障、Flash写入；右手未动。左腕退出保持Rest，没有自动恢复/使能，现场须继续可靠支撑。本轮授权不用于额外Rest或自动改变姿态。

原始数据已保存主机，下载后SHA256核验一致，见evidence/left_supported_rest_20261108.json。数据是成功真实采集，非Mock；但笔尖在此次采集期间的固定点接触确认仍待用户回答；V2的CAN COM Theta MIN/MAX尚未从驱动器读回。原始U16保留，不把SDK默认±12.5rad静默认证为实测。模式/状态/故障已确认，不等同于角度量化/物理精度验收。

目前尚无有效pivot输入或标定矩阵。后续可继续保留接触确认后的原始姿态候选，同时完成V2量化来源核验；完整pivot需4训练+4独立验证、多个不同方向，不能重复静止姿态充数。不要以本次支持授权自动下发运动目标。

工具调用（必须另有具体现场支持/Rest授权，不能作为只读API）：`python3 tools/c_left_wrist_rest_capture.py <新输出.json> --supported-wrist --allow-rest --authorization-ref <现场授权记录>`。失败不重试、不自动使能或Rest其他轴；有匹配模式、状态、故障检查，保留部分原始反馈。测试覆盖模式不符零Rest、首轴故障取消后续、精确2Rest/无退出恢复、支持/授权缺失拒绝；全套171 passed，命令artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c24-final。
