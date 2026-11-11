# 线 H 现场 Runbook（2026-11-11）

权威计划：[`docs/TWO_LINE_WRIST_PLAN_20261111.md`](../../TWO_LINE_WRIST_PLAN_20261111.md)。进度 Epic [#27](https://github.com/ANRUNYU/brick-stacking-real/issues/27)。

默认：`executable=false`，`control_ready=false`，`motion_commanded=false`（示教记录）。需要你托举/摆放时，操作员按本节口令确认后再记录。

## 现场前检查

1. 左臂 `can2`、左手 O6、头相机 `CP2L863000KL` 空闲。
2. 右臂/右手失能并已记录停放角。
3. 桌面：固定红块、黑十字放置槽、指定棋盘格 `table_checkerboard_primary`（格长 0.01938 m）。
4. 急停可达；腕部需要 Rest/使能前必须物理支撑。

## #28 示教顺序（需要操作员摆臂/摆手）

每次只改一项：准备角 / 腕姿态 / 闭合速度。

| 步 | 操作员动作 | 记录 phase |
|----|------------|------------|
| A | **失能**下托举左臂到自然垂落附近的安全悬停；手张开 | `hang` |
| B | 托举到红块上方抓取准备姿；手指调到三指 **preshape**（将触未触） | `preshape_at_block`（须含 `block_pose_base`） |
| C | 保持臂姿，手指执行/摆到 **close**；确认三指同时接触、块在指间正中 | `close_at_block` |
| D | 张开手；托举到十字槽上方放置准备姿（手张开） | `place_ready_at_cross`（须含 `cross_pose_base`） |

口令示例：回复「已摆好 hang，可以记录」后再跑记录脚本。

冻结：

```powershell
$env:PYTHONPATH='src'
python tools/h_freeze_grasp_relative.py tests/fixtures/line_h/synthetic_teach_bundle.json docs/team/B/evidence/line_h/grasp_relative_SYNTHETIC.json --relative-version syn-rel-0.1 --pack-version syn-hand-0.1
```

现场真实包替换 synthetic 路径与版本号；`rejects_c49_two_finger` 必须为 true。

## #29 发出 wrist-target

```powershell
python tools/h_build_wrist_target.py <grasp_relative.json> <poses.json> <wrist_target.json> --table-board <table_board.json>
```

`poses.json` 含 `base_block` / `base_cross`，可选 `hang`。输出 `executable=false`。把文件交给线 P（#30）。

临时中继（当前块当 mid，尚无十字放置）：示教齐 `hang` / `preshape_at_block` / `close_at_block` / `handoff_ready` 后：

```powershell
$env:PYTHONPATH='src'
python tools/h_build_provisional_handoff_target.py `
  docs/team/B/evidence/line_h/teach_hang_20261111.json `
  docs/team/B/evidence/line_h/teach_preshape_20261111.json `
  docs/team/B/evidence/line_h/teach_close_20261111.json `
  docs/team/B/evidence/line_h/teach_handoff_ready_20261111.json `
  docs/team/B/evidence/line_h/wrist_target_provisional_handoff_20261111.json `
  --pack-version field-provisional-handoff-hand-0.1
```

输出仍 `executable=false`；`targets` 为 `hang` / `grasp_ready` / `handoff_ready`。

## #31 校验路径后授权抓放

```powershell
python tools/h_check_wrist_path.py <wrist_target.json> <wrist_path.json> --tip-poses <optional_fk.json>
```

仅当 check `ok=true` 且另有现场授权口令后，才可低速：到 `grasp_ready` → 停稳闭合 → 到 `place_ready` → 停稳张开。

## 头摄定位靠机器人一侧 mid（方框+十字）

固定曝光采头机后本地解算（不发运动）：

```powershell
$env:PYTHONPATH='src'
python tools/h_localize_mid_cross_from_rgbd.py `
  docs/team/B/evidence/line_h/mid_zone_box_cross_<stamp> `
  docs/team/B/evidence/line_h/mid_zone_localize_<stamp>.json
```

核对叠加图十字落点；`pose_base_c35` / `mid_zone_poses_base_*.json` 的 `base_cross` 供后续 handoff / `h_build_wrist_target` 使用。C35 仍为 fit-only，`executable=false`。

示教齐且 mid/块视觉位姿齐后冻结：

```powershell
$env:PYTHONPATH='src'
python tools/h_freeze_from_teach_and_mid.py `
  docs/team/B/evidence/line_h/teach_hang_20261111.json `
  docs/team/B/evidence/line_h/teach_preshape_20261111.json `
  docs/team/B/evidence/line_h/teach_close_20261111.json `
  docs/team/B/evidence/line_h/teach_handoff_ready_20261111.json `
  --base-block docs/team/B/evidence/line_h/base_block_<stamp>.json `
  --base-mid docs/team/B/evidence/line_h/mid_zone_localize_20261111_153156.json `
  --relative-version field-mid-rel-0.1 `
  --pack-version field-mid-hand-0.1 `
  --output-relative docs/team/B/evidence/line_h/grasp_relative_field_mid_0.1.json `
  --output-wrist-target docs/team/B/evidence/line_h/wrist_target_field_mid_0.1.json
```

## #32 棋盘格挪桌

```powershell
python tools/h_build_table_board.py <board_inputs.json> <table_board.json> --nominal-table-height-m <H> --camera-extrinsic-hash c35-fit-only
```

`reject_emit_wrist_target=true` 时禁止发 #29/#33 目标。

## #33 不固定块位

头相机更新 `base_block` 后重跑 `h_build_wrist_target.py`；相对姿态与手预设不改。依赖 #17 C35 对尺与 #31/#32。
