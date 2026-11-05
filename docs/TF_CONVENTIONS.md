# 坐标与模块接口

- `T_A_B` 将 B 中列向量映射到 A，组合为 `T_A_C = T_A_B @ T_B_C`。单位 m/rad，四元数（未来输出）为 XYZW。
- optical：X 右、Y 下、Z 前。depth 是 optical-Z，不是斜距。
- `world` 是经定义的公共参考，不要求外部绝对定位。未知相机→基座关系不能用单位矩阵补齐。
- 本版 `RigidTransform` 检查 SO(3)、frame 链、来源、时间。动态链必须同一时刻/时钟域；静态变换以 stamp=null 明示。
- `approved=true` 需要 `source=real_measured` 和 calibration_id；这只是数据一致性检查，不是审批/安全授权系统。本版没有任何真实执行入口。
- `BlockDetection.surface_point_camera_m` 是可见面代表点；不是积木中心，不保证为该面几何中心。
- `localize_top_face` 仅在显式顶面假设、单位桌面外法向、边长、对应 TF 下减去半边长求诊断中心。遮挡、斜面、非正视等不能套用此假设。
- 方向不可观测时保持 null，不捏造 identity quaternion。frame-local candidate_id 不等于跨帧 object ID。

接口用途：CameraFrame→视觉；BlockDetection→定位；BlockPose→后续场景模块；Hardware Protocol→未来设备适配。当前没有网络端口，没有 ROS publisher，没有实体执行方法。ROS bridge 应独立放在 ros2_ws，待部署与消息契约明确后增加。
