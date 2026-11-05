# 离线 RGB-D 格式 v1

每帧一个 `.npz`，用 numpy load 的 `allow_pickle=false` 加载，不保存 Python 对象。

| 字段 | 约束 |
|---|---|
| rgb | H×W×3 uint8，RGB 次序 |
| depth_m | H×W，米制 optical-Z；无效值为 NaN 或非正数 |
| k | 3×3 内参，零 skew，最后一行为 0/0/1 |
| metadata | Unicode JSON 标量，字段如下 |

```json
{"camera_id":"head","frame_id":"head_camera_color_optical_frame","stamp_s":12.3,"clock_domain":"recording_epoch_1","source":"real_measured","registered":true,"rectified":true,"depth_unit":"m"}
```

以上是格式示例，不是真实拍摄参数。真实毫米深度必须由采集适配器按设备报告的尺度换算，保留原始尺度记录；不得通过数值大小自动猜测。畸变图必须先校正；RGB/depth 先同步并配准，标记 true 应由采集流程提供证据。

可用 `brick_stacking.app.offline_runner.save_recording(path, frame)` 写入。直接 rosbag2 读取、CameraInfo 转换和时间同步采集将在实际 ROS 2 版本确认后实现。

合成来源为本项目 `synthetic_frame()`：四个孤立 20×20 面和一个 40×20 同色紧贴面，K 焦距 200 px、面深度 0.5 m。只验证保守候选行为；不评估现实相机、透视、反光或定位精度。
