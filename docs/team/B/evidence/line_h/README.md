# Line H evidence

- `*_SYNTHETIC.*`：软件管线样例，**不是**现场冻结，**不可**当真机指令。
- 现场 #28 示教记录应另存为不带 `SYNTHETIC` 的文件，并经 `h_freeze_grasp_relative.py` 生成真实 `grasp-relative`。
- 2026-11-11 临时中继：`teach_*_20261111.json` → `wrist_target_provisional_handoff_20261111.json`（`hang`→`grasp_ready`→`handoff_ready`，`handoff_provisional=true`）。手预设见 `hand_preset_pack_provisional_handoff_20261111.json`。尚无块/十字相对冻结，不可当真机运动指令。

工具：`tools/h_*.py`（含 `h_build_provisional_handoff_target.py`）。Runbook：[`../LINE_H_RUNBOOK_20261111.md`](../LINE_H_RUNBOOK_20261111.md)。
