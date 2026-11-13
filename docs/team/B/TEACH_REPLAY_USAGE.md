# 示教 JSONL 独立复现

该入口用于复现控制面板生成的 `manual-teach-stream-1` 文件，不需要再次由开发人员临时编写命令。

## Windows 直接运行

在 `output/manual-teach-ee15b58` 目录执行：

```powershell
python tools/run_teach_replay.py "完整的录制文件路径.jsonl"
```

例如：

```powershell
python tools/run_teach_replay.py `
  "E:\Desktop\第十三届华北五省大学生机器人大赛\output\manual-teach-ee15b58\docs\team\B\evidence\line_h\teach_02_20261113_100513.jsonl"
```

Windows OpenSSH 会提示输入 Linux 主机密码。脚本会依次完成：

1. 核对文件为左臂 `can2` 的七轴示教记录。
2. 上传 JSONL 和固定执行器到 `qwer@10.157.173.135`。
3. 停止固定命令行的 `arm_angle_readonly.py:8094` 只读占用。
4. 使用 `linkerbot.P7(side="left", interface_name="can2")` 使能并复现机械臂。
5. 按记录事件调用现有 `8091` 左 O6 服务。
6. 结束或异常时失能左臂并释放 `can2`。
7. 将逐阶段日志保存在 `/home/qwer/teach_replays/logs/`。

默认关节流速度上限为 `0.25 rad/s`，结束后自动失能。需要修改速度时使用：

```powershell
python tools/run_teach_replay.py "记录.jsonl" --speed-rad-s 0.20
```

只有确实需要保持使能时才使用 `--keep-enabled`。

## Linux 主机直接运行

文件已经在 Linux 主机时可运行：

```bash
/home/qwer/p7_sdk_venv/bin/python -u /home/qwer/replay_teach_live.py \
  /home/qwer/teach_02_20261113_100513.jsonl \
  --release-known-reader \
  --output "/home/qwer/teach_replays/logs/replay-$(date +%Y%m%d-%H%M%S).jsonl"
```

执行器只操作左 P7 `can2` 和左 O6 `can1`，不会操作右臂或右手。

