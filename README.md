# brick-stacking-real

**C分支交付更新（2026-11-08）：** 坐标/标定/规划代码、真实采集证据及约1MB可复算RGB-D/关节样例见 [C → A/B/D交付入口](docs/team/C/README.md)。完整软件回归290通过；头部到左臂基座外参、实际抓握TCP和真机闭环尚未验收。下文原v0.2基线说明按历史范围保留，当前C状态以任务表为准。

独立真机项目的 **Python 离线开发 v0.2.0**。依据根目录两份设计/命名文档，从头实现；未导入 Rabokit 控制代码，未安装或实例化任何硬件 SDK。Windows 开发，Ubuntu 24.04 + ROS 2 Jazzy 部署目标已由团队确认。

## 当前可用

- 严格 RGB-D 输入：uint8 RGB、米制 optical-Z、独立相机内参、拍摄时间/时钟域、已对齐且已去畸变。
- 四色 HSV 掩膜、连通候选、深度有效率与近正视方形面几何检查。紧贴同色大轮廓返回 `AMBIGUOUS`，不按长度强行拆块。
- 显式 frame/provenance 的刚体变换、反投影、动态变换时刻检查。
- RANSAC 平面和含 unknown/NaN 的高度图；由调用者提供桌面法向正方向。平面不能自行确定桌面 XY 原点。
- 顶面假设下的诊断中心估计；没有可靠方向时 `orientation_xyzw=null`，所有视觉结果 `control_ready=false`。
- NPZ RGB-D 回放、MockArm/MockHand、官方 URDF 文本只读检查。
- 固定命名测试及时间戳运行记录，分钟内冲突使用 `_R02`。
- 参数化槽位/支撑 DAG、选砖调度、单臂 Mock 事务、复检后提交、有限重试和最终位置稳定窗口。
- 交接区串行互斥/恢复纯逻辑，Windows/Linux 环境检查、白名单源码 ZIP 和离线 CI 配置。

**尚未实现**：真实相机/机械臂/手适配器、ROS 2 节点、稳定实例跟踪、可靠紧贴实例拆分、手眼/TCP 求解流程、避碰规划和真实抓放执行器。Mock 任务尚未与视觉流水线接通，不代表物理抓放验收。

## 安装与运行

Python 3.11+，建议使用独立虚拟环境。在本项目目录运行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m brick_stacking.app.offline_runner --synthetic
python -m brick_stacking.app.task_runner
python experiments/scripts/run_offline_validation.py
```

Linux 激活命令为 `source .venv/bin/activate`。不需要 ROS 2、CAN、SDK、GPU 或大模型 API key。安装 OpenCV headless，不使用桌面窗口。

Windows→Linux 的 GitHub/移动硬盘同步、Jazzy 虚拟环境和检查命令见 [DEPLOYMENT.md](docs/DEPLOYMENT.md)。不要拷贝 Windows 虚拟环境到 Linux。大体模块与明确缺项见 [FRAMEWORK.md](docs/FRAMEWORK.md)。

输出位于 `artifacts/test_runs/<date>/Perception_AdjacentBlocks_RGBD_<YYYYMMDDHHmm>/`，包含 manifest/config snapshot/events/metrics/result，合成演练另保存 `synthetic_rgbd.npz`。`PASS` 仅表示该合成预期被满足。

```bash
python -m brick_stacking.app.offline_runner --recordings path/to/frame.npz
python tools/inspect_urdf.py path/to/arm.urdf
```

录制数据无标注时输出 `INCONCLUSIVE`：程序完成不等于精度合格。格式见 [DATA_FORMAT.md](docs/DATA_FORMAT.md)。

## 团队接口

相机→视觉：`CameraFrame`。视觉→定位：`BlockDetection`，其中三维点是可见表面点。定位→后续场景：`BlockPose`，中心与方向可观测性分开。硬件 Protocol 见 `hardware/protocols.py`；执行接口在实际能力审计完成后定义。

目前没有 TCP 网络端口或 ROS 话题需要启动；这些是 Python 数据接口。未来 ROS 2 桥接必须确认 topic/message/QoS，并保留原厂话题。详见 [TF_CONVENTIONS.md](docs/TF_CONVENTIONS.md)。

## 状态与后续

M0：工程隔离、接口来源审计已建立，设备个体待核验，Ubuntu 24.04/Jazzy 部署目标已确认。M1：合成数据的保守视觉原型可运行，未完成真实数据集验收。M2–M6 的部分任务/交接逻辑已有 Mock 验证，各阶段真实验收仍未完成。

先补充实机 RGB-D 记录与分辨率、对齐方式，再做固定标注测试集、桌面分离与多视角实例分割。未知安装变换、TCP、限位、安全速度始终保留未知值。

入口文档：[设备清单](docs/HARDWARE_INVENTORY.md)、[API 审计](docs/API_AUDIT.md)、[开放问题](docs/OPEN_QUESTIONS.md)、[测试计划](docs/TEST_PLAN.md)。团队已指定远端 ANRUNYU/brick-stacking-real，但本轮连接器返回 404、Git 网络查询失败，未发布代码。该目录尚未初始化独立 Git 仓库；运行记录中 `source_commit=null` 明示当前状态，并记录源码摘要。

C 标定/规划离线工具与边界见 [C 任务状态与交接](docs/team/C/STATUS.md)。
