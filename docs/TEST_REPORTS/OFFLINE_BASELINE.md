# v0.1.0 离线验收摘要

日期：2026-11-05（Asia/Shanghai）。范围：设计 M0 基础及 M1a 合成原型；M0 设备个体审计与 M1 真实数据验收未完成。

- Python 3.12；NumPy 2.5.4、OpenCV headless 5.0.0、PyYAML 6.0.3、pytest 9.2.0。
- 首次测试：19 passed，9 个临时目录创建错误；建立 artifacts 父目录后修正运行设置，无算法断言被放宽。
- 完整测试：**37 passed**，无跳过。覆盖输入格式/单位/对齐、颜色、同色歧义、深度失效、TF 方向和时钟、平面、高度图、回放、Mock、配置与日志。
- 官方左右 P7/O6 四个 URDF 经本项目只读 XML 工具解析；P7 各 7 主动，O6 各 6 主动+5 mimic。实际装配匹配=false。
- 自动记录器路径：`artifacts/test_runs/2026-11-05/Verification_OfflineCore_PYTHON_202611051419/`。完整断言结果见 junit.xml/pytest_output.txt，后续同命令生成独立记录。
- 未连接相机、机械臂或灵巧手；无 CAN、ROS 或硬件 SDK 实例；无任何真实动作。

合成预期：4 个孤立色面候选 UNAMBIGUOUS，1 个两块同色无接缝连通区域 AMBIGUOUS。不是已识别 6 个实际实例；不把未拆分区域编造为多个中心。

保留限制：近正视单面检查不适用于任意手腕视角；未实现 persistent ID、一般 6D 姿态、真实同色紧贴可靠拆分或精度统计。中心估计需要显式顶面假设，方向保持未知。所有候选/诊断位姿均 control_ready=false。

下一步：真实 RGB-D 录制与标注 → 固定回归数据集 → 桌面/高度联合实例分割 → 时序追踪 → 多点标定验收。硬件执行在后续独立阶段开发。
