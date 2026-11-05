# 离线实验

运行 `python experiments/scripts/run_offline_validation.py` 生成按命名规范组织的测试报告。脚本调用当前 Python 的 pytest；无 ROS、CAN 或 SDK 实例。

`python -m brick_stacking.app.offline_runner --synthetic` 另行生成候选演练。后续真实录制/动作实验应新增稳定命名的协议和证据，不复制日期命名的测试代码。
