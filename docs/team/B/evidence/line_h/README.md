# Line H evidence

- `*_SYNTHETIC.*`：软件管线样例，**不是**现场冻结，**不可**当真机指令。
- 现场 #28 示教记录应另存为不带 `SYNTHETIC` 的文件，并经 `h_freeze_grasp_relative.py` 生成真实 `grasp-relative`。
- 2026-11-11 临时中继：`teach_*_20261111.json` → `wrist_target_provisional_handoff_20261111.json`（`hang`→`grasp_ready`→`handoff_ready`，`handoff_provisional=true`）。手预设见 `hand_preset_pack_provisional_handoff_20261111.json`。尚无块/十字相对冻结，不可当真机运动指令。
- 2026-11-11 头摄 mid 定位（左棋盘下方更清晰方框+十字）：采集 `mid_zone_box_cross_20261111_153156/`；定位 `mid_zone_localize_20261111_153156.json` + `_overlay.png`。更早的 `…145219` 打在旧原点十字上，已作废。线 H：`mid_zone_poses_base_20261111.json`（`base_cross`，C35 fit-only）。
- 2026-11-11 红块定位 + 冻结：`red_block_20261111_154153/` → `red_block_localize_20261111_154153.json`；`grasp_relative_field_mid_0.1.json` + `wrist_target_field_mid_0.1.json`（`hang`→`grasp_ready`→`handoff_ready`，C35 fit-only，`executable=false`）。

工具：`tools/h_*.py`（含 `h_build_provisional_handoff_target.py`、`h_localize_mid_cross_from_rgbd.py`）。Runbook：[`../LINE_H_RUNBOOK_20261111.md`](../LINE_H_RUNBOOK_20261111.md)。
