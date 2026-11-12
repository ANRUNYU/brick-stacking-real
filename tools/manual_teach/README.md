# 示教记录面板

手动摆十个物块时用。浏览器打开本机 `http://127.0.0.1:8092/`。

开始之后，主机每秒写 100 行：左臂七个关节（弧度，`get_angles()`，不使能、不发运动）和左手六路百分数。暂停停笔，文件还开着，再点开始继续写同一份。结束关文件。下一次开始新建 `teach_01_...jsonl`、`teach_02_...jsonl`。

抓取和松开在同一页。抓取是 `40.8 23.9 76.5 72.9 0 0`，松开是 `83.5 23.9 84.3 84.3 0 0`。不抓物块时用松开。弧度、百分数和 0–255 原始字节的对照见 [CONTROL_MAP.md](CONTROL_MAP.md)。

默认目录：`docs/team/B/evidence/line_h/`。

## 怎么连

手继续用已经在跑的 `8091`，不要另开一个 O6。手臂另起一个只读进程，只调用 `get_angles()`，不使能、不发运动：

```bash
export PYTHONPATH=/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src
/home/qwer/p7_sdk_venv/bin/python -u /tmp/arm_angle_readonly.py --bind 0.0.0.0 --port 8094
```

操作员电脑上的面板不占 CAN。弧度来自 8094，抓取和松开调用 8091 的 `APPLY`。

```powershell
python tools/run_manual_teach.py --bind 127.0.0.1 --port 8092 `
  --hand-url http://10.157.173.135:8091 `
  --arm-url http://10.157.173.135:8094
```

浏览器打开 `http://127.0.0.1:8092/`。不加这两个地址时是模拟，数字不是真机。
