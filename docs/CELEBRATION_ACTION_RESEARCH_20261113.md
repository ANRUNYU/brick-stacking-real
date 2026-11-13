# 庆祝动作现成资源调研（2026-11-13）

## 结论

官方 LinkerBot 仓库当前没有可直接下发到 P7 双臂的“举手欢呼”预设。官方已提供 P7 双臂模型、MuJoCo 仿真、轨迹回放和控制 SDK，但仓库中没有 `celebrate` / `cheer` / `wave` 上肢轨迹资源。

因此选择“现成动作语义 + P7 仿真重定向”，而不是手写一组未经验证的 P7 关节角：

- 双臂动作来源：`YauhenBichel/humanoid-companion` 的 `celebrate`，Apache-2.0。2.2 秒，0.35 秒余弦平滑起落，双臂上举，双肘同相 2.5 Hz 摆动，最后回到起始位。
- 手型来源：`linker-bot/primitive` 的 O6 `v_sign`，MIT，原始六路数值 `[60, 140, 255, 255, 0, 0]`。这个预设已原样换算到本项目示教面板的 0–100 百分数量纲。
- 重定向目标：LinkerBot 官方 `linker-sim` + `linker-sim-assets` 中的 `p7_i1_o6_bimanual` 工位。

冻结的来源、commit、许可证和节奏参数见 [`config/motions/celebrate_external_candidate.yaml`](../config/motions/celebrate_external_candidate.yaml)。

## 不直接复制关节角的原因

`celebrate` 的源机型是 ROBOTIS OP3，每臂只使用肩 pitch 和肘部主要自由度；P7 是 7 轴机械臂，关节轴、零位、手臂长度、左右镜像符号与碰撞包络都不同。把 OP3 的 `±2.3 rad` 肩角直接写入 P7 会是不可接受的跨机型控制。

## 当前实现（非对称可循环 v2）

现场验证表明，双臂同角度高举、同步摆动容易被读成“投降”。v2 因此保留外部动作的“上举、摆动、回程”语义，但改成明确的非对称编排：

- 左臂是主动作：斜向高举，慢速前后挥动两次。
- 右臂是次动作：弯肘收在胸前，快速泵拳两次。
- 循环结尾增加一次不同方向、不同速度的双臂重拍，然后精确回到非对称锚点。
- 进入锚点和退出回原位各执行一次；只有闭环循环体按 `--loops` 重复。
- `--loops` 每次调用必须显式提供，范围为 1–10，避免无界循环和长时间持续负载。

默认命令只生成 dry plan，不打开 CAN：

```bash
python tools/run_celebration.py --loops 3
```

真机执行仍为逐次显式授权，必须同时提供现场清场、空手和实体急停确认：

```bash
python tools/run_celebration.py \
  --loops 3 \
  --enable-live-motion \
  --authorization-ref onsite-operator-approval \
  --confirm-empty-hands \
  --confirm-clear-workspace \
  --confirm-physical-stop
```

实现位于 `src/brick_stacking/motion/celebration.py`。循环模板最后一帧的左右七轴目标与循环锚点完全相同，因此循环次数变化不会在接缝处产生位置跳变。发生异常时对两臂发送当前位置保持，最终正常退出时回到本次执行开始时实测的关节角。

## 真机闭环验证

2026-11-13 在双手空载、工作区清场且实体急停就绪条件下执行 `loops=5`：请求与完成均为 5 圈，循环接缝无位置跳变，最终左臂最大回位误差为 `0.05035477225909801 rad`，右臂为 `0.04806591897459356 rad`，均低于 `0.08 rad` 验收阈值；CAN2/CAN3 收发、丢包和总线错误均为 0。验证后双臂已失能，相关进程与 8088、8091–8094 端口均已释放。

## 后续约束

1. 只有逐次现场授权才可使用 live CLI；manifest 继续默认关闭 `permit_live_execution`。
2. 当前验证范围为空手固定底座庆祝动作；负载、移动底座或环境变化需要重新验证。
3. 每次执行仍必须显式给出 1–10 的循环次数并确认清场、空手和实体急停。

## 排除的候选

- Unitree G1 的 `both_hands_up_deviate_right` 是固件内置 action ID，没有可移植的关节轨迹，且机型不同。
- LinkerHand 旧 ROS 仓库的 `gesture-Show-Wave` 是手指波浪，不是手臂举起欢呼。
- 通用 BVH/Mixamo 欢呼动画需要额外骨架授权与全身重定向，对当前固定躯干 P7 双臂没有更直接的优势。
