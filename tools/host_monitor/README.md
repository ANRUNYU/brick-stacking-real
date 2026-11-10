# 机器人主机监视服务（局域网网页）

在 **Ubuntu 机器人主机**上运行：实时预览头部相机画面，并轮询左/右臂只读关节角。同一局域网协作者用浏览器打开即可。

- **只读**：不使能、不发轨迹、不构造 P7 运动 SDK、不写 Flash。  
- **相机可一键释放**：网页按钮或 `POST /api/camera/release` 释放 Orbbec；`POST /api/camera/acquire` 再占用。关节轮询在释放后仍继续。  
- **J6/J7**：与现有 `ArmStateReader` 一致，可能无角度（显示为 —）。

权威计划见仓库 `docs/THREE_TRACK_GRASP_DEV_PLAN.md`；本工具仅辅助联调观察，不提升 `control_ready`。

## 主机启动

```bash
cd ~/brick-stacking-real   # 或你的仓库路径
git pull
export PYTHONPATH="$PWD/src"
# 使用已装 pyorbbecsdk2 / opencv / python-can 的环境，例如：
source ~/brick_vision_venv/bin/activate

python tools/host_monitor/server.py \
  --bind 0.0.0.0 \
  --port 8088 \
  --serial CP2L863000KL \
  --arms left
```

浏览器访问：`http://<主机局域网IP>:8088/`  
例：`http://10.157.173.135:8088/`

可选：`--arms both` / `--arms none`；分辨率 `--width 640 --height 480 --fps 15`。

### systemd（可选常驻）

```bash
sudo cp tools/host_monitor/brick-host-monitor.service /etc/systemd/system/
# 按实际仓库路径与 venv 编辑 ExecStart / WorkingDirectory / User
sudo systemctl daemon-reload
sudo systemctl enable --now brick-host-monitor.service
sudo systemctl status brick-host-monitor.service
```

停服以便视觉独占采图：

```bash
sudo systemctl stop brick-host-monitor.service
```

### 防火墙

若打不开页面，在主机放行 TCP 8088（仅建议局域网）：

```bash
sudo ufw allow from 10.157.0.0/16 to any port 8088 proto tcp
# 或临时：sudo ufw allow 8088/tcp
```

## 本机 UI 冒烟（无硬件）

```powershell
cd <repo>
$env:PYTHONPATH="src"
python tools/host_monitor/server.py --mock --bind 127.0.0.1 --port 8088
```

打开 http://127.0.0.1:8088/

## API

| 路径 | 说明 |
|------|------|
| `/` | 监视页 |
| `/api/health` | 存活与只读声明 |
| `/api/state` | 相机元数据 + 关节 JSON（含 `camera_held`） |
| `/api/camera/release` | **POST** 释放 Orbbec，方便其它视觉工具独占 |
| `/api/camera/acquire` | **POST** 重新占用预览 |
| `/stream/head` | 头部 MJPEG |

## 依赖

主机真实模式：`pyorbbecsdk2`、OpenCV、`python-can`（臂）、仓库 `src` 可导入（`PYTHONPATH=src` 或 `pip install -e .`）。  
`--mock` 仅需 OpenCV（编码 JPEG）与标准库。
