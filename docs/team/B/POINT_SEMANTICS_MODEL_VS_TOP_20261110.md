# 点语义：model_center vs visible_top_center

对齐 M ACK `be50b37` / `first_placement_review_request.template.json`。

| 用途 | 点种类 | 字段 |
| --- | --- | --- |
| LocalizedReview / 摆放复检侧车 | `visible_top_center` | `b_extensions.top_surface_point_camera_m` + `top_surface_point_kind` |
| 正式 VisualSample / `verify()` | `model_center` | `b_extensions.model_center_camera_m` |

## 硬规则

- 两套点**不是**同一测量；禁止静默回退（缺 `model_center` 时不得改用顶面点，反之亦然）。
- 期望位姿必须与所用点种类一致：顶面期望只对顶面测量，模型中心期望只对模型中心测量。
- 不得把当前观测点当作它自身的期望目标。
- 多 VALID 候选或仅有非 VALID 杂波 → `AMBIGUOUS`，**不是** `EMPTY`。
- `calibration_hash_unavailable` 只是 verify 路径 sentinel，**不是**已批准标定绑定；侧车仍输出 `calibration_hash=null`，候选文件 sha 单独存放。

## 导出入口

```text
python tools/v_verify_field_session.py <bundles.jsonl> \
  --placement-request config/planning/first_placement_review_request.template.json \
  --phase pre_grasp \
  --output docs/team/B/evidence/field_20261110/verify_pre_grasp_handoff_v0.2.json
```

`control_ready` 保持 false。
