# 头部相机采集与型号核验

日期：2026-11-06，范围仅相机视觉，无 CAN/机械臂/手操作。

## 权限与环境

独立 Linux 环境 /home/qwer/brick_vision_venv，pyorbbecsdk2 2.1.3，SDK 2.10.6。首次打开失败。确认 /dev/bus/usb/002/013 属于 2bc5:0804 335L、序列号 CP2L8630008J，用户明确批准后仅对此节点为 qwer 设置临时 rw ACL。两台其他相机权限未变；未安装持久 udev 规则或更新固件。

## 实测采集结果

- 相机：Orbbec Gemini 335L，CP2L8630008J，固件 1.4.60，USB3.2。
- RGB 640×480 RGB / 15 Hz；Depth 640×480 Y16 / 15 Hz。
- 软件 D2C 配准及 BROWN_CONRADY_K6 去畸变，读到的深度尺度为 1 mm/raw，保存为米。
- 10 组 RGB-D，图像时间戳单调递增；报告中 RGB/depth 差约 0.001 ms，是 SDK 时间戳差，不是独立测出的曝光同步精度。
- 全图有效深度比例 89.31%–89.73%；这一比例不能代替积木 ROI 深度质量或毫米精度。
- fx=369.363983、fy=369.274536、cx=318.157623、cy=241.219101（当前分辨率设备内参，非世界外参）。
- 采集完成 CAPTURED，errors=[]、cleanup_errors=[]，相机流已关闭。

Linux：/home/qwer/captures/vision-head-20261106-02。
Windows：artifacts/vision-head-20261106-02，原始 ZIP 同名，含 10 个 NPZ、彩色/深度预览和 camera_report.json。

已查看彩色与深度预览，桌面及两排积木可见，有较强窗边光照/阴影。Windows RecordedCamera 能读取 10 帧并调用现有检测器；真实回放结果 INCONCLUSIVE。默认合成 profile 在全图产生大量背景候选（10 帧合计 1 UNAMBIGUOUS、437 AMBIGUOUS、201 INVALID_DEPTH），不能将这些累积候选当作物块数量或识别成功。

后续先限定桌面/供料 ROI、调整实拍 HSV/深度与几何条件、建立标注后评估，不宣称已完成抓取定位。

## 其他两台相机型号

sysfs：AY6M863005Z 与 AY6M86300EM，均为 VID 2bc5 / PID 0670；SDK 列表显示 Gemini2。官方源码 commit f5d59930ccb9a189f200e58fba4e2ae42664792d 的 src/device/gemini2/G2DeviceInfo.cpp 将 0x0670 明确映射为 Gemini2。

因此当前应按 Gemini2 识别记录，而非仅将名称当作 335 的别名。两台的 SDK 完整身份/固件、左右角色和流能力仍未验证；设计中腕相机为 335 的假设需要团队核对后修订，不能复用 335L 参数。尚未请求或更改这两台的设备权限。

## 离线测试

新增相机编码/深度单位/畸变拒绝与 unknown 保留测试 7 项通过；视觉专用套件 35 passed、1 deselected（明确排除 Mock 设备用例），记录 Verification_VisionCore_PYTHON_202611061532。没有运行机器人控制测试。
