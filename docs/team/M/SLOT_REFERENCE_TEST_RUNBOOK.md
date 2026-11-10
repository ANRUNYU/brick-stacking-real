# 黑色十字参考输入采集测试

此入口只枚举并采集头相机RGB-D，不运行积木检测，不访问ROS/CAN/臂手SDK，不执行动作。十字目标已由用户确认；目标相机系位置、标定有效性、误差、红块关联仍待参考数据处理，采到原始帧不代表验收通过。

## 现场条件

十字完整可见、桌面标记附近无遮挡；保持相机与基座/桌面不动。先与其他成员确认头机空闲；若设备占用则停止并协调，不杀进程、不改设备权限。默认头机CP2L863000KL，若枚举不匹配先核对，不自动切换设备。

## 在包含本提交的仓库根目录运行

预览（无设备访问）：

```bash
/home/qwer/brick_vision_venv/bin/python tools/m_slot_reference_capture.py --output /home/qwer/captures/slot-reference-01
```

确认条件后，仅相机采集：

```bash
/home/qwer/brick_vision_venv/bin/python tools/m_slot_reference_capture.py --execute --marker-clear-confirmed --output /home/qwer/captures/slot-reference-01
```

脚本不要求pip安装项目包，复用同仓库orbbec_camera_probe.py。固定请求640×480/15Hz，不暗中回退；默认10帧，单次子程序最多90秒。保留SDK默认曝光/自动稳定预热，不提供绕过稳定预热的开关；灯光闪烁/设备不支持/权限/占用等导致失败时如实记录，不尝试修权限。新输出目录和zip均须不存在。

成功返回CAPTURED_REFERENCE_INPUTS_PENDING_ANNOTATION；失败退出码2，保存FAILED原因。两者均打包zip：inventory及rgbd的camera_report、原始npz/预览、stdout/stderr、slot_reference_capture.json及输入hash。提交zip或失败日志即可，不需复制整段终端历史。默认仅创建诊断文件，不修改仓库配置和原始标定。

## 后处理与后续测试

由V/标定成员标注十字中心及像素坐标约定/误差，估计桌面法向与平面误差，并核验积木边长。M据独立十字参考构造两种点的相机系期望，绑定当前SN/profile/scene/epoch和标定证据，再出红块居中与已测偏移的对照采集请求。此入口**不自动定位十字，不求桌面平面或相机期望**，这些输出保持null。

没有真实动作的人工静态对照只验静态视觉，不填写action_finished/released来伪造post_place；真实抓放仍须原T1–T5与执行证据。
