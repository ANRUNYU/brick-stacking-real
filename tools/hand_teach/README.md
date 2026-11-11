# Hand Teach（左手 O6 网页调姿）

在机器人主机运行，本机浏览器打开。只控制左手，不构造/使能/移动机械臂。

## 主机启动（可调姿）

```bash
cd ~/brick-stacking-real
source ~/p7_sdk_venv/bin/activate
export PYTHONPATH="$PWD/src:/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src"

python tools/hand_teach/server.py \
  --bind 0.0.0.0 \
  --port 8091 \
  --enable-hand \
  --max-speed-percent 15
```

本机浏览器：`http://10.157.173.135:8091/`

流程：READY 开会话 → 拖六路滑条或点预设 → APPLY。

## 注意

- 默认若不加 `--enable-hand` 则只读。
- 速度上限默认 15%。
- 关掉网页不会自动停手，最后一次目标会保持。
- 若 Windows 上位机/`can-bridge` 占用 `can1`，先关掉再开本服务。
