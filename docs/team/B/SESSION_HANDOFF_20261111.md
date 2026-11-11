# 会话交接 · 2026-11-11

分支：`codex/v-vision-20261110` → PR [#24](https://github.com/ANRUNYU/brick-stacking-real/pull/24)（CI 绿、可合入 main）。  
Issue：[#10](https://github.com/ANRUNYU/brick-stacking-real/issues/10)。  
约束：`control_ready=false`；默认不开臂 / 不 `--enable-motion`；不大轨迹运动。

## 当前结论

| 层级 | 状态 |
| --- | --- |
| 视觉 pre_grasp | **就绪**（`vision_pre_grasp_ready=true`） |
| dry-run 抓取入口 | **就绪**（`dry_run_grasp_entry_ready=true`） |
| 正式抓取入口 | 默认 **否**；双重 Rest attest + Mock/草案下可证明 `formal_grasp_entry_allowed=true` |
| 真机运动 | **否**（`control_ready` 硬 false） |

## 刚完成的现场视觉/影子/dry-run 测试

1. 操作员放好十字上红块后，主机 `qwer@10.157.173.135`（密码见历史会话；用 paramiko）短采：  
   `~/captures/slot_contrast_s140_20261111_082359`  
   固定曝光 100 / gain 16 + `head_slot_contrast_s140.yaml`。
2. 结果：**6/6 VALID red**，4/6 `scene_consistent`；xy≈6.4–7.2 mm。
3. 本机证据：  
   - 原始：`docs/team/B/evidence/field_20261110/slot_contrast_s140_20261111_082359/`  
   - 链路：`docs/team/B/evidence/field_20261110/_chain_test_20261111/live_*`  
4. 影子：4 PASS / 2 UNKNOWN（warmup）；4× `SHADOW_INSPECTION_READY`。

## 关键路径 / 文档

- 进度：`UNIFIED_SLOT_PROGRESS_20261110.md`、`PRE_GRASP_GATES_20261110.md`、`HOST_CONTROL_READY_20261110.md`
- 门禁审计：`formal_grasp_entry_audit_20261110.json`
- J6/J7 硬阻塞：`J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md`
- 合入清单：`MERGE_TO_MAIN_CHECKLIST_20261110.md`

## 下一会话建议

1. 若合代码：审/合 PR #24（已含 `host_monitor` merge from main）。
2. 若继续真机抓取：需厂商 J6/J7 **纯只读**协议，或显式授权 Rest 取角（腕失持）+ live Permit / host 抬升；**勿**把 dry-run 当可执行运动。
3. 再采：SFTP 同步 `src/config/tools` 后跑 `orbbec_camera_probe.py`（`--fixed-color-exposure 100 --fixed-color-gain 16 --observe-profile …/head_slot_contrast_s140.yaml`）；主机缺 clock study 文件时本机 `attach_accepted_timing_bound` 补齐。
4. 勿提交：`slot_contrast_*214000.zip`、未跟踪 `slot_reference_*` 展开垃圾、`fail212542*`（已 gitignore）。

## 主机操作备忘

- SSH：`qwer@10.157.173.135`（BatchMode 无密钥；用 paramiko 密码）
- venv：`~/brick_vision_venv`
- 仓库同步目录：`~/brick-stacking-real`
- 头机 SN：`CP2L863000KL`
