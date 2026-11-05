# 测试命名

源码 `test_<behavior>.py` 固定命名。运行记录为 `<Objective>_<Object>_<InterfaceCode>_<YYYYMMDDHHmm>`，相同分钟追加 `_R02`。默认 Asia/Shanghai（固定 UTC+08:00），manifest 保存带偏移 ISO 时间。

当前接口代码：RGBD=图像/深度数据契约；TF2=坐标变换语义（不代表本版启动 TF2 节点）；MOCK=纯软件设备替身；PYTHON=Python 测试套件。ID 尚未定义，拒绝使用。

结果枚举 PASS/FAIL/INCONCLUSIVE/SKIPPED/ABORTED。合成或 Mock PASS 不属于平台/真机成功。无标注回放为 INCONCLUSIVE。
