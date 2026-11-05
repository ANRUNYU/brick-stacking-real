# v1 配置约束

加载器 `runtime/config_loader.py`：schema_version=1；只接受 offline、dry_run=true；运行模式三选一；人工恢复标记为布尔值，自主试跑/比赛禁止人工恢复。

视觉参数由 BlockDetector 校验正值、有效比例、深度区间。HSV H 范围 0–179，S/V 0–255。所有 defaults 数值是合成测试起点，不是实测相机量程或认可精度。nominal_edge_m 是先验，不等于实测边长。

其他设备/标定参数未确认，因此没有给可执行安装矩阵、CAN 配置或手势默认值。后续采用独立设备/相机配置时扩展 schema，当前不声称已实现完整设计配置。
