# Changelog

## 2026-11-09 — 完成左腕相机手眼标定（C48）与左爪持块抓取偏移标定（C49）

- 定位并解决 C37 棋盘格深度差问题：实测确认 A4 打印棋盘格真实边长为 19.38 mm（19.30~19.47 mm），RGB-PnP 与激光深度误差 < 0.2 mm。
- 新增多角点腕部相机手眼标定求解器 wrist_camera_calibration.py 及单测，完成真机 6 组静态采样并输出 C48_left_wrist_fit_only_user10mm_20261109.json（静止 5 组中心 RMSE = 8.63 mm）。
- 完成左臂 L8_Link 到 50 mm 木块的抓取偏移与左手 O6 抓取角度预设标定，输出 C49_left_grasp_offset_candidate_20261109.json（consistency: PASS，偏移范数 129.3 mm）。
- 整理标定索引 calibration/README.md 与交接文档 docs/team/C/HANDOFF_20261109_CALIBRATION_COMPLETE.md。

## 2026-11-07 — 两阶段团队计划与接口审计

- 导入完整日期交付、36项任务、合并点与验收入口。
- 衔接现有目录，补实测CAN/O6/电机/三机身份，腕机更正Gemini2。
- 保留离线代码与历史设计；本次未进行真实硬件动作。


## 0.2.0 — 2026-11-05

独立实现离线任务骨架：可配置槽位/支撑、单臂选砖和 Mock 事务、验后提交、有界失败恢复、最终位置窗口、交接互斥纯逻辑。新增 Windows→Ubuntu 24.04/Jazzy 部署说明、只读环境检查、源码 ZIP 和离线 CI；未接硬件、未发布远端、未声称 Linux 已实测。

## 0.1.0 — 2026-11-05

独立 Python 离线基础：输入/检测/诊断位姿契约、TF 数学、深度反投影、平面与高度图、保守颜色候选、NPZ 回放、Mock、运行记录、官方 URDF/SDK 审计。没有硬件控制实现或真机验收声明。
