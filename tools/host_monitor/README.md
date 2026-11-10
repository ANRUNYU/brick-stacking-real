# 机器人主机监视服务（局域网网页）

在 **Ubuntu 机器人主机**上运行：实时预览头部相机、轮询左臂只读关节角，并可选打开**单关节控制**（对齐 `left_robot_motor_menu.py` / `p7_test_v1_joints.py` 的 READY→ENABLE→MOVE→RELEASE）。

- **默认只读**：不使能、不发轨迹、不构造完整 P7、不写 Flash。  
- **相机可一键释放**：`POST /api/camera/release` / `acquire`。  
- **运动需显式开启**：进程加 `--enable-motion`，网页再输入确认词；控制会话打开时会暂停只读 CAN 轮询，避免抢 `can2`。

## 主机启动（只读）

```bash
cd ~/brick-stacking-real
git pull
source ~/brick_vision_venv/bin/activate
export PYTHONPATH="$PWD/src"

python tools/host_monitor/server.py \
  --bind 0.0.0.0 \
  --port 8088 \
  --serial CP2L863000KL \
  --arms left
```

浏览器：`http://10.157.173.135:8088/`

## 主机启动（只读 + 单关节控制）

控制依赖 `linkerbot`（建议 `p7_sdk_venv` 或把 SDK `src` 加进 `PYTHONPATH`）：

```bash
cd ~/brick-stacking-real
source ~/p7_sdk_venv/bin/activate   # 需同时有 opencv / pyorbbecsdk2，或另混路径
export PYTHONPATH="$PWD/src:/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src"

python tools/host_monitor/server.py \
  --bind 0.0.0.0 \
  --port 8088 \
  --serial CP2L863000KL \
  --arms left \
  --enable-motion \
  --linkerbot-src /home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src
```

流程：页面「READY 开会话」→ 选 J1–J7 / 步长 → Prepare → ENABLE → MOVE → RELEASE → 关会话。

### systemd

默认单元仍为**只读**。若要常驻带运动，自行在 `ExecStart` 追加 `--enable-motion` 并配好 `PYTHONPATH`/`linkerbot`。

```bash
sudo cp tools/host_monitor/brick-host-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brick-host-monitor.service
```

## 本机 UI 冒烟

```powershell
cd <repo>
$env:PYTHONPATH="src"
python tools/host_monitor/server.py --mock --enable-motion --bind 127.0.0.1 --port 8088
```

## API

| 路径 | 说明 |
|------|------|
| `/api/health` | 存活；`motion_enabled` |
| `/api/state` | 相机 + 关节 + `control` |
| `/api/camera/release` / `acquire` | POST 释放/占用 Orbbec |
| `/api/control/session/open` | POST `{"confirm":"READY"}` |
| `/api/control/session/close` | POST 关会话并恢复只读轮询 |
| `/api/control/joint/prepare` | POST `{"joint":1,"step_deg":5,"direction":0}` |
| `/api/control/joint/enable` | POST `{"joint":1,"confirm":"ENABLE"}` |
| `/api/control/joint/move` | POST `{"joint":1,"confirm":"MOVE"}` |
| `/api/control/joint/release` | POST `{"joint":1,"confirm":"RELEASE"}` |
| `/api/control/status` | GET 控制快照 |
| `/stream/head` | MJPEG |

## 安全边界

- 仅左臂 `can2`，ID 61–67；一步默认 ≤5°（腕 ≤3°），硬上限见 `joint_control.py`。  
- V1=J1–5 PP；V2=J6–7 仅当 Flash 模式已是 P-T-M=2，否则拒绝（不写 Flash）。  
- 不实例化 `linkerbot.P7`。
