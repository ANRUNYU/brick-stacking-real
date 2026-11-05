# Windows 开发 / Ubuntu 24.04 + ROS 2 Jazzy 测试

目标环境由用户于 2026-11-05 确认。日常核心算法、Mock、单测运行于 Windows；测试机为 Ubuntu 24.04 + ROS 2 Jazzy。SSH 只作为远程登录/传输手段，不代替机器人 SDK、ROS 或安全门控。

## Windows 开发

在本工程目录，使用独立 Python 3.11/3.12 虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python experiments/scripts/run_offline_validation.py
python -m brick_stacking.app.task_runner
python tools/check_environment.py --output artifacts/windows_environment.json
```

以上步骤不需要 ROS 2、CAN 或硬件 SDK。不要复制 Windows `.venv`、`.offline_deps`、已安装 SDK 或本机 Python 二进制到 Linux。

## 同步方式 A：GitHub

团队指定远端为 `https://github.com/ANRUNYU/brick-stacking-real.git`。本轮连接器返回 404、当前环境 Git 网络查询失败；尚未核实仓库可见性/默认分支，也未初始化或推送本地工程。以下只适用于团队完成首次源码发布后：

```bash
git clone https://github.com/ANRUNYU/brick-stacking-real.git
cd brick-stacking-real
git status --short
git rev-parse HEAD
```

后续同步先确认工作区干净，再切换团队认可的 commit/tag。不要在测试机未知本地改动上执行 reset --hard，或自动拉取未经验收的最新版后运动。

## 同步方式 B：移动硬盘

Windows 打包：

```powershell
python tools/package_source.py --output artifacts/brick_stacking_source_01.zip
```

记录输出 SHA256，将 ZIP 拷到 Linux 后比较 `sha256sum <ZIP文件>`。在新目录解压，避免覆盖测试机本地标定/数据。源码包采用白名单，不含虚拟环境、密钥、原始记录和 artifacts；`source_manifest.json` 保存逐文件哈希。它不是已签名发行版或可离线安装的依赖包。

若测试机无网络，提前为 **Linux CPython 3.12、实际 CPU 架构**准备依赖 wheelhouse；不能将 Windows wheel 当 Linux wheel。当前尚未制作 Linux 离线依赖包。

## Linux 先做软件验收

Jazzy 已由团队安装后：

```bash
source /opt/ros/jazzy/setup.bash
python3 --version
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python tools/check_environment.py --require-linux-jazzy --output artifacts/linux_environment.json
python experiments/scripts/run_offline_validation.py
python -m brick_stacking.app.task_runner
```

`--system-site-packages` 用于让系统安装的 ROS Python 包在虚拟环境中可见。实际 ABI、厂商依赖仍需现场验证。检查脚本只读取系统信息并检查模块可发现性，不 import/实例化 P7/O6、初始化 ROS 或访问设备。

GitHub Actions 已配置 Windows/Ubuntu 的离线测试矩阵，但尚未在远端运行；本轮仅 Windows 本地测试通过，不宣称 Linux 已验证。

## 后续硬件接入边界

1. 先核实 SDK commit、模型、设备身份和已有 ROS 图；P7 构造函数可能写电机模式，不能拿它做普通探测。
2. 新增 Linux 适配器/ROS 节点，与 Windows 核心包隔离。厂商 topic、QoS、单位、反馈和 stop 能力逐项验证。
3. 通过实测标定、全机碰撞规划和阶段授权后才增加真实执行入口。本版所有 CLI 都是 offline，没有 `--execute` 真机开关。
4. SSH 的主机地址、用户、密钥由团队配置到本机 SSH config；不写进仓库。SSH 会话断开/进程退出不等于机器人已经停车，需要设备侧看门狗和已验证停止链路。

飞书链接 `https://my.feishu.cn/wiki/CffkwZRrmiir4gkeEtJclLyxnjs` 本轮无法直接读取，其具体 SSH 配置或驱动安装步骤尚未核对。本文件没有推测其中的机器人地址/命令。
