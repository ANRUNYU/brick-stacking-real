# M：V 最新交付接收、摆放检查接口与尺量联调

基线：V `24acf856`；M 前序 `47b6aa8`。独立本地快照开发，未覆盖其他成员目录。main 当前 `b8395ce` 的主机监控变更不在本轮修改范围。历史 H0 报告保留原采样语义，不能用新的时钟研究给旧帧补造时钟字段。

## 本轮完成

- 接收 V 最新 H0 ACK、独立尺量、时钟界及三组真实复检导出。
- `planning/placement_bridge.py` 增加来源/相机/帧/epoch/profile/主机启动周期/曝光时钟引用检查，按误差界检查记录输出时的曝光龄期。
- 增加 `LocalizedReviewEvidence → Inspection` 的影子接口：要求明确目标关联、顶面中心语义、标定 hash 和有界位置/高度/角度误差，不把 scene_consistent 当作支撑、稳定或已撤手。
- `localization/ruler_reference.py` 要求独立十字→基座桥接，保留测量误差与桥接在目标点的误差界，不从单个红块反拟合该变换。
- `m_ruler_validation.py` 对旧 `head` 帧严格拒绝隐式别名，同时提供显式已确认相机帧变换入口；原始 V 样例不修改。
- C35 诊断保留新帧实际携带的时钟界/曝光→输出测量值，标注为记录最大值，不当未来延迟保证。PlanBundle freshness 字段改用中性名称并标明 exposure/receive 来源，未冻结策略仍阻止执行。

## 真实导出回放结果

| 记录 | 帧数 | 候选颜色诊断 | 来源检查通过 | 摆放结论 |
|---|---:|---|---:|---|
| 单红 pre_grasp | 15 | 15 MATCH | 13 | 15 UNKNOWN |
| 空桌 | 12 | 12 UNKNOWN | 0 | 12 UNKNOWN |
| 单绿错色 | 11 | 11 MISMATCH | 9 | 11 UNKNOWN |

每段开头两帧未通过场景连续确认，所以未计入来源通过；不是删去这两帧使样例“全通过”。空桌导出的场景为 REJECTED，不能据此证明目标区域可见且已清空，更不能证明抓起成功。错色只是单候选颜色与期望不符，尚无目标槽位关联，故不是正式 post_place FAIL。三组均没有填充摆放误差、接触或稳定证据，不能报告 placement PASS。

回放时 now 使用每帧记录的 output_monotonic_s，仅复核记录时状态，不代表这些历史帧在现在仍新鲜。2.656 s 是 V 当前诊断门，不是本轮替团队冻结的生产 freshness。约 1.686 ms 是 V 接受用于观测 timing 的界，control_ready 仍 false。

输出（含输入 sha256 与逐帧结果）：

- `docs/team/M/evidence/placement_field_replay_20261110.json`
- `docs/team/M/evidence/ruler_handoff_validation_20261110.json`

## 尺量交接：已收到参考，但尚不能发布基座对尺通过

确认接收独立红块顶面参考：`table_black_cross_20mm` 下 `[0.172, 0.079, 0.050] m`，估计误差 2 mm。五帧绑定观测的顶面中位为约 `[-0.008573,0.239100,0.788988] m`。

实际存在两项不同的坐标关系缺口：

1. **相机帧语义**：绑定导出使用 `frame_id=head`；C35 使用 `camera_CP2L863000KL_color_optical_frame`。需要生产方确认是否同原点同轴，或提供 `T_c35_camera_head`。不能静默改名为相同帧。此批 `epoch=ruler_bind`、host_receive/exposure/clock bound 为 null，是历史诊断样例；后续已验收时钟的记录不能补给这一批。
2. **桌面参考到基座**：需独立确定 `T_L_arm_root_table_black_cross_20mm`，或直接提供 `L_arm_root` 下的红块顶面参考与桌面法向。J1 候选的原点关系与完整轴向尚未被确认，只有 J1 的一个位置不能确定旋转。可用经验证的安装/模型坐标关系配合测量，或足够的独立非共线对应点求取并另设验证点；禁止用当前红块加 C35 反求桥接再验同一红块。

尺量记录中 J1 桌上高度同时有 495 mm 与地面差推导 502 mm，差 7 mm；不能只采用其中之一而忽略误差预算。十字到立柱水平闭合误差小，只说明这部分距离自洽，不证明上述坐标关系。

在 J1=基座原点的**未确认假设**下，尺量红块到 J1 距离约 0.69021 m。当前未确认 `head` 与 C35 光学帧关系，报告不计算对应的基座距离；即使两距离以后吻合，也不能替代平面≤10 mm、法向高度≤8 mm的独立验收。

## 桥接输入与复现

```text
python tools/m_review_field_replay.py --output artifacts/m-review-replay-01.json
python tools/m_ruler_validation.py --output artifacts/m-ruler-01.json
python tools/m_ruler_validation.py --camera-frame-bridge CAMERA_BRIDGE.json --bridge CROSS_BASE_BRIDGE.json --output artifacts/m-ruler-bridged-01.json
```

输出文件须未存在。两种 bridge 均无默认矩阵：

- CAMERA_BRIDGE：`source_frame=head`、`target_frame=camera_CP2L863000KL_color_optical_frame`、4×4 `matrix`、`verified=true`、`version`、`evidence_ref`。
- CROSS_BASE_BRIDGE：`source_frame=table_black_cross_20mm`、`target_frame=L_arm_root`、4×4 `matrix`、`independent=true`、`verified=true`、`version`、`evidence_ref`、`point_error_bound_m`（包含旋转在目标处引入的误差）。

这些字段是调用方交付证据的声明，不是程序证明了现场几何。若只是同帧别名，也需有生产方确认依据后才能显式给出单位矩阵；合成测试里的单位矩阵不构成现场证据。

## 验证与下一步

88 项相关测试通过：M coordination 及受本次 V 时钟更新影响的三组 V 接口测试。包含真实导出回放和合成桥接/缺项/版本/时钟/矩阵拒绝测试；数学合成参考不是物理误差验收。

下一步：V 确认旧 head 帧含义；M/标定负责人提供独立十字→基座关系及误差；再运行逐点对尺，仍不扩大原预算。另由 V 提供槽位/目标关联、有界局部误差与支撑/稳定/撤手结果，才能进入影子纠偏决策。腕相机观察位、真实接触响应与执行 Gate 仍待实现/验收。

本轮无 SSH、ROS、CAN、SDK 或硬件运动，commands_sent=0、permit=null、motion_enabled=false、control_ready=false。
