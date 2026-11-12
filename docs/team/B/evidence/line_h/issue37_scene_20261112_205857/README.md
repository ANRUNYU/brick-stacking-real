# Issue #37 stationary scene capture (2026-11-12 20:58)

Left arm held in place. Read-only only: head RGB-D + bilateral P7 + left O6. No motion commanded.

## Contents

| Path | What |
|---|---|
| `field/summary.json` | Capture gates / hand SN |
| `field/samples.jsonl` | 68 dual-arm + left-hand feedback rows with host timestamps |
| `field/rgbd/` | 10 registered RGB-D frames + `camera_report.json` |
| `localized/frame_*.json` | Per-frame red-block localize (C35 FIT_ONLY) |
| `scene_packet.json` | Fused packet for P-line MoveIt scene binding |
| `precheck_from_scene.json` | Read-only precheck rebuilt from this capture |
| `planning_request.json` | Refreshed #37 request (start = this capture; goal = 215245) |
| `tools/capture_scene_feedback.py` | Host capture script (also at `tools/`) |
| `tools/review_scene_feedback.py` | Offline fuse script |

## Key numbers (most recent frame)

- Left L8 → grasp_ready distance: **518.324 mm** (wrist J6/J7 drifted vs 20:14 precheck; J1–J5 nearly unchanged)
- Max host feedback↔RGB nearest offset: **≈38 ms**
- Max RGB–depth skew: **≈0.019 ms**
- Left hand SDK percent: `[99.61, 24.71, 99.61, 99.61, 0, 0]` (not URDF rad)
- Red brick median model center (base): ≈ `[0.351, -0.055, -0.505]` m

## Reproduce

```bash
python tools/review_scene_feedback.py \
  --field docs/team/B/evidence/line_h/issue37_scene_20261112_205857/field \
  --localized docs/team/B/evidence/line_h/issue37_scene_20261112_205857/localized \
  --calibration calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json \
  --urdf config/models/p7_left/p7__left.urdf \
  --request docs/team/B/evidence/line_h/left_auto_preposition_20261112/planning_request.json \
  --output docs/team/B/evidence/line_h/issue37_scene_20261112_205857/scene_packet.json
```

Host raw: `/home/qwer/captures/issue37-20261112-205857-ygje`

## Still missing for MoveIt

Desk full polygon/thickness, right-arm collision mesh binding, O6 rad/fingertip envelope for the new path. First live approach still needs separate authorization; this packet does not authorize motion.
