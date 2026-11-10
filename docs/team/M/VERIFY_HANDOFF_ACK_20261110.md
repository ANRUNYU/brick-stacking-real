# M 接收 V aed8a0b：侧车联调与目标请求

V基线：aed8a0b224db3eadfefcc0fb6a7a74c0a8bba856。M前序878347d。此文为离线接口ACK，不是现场定位或执行验收。

## 接收与实现

- 接收 verify_export、v_verify_field_session.py、三组handoff、索引及FRAME_ID_HEAD_VS_C35说明。
- 新增 `planning/verify_handoff_consumer.py`，将V侧车与**原始bundle**逐项核对sample/observation/frame/profile/calibration/epoch/曝光/时钟引用/期望颜色，防止脱离原帧修改侧车。
- 只有有界误差、目标/参考关联和当前标定绑定等字段齐备，才构造已有M的LocalizedReviewEvidence/Inspection；不新造公共contracts。支撑、稳定、邻块为None时继续保留None，不能由scene_consistent推导。
- 消费成功仅表示SHADOW_INSPECTION_READY，正式placement verdict仍UNKNOWN，不能当作permit。

## 真实交付回放

`verify_handoff_index_v0.1.json` 的38帧均消费为BLOCKED：红15 MATCH，绿11 MISMATCH，空桌12 UNKNOWN。缺target/region关联、参考、calibration_hash和有界误差，不造PASS。每条拒绝原因和输入sha256见 `docs/team/M/evidence/verify_handoff_consumption_20261110.json`。

104项相关测试通过：已有M/时钟接口测试+V verify_export测试+M侧车拒绝/完整合成接口测试。正向接口样例为合成绑定，不是已完成真实摆放验证。

```text
python tools/m_consume_verify_handoff.py --output artifacts/m-consume-verify-01.json
```

输出拒绝覆盖历史文件。使用记录输出时间回放，不声称历史数据当前仍新鲜。设备指令0次。

## M给V的目标请求草案

版本化模板：`config/planning/first_placement_review_request.template.json`。

| 字段 | 当前交付 |
|---|---|
| target_id | m-first-red-01，拟议逻辑ID，不代表已经关联到某一实物 |
| slot_id / region_id | m-first-placement-slot-01 / m-first-placement-region-01，拟议逻辑ID，不代表已有场景几何 |
| expected_color | red |
| frame | camera_CP2L863000KL_color_optical_frame |
| association | false，证据ref=null |
| expected pose/point | null，真实目标槽位尚未测量/确认，不能把同一观测点当自己的目标 |
| calibration_hash | null，尚无与当前scene/epoch/profile绑定的确认值 |
| C35候选文件sha256 | a8711b804660ff8888e85e07b836bb336832ab04a31bf5337e7b64157a003461，仅识别候选文件，不等同批准或当前绑定 |

目标位姿的接入步骤：由任务/场景负责人确认实际槽位几何及独立参考；标定负责人交付有效的base/camera/table关系和误差；M将槽位目标变换到相机系并保留原始目标、变换/hash、误差及scene版本；关联负责人提供对象/槽位关联证据后，由V对原始观测调用正式verify。现有十字红块参考及旧head帧的缺项仍按#17/#8处理，不用本次检测反求期望值来通过验证。

## 必须共同确认的两个语义

1. **顶面中心与模型中心不同**：V `bundle_to_visual_sample`优先model_center、无则回退top_surface；M当前Inspection要求visible_top_center。因此模板分别列出placement_review_reference（顶面）与formal_verify_reference（模型中心）。正式接入前应显式固定所用点；不能把顶面期望与模型中心测量比较，或在缺字段时无记录地切换。
2. **三项输入不是post_place PASS充分条件**：target/expected pose/calibration绑定是必要条件；现有verify的post_place还要求before/after关联、动作开始完成时间、正向释放证据、稳定窗口、非过期帧和正确区域。V也不能代替执行端证明动作完成。支撑/撤手/邻块等更完整摆放检查仍由分项证据提供，position_only或released_stable不能冒充全结构验收。

建议V后续保持：场景REJECTED/多候选/遮挡不等于可见空区；缺calibration的sentinel不当真实hash；回退点语义必须显式。M新消费层对此保守拒绝，但不是替代V正式verify入口的完整校验。

## 后续边界

#10继续提供视觉证据，M继续目标/槽位/标定/关联接入。#22/#23保持首抓后的扩展优先级，不要求V抢占。control_ready=false、motion_enabled=false、permit=null，无SSH/CAN/ROS/SDK动作。
