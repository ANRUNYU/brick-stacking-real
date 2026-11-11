# 2026-11-12 上午交接：215245 空跑未开跑（起点超门）

- 作者：cube规划
- 日期：2026-11-11 23:15 Asia/Shanghai（UTC+8）
- 给：明天上午先到的协作者
- 仓库：https://github.com/ANRUNYU/brick-stacking-real
- 工作分支：`dev/line-h-wrist-handoff`（不要合进 `main`）
- 播放器 PR：[#34](https://github.com/ANRUNYU/brick-stacking-real/pull/34)，分支 `feat/wrist-path-left-arm-player`，头 `d0425f19d5a99f1495fe9be21c805af65aa6c981`（未合并）

## 一句话

官方路径 215245 的离线规划已通过，七轴播放器也已补齐并修好安全缺口，但空跑被正确拒绝：用同一 `P7` 后端 `get_angles()` 读满七轴后，锁定 URDF 正解得到当前 L8 距官方 `grasp_ready` 约 **497 mm**（门限 10 mm）。明天先核对这次读数是不是单位/轴序/坐标系问题，若读数诚实，再用已有示教把左臂摆到 `grasp_ready` 的 10 mm 门内，然后等待规划的新一次口头授权再空跑。不要发明接近路径，不要开 #31，不要用 `--assume-at-path-start` 跑真机。

## 明确禁止

- 不要 `git reset --hard`，不要丢弃主机脏工作区或 Hand Teach 本地文件
- 不要在主机原来的脏 `main` 工作树上 checkout / 切换分支；继续用独立 worktree（例如 `/home/qwer/brick-stacking-real-wrist-player`）
- 不要把本线合进 `main`，不要自行 Merge #34（规划看过再合到 `dev/line-h-wrist-handoff`）
- 不要关闭或勾完 #29 / #30 / #31
- 不要开 #31，不要在空跑成功后自动抓放，不要对手指 / O6 / 右手 / Rest 下发
- 不要用 `host_monitor` 单关节 MOVE、`tools/t1_bounded_short_combo_runner.py`、`tools/replay_single_block_handoff.py` 代替播放
- 不要把已入库证据的 `executable` / `motion_enabled` / `control_ready` 改成 true
- 不要改官方路径 215245，不要改锁定 URDF，不要为了 Windows CI 去改 URDF 哈希或 T1（那是既有 CRLF 问题）
- 真机不要带 `--assume-at-path-start`
- 昨晚的授权字 `empty-run-215245-20261111` 作废；空跑必须再等规划口头授权并另给授权字
- 不要把只读 `host_monitor` 的 `q_rad`（J6/J7 常为 null）当成七轴真值，更不要编造腕角

## 当前状态

### 官方包（已在 `dev/line-h-wrist-handoff` 头 `00bb0b9`）

- 目标：`docs/team/H/...` 包 213203，canonical sha256 `10ccea75df2472b2a10cf05901316a6cd68bcacf28cf7309db4386de700cda07`
- 路径：`docs/team/P/evidence/wrist_path_layer1_grasp_to_place_20261111_215245.json`
  - LF SHA-256：`349adb65352c820dc13ece77da26b575b269ab31af821244ec60e426758d16a3`
  - 状态 `PLANNED_OFFLINE`，三个可执行标志均为 false
  - #30 离线复核通过（同目录 `..._215245_verification.json`，`PASS_OFFLINE`）
- 官方障碍物源：`two_row_blocks_20261111_212725`（201100 只是归档）
- 官方 `grasp_ready` L8 平移（锁定 URDF FK，`L_arm_root` → `L8_Link`）：
  - `t = [0.43704060430410385, 0.03568436322969936, -0.319015465944929]`
- 锁定 URDF SHA-256：`233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce`
- 门限：到位 10 mm，水平净空 80 mm，先抬 30 mm，TCP ≤ 0.02 m/s，J2 ≥ −0.07 rad；J6/J7 保持 `sdk_report_not_audited`
- 赛题约定：指定四层松散金字塔（红 4 / 黄 3 / 蓝 2 / 绿 1，共 10 块），左臂单独完成，位置不约束，无中途换手；两行里选更红的一行作底。块边长 0.05 m 仍是假设，须保持标注。

### 播放器 PR #34（未合并）

两笔提交，均已推到 `feat/wrist-path-left-arm-player`：

1. `27fc0e8080e5e0634e15250e7b6cb84db9572e0b`：新增默认干跑的左臂七轴播放器（`tools/play_wrist_path_left.py` + `wrist_path_player`）
2. `d0425f19d5a99f1495fe9be21c805af65aa6c981`：补安全缺口
   - 真机若带 `--assume-at-path-start`，硬拒为 `REFUSE_ASSUME_AT_START_ON_LIVE`，不开 CAN
   - 限速改为运动中生效：路点加密弦长 ≤ 2 mm，先 `set_velocities` / `set_accelerations`（按 TCP 弦长 / 0.02），再 `P7.move_j(..., blocking=True)` 主机流式；禁止到点后再 `sleep`
- 单测：`pytest -q tests/unit/wrist_handoff/test_wrist_path_player.py`（报告 10 passed）
- Ubuntu 离线检查已通过。Windows 上 `test_t1_bounded_live_runner.py` 对 URDF 哈希失败（`233a0fd9…` vs `e3cadd19…`）是既有 CRLF，与本播放器无关，不要改。

### 今晚空跑（未开跑，拒绝是对的）

- 用即将播放的同一 `linkerbot.P7` 后端 `get_angles()` 读满七轴，锁定 URDF FK 得当前 L8 约 `tip ≈ [0.033, 0.075, -0.606]`，相对官方 `grasp_ready` 约 **497 mm**，超过 10 mm 门，按授权拒绝。
- 未使能、未下发、未碰手指 / Rest / 右手，未发明接近路径。
- 中止证据（当时还在现场，**尚未入库**）：
  - `docs/team/P/evidence/wrist_path_empty_run_215245_refuse_start_20261111_230520.json`
  - 优先从主机 worktree 原样拷入，不要改内容。

这与稍早只读 `host_monitor` 的观察一致：当时左臂 J1–J5 约为

`[-0.02608, 0.01177, -1.36619, -0.02155, 1.36929]`（J6/J7 为 null），

而路径起点 seed 约为

`[-0.44852, -0.05182, -0.02721, -0.98396, 1.74519, -0.07191, -0.39921]`。

J3 相差很大。因此「臂不在 `grasp_ready`」在空跑前就已经能看出来，不一定是播放器算错。明天仍必须先做一次读数审计，排除单位、轴序或坐标系约定错误，因为现场感觉「似乎有问题」。

### 主机现场

- 主机：`qwer@10.157.173.135`，原仓库 `/home/qwer/brick-stacking-real` 仍在脏的 `main`（约 `bd18d7d`），不要在这棵树上改分支。
- 播放/空跑应使用独立 worktree（建议 `/home/qwer/brick-stacking-real-wrist-player`），检出 `feat/wrist-path-left-arm-player` 的 `d0425f19`（若又有交接提交，用最新头）。
- 为腾出 `can2`，只读 `host_monitor`（原 8088）已停，且误重启过一次后已再次停掉，**现在不在跑**。不要给它加 `--enable-motion`。需要监视时，等播放器释放 CAN 后再只读拉起。
- Hand Teach 仍在 `0.0.0.0:8091`（不要删它的进程日志和本地文件）。示教到 `grasp_ready` 优先走这条已有入口。
- 真机后端：`linkerbot.P7(side=left, interface_name=can2)`。开 CAN 前确认没有第二个控制器在驱左臂。

## 明天上午工作（按顺序，做完一步再走下一步）

### 0. 把今晚的拒绝证据和本交接文档入库

若本文件与 `wrist_path_empty_run_215245_refuse_start_20261111_230520.json` 还没在 `feat/wrist-path-left-arm-player` 上，先从主机 worktree **原样**提交并推到同一 PR #34，不要新开 PR，不要合。不要夹带 Hand Teach 或其他无关文件。

### 1. 分析 497 mm：先证明读数诚实，再谈「去摆臂」

用 worktree 里的锁定 URDF 和当晚拒绝证据（以及如需再一次只读 `P7.get_angles()`，读完即关、不要使能）核对：

1. `get_angles()` 是否为弧度，有没有被当成角度或再乘一次 π/180
2. 七轴顺序是否就是路径里的 J1..J7 / URDF `L1_Joint`..`L7_Joint`，有没有对调或少记腕轴
3. 正解是否锁定 URDF、`parent_frame=L_arm_root`、`child_frame=L8_Link`，哈希是否仍是 `233a0fd9…`
4. 用证据里的七轴（不要用 host_monitor 的 null 腕角）重算 L8，应能复现约 `[0.033, 0.075, -0.606]` 和约 497 mm；复现不了就先修播放器/FK 约定，不要去示教
5. 把当晚七轴与官方 `grasp_ready` seed、以及稍早 host_monitor 的 J1–J5 对照，写成一张短表

结论只能是其中一种，写进证据目录的分析笔记（不要改 215245 本身）：

- **读数诚实**：臂确实不在起点。进入步骤 2。
- **约定有 bug**：先修并补测、推到 #34，再重新读臂；在修复前不要示教去追错误目标。

### 2. 若读数诚实：用已有示教把左臂摆到 `grasp_ready`（≤10 mm）

- 用 8091 Hand Teach（或同等已有示教），把左臂摆到官方 `grasp_ready` 附近。
- 摆完必须再用**同一** `P7.get_angles()` + 锁定 URDF FK 复查 L8，与 `t=[0.43704060430410385, 0.03568436322969936, -0.319015465944929]` 的距离 ≤10 mm。
- 超门就停，报告当前 tip / q / 误差。不要自动规划接近路径，不要单关节搬，不要 T1，不要 `--assume-at-path-start`。
- 示教过程注意急停和有人看臂；不要同时让两个程序占用 `can2`。

### 3. 到位后停下来，等待新的空跑授权

即使已经 ≤10 mm，也**不要**自己开空跑。向规划报告：

- 读数审计结论
- 当前七轴与 L8、误差毫米数
- worktree 提交、CAN 占用情况、急停和扶臂是否就绪

等到规划给出**新的**口头授权和授权字之后，才允许空跑 215245（空手、不开合手指、到 `place_ready` 立即停）。命令形态如下，但授权字以当时规划给出的为准，且**禁止** `--assume-at-path-start`：

```bash
python tools/play_wrist_path_left.py \
  docs/team/P/evidence/wrist_path_layer1_grasp_to_place_20261111_215245.json \
  --expected-sha256-lf 349adb65352c820dc13ece77da26b575b269ab31af821244ec60e426758d16a3 \
  --enable-live-motion \
  --authorization-ref <规划当场给出的新授权字> \
  --output docs/team/P/evidence/wrist_path_empty_run_215245_<ts>.json
```

异常、超速、J2 越界、到位超 10 mm、SDK 失败都立即停。跑完只报告，不要合并，不要开 #31，不要再跑第二次，除非规划再授权。

## 相关 issue（保持打开，不要勾完成）

- #27 Epic：仍停在「固定块路径已离线通过，尚未完成授权空跑」
- #29：官方目标 213203 仍有效，不要重发目标来「绕过」起点门
- #30：官方路径 215245 离线已通过；缺的是现场起点，不是再规划一条路径
- #31：抓放仍未授权，空跑都还没开始
- #32 / #33、C35/#17：本上午不做，除非规划另说
- #34：播放器软件已在 `d0425f19`，空跑未开始；先把拒绝证据和本交接入库，再做读数审计

## 访问 8088（若重新只读拉起）

从操作员电脑访问 `http://10.157.173.135:8088/` 时，把 `10.157.173.135` 加到代理绕过，否则会变成 502（本机 HTTP(S)_PROXY `127.0.0.1:7897`）。
