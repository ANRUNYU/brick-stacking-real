# 头相机 `frame_id` 与 C35 光学帧

日期：2026-11-10  
对象：V ↔ M 对尺 / 摆放复检  
结论：**禁止把历史 `head` 与 C35 光学帧静默当成同一帧。**

## 现行在线导出（2026-11-10 现场 verify_*）

`ObservationBundle.rgbd.frame_id` / `blocks[].frame_id` 使用：

```text
camera_CP2L863000KL_color_optical_frame
```

这与 C35 候选标定使用的颜色光学帧命名一致。新采集路径应继续写该字符串，不要改回 `head`。

## 历史 / 诊断别名

部分更早尺量绑定样例曾使用 `frame_id=head`（或文档口语 “head”）。  
这些记录：

- **不能**在代码里 `rename` 成光学帧名后直接喂 C35；
- 若确认同原点同轴，须由生产方提供显式 `CAMERA_BRIDGE`（单位矩阵亦可，但必须 `verified=true` + `evidence_ref`）；
- 若未确认，M 应保持拒绝隐式别名（PR #21 / `m_ruler_validation.py` 行为正确）。

## V 交付约定

| 场景 | `frame_id` |
|------|------------|
| 在线 `observe` / 新现场 jsonl | `camera_<SN>_color_optical_frame` |
| 旧 `ruler_bind` / 未桥接历史包 | 保留原文；报告中标注需 bridge |

`control_ready` 不因本说明变为 true。
