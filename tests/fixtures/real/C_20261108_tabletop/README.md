# C真实录制桌面最小复算样例

来源：2026-11-08，真实头部Gemini335L CP2L863000KL，原采集c32_clock_probe01。原流1280×800@15，配准/去畸变RGB和米制深度；此目录是离线裁剪545×280，**不是设备流profile**。

- `camera/frame_000..002.npz`：原图裁剪矩形[x=575,y=410,w=545,h=280]，去除无关人物区域，RGB/深度像素未改。K的cx减575、cy减410；光学射线与原图一致。
- 每帧metadata：原始SHA、原始K/shape、派生profile、裁剪来源、原设备stamp与clock_domain、主机接收时间、SDKdevice/system/global时间和host桥接。时钟语义不同，不能直接相减或换名。
- `camera/camera_report.json`：原流profile与时钟记录保留，单独标明派生图像尺寸。SDK到达时间不等于曝光时间；时间误差界仍未知。
- `joint_cycles.json`：当次98组左can2、61–65 raw06位置读数，rad与host_monotonic/boot epoch；不是七轴状态。仅位置READ，无Rest/使能/目标/回零/清故障/Flash。
- `roi_config.json`：手选清洁桌面和右侧红块顶面；50mm来自用户尺量。裁剪后ROI及原点像素已平移，`pixel_partition_offset_xy`保留原训练/检查像素相位。
- `sample_manifest.json`：输入文件SHA256及限制。输出不属于有效标定样本，base外参/TCP未知。

复算命令见[交付入口](../../../../docs/team/C/README.md)。该次录制没有装在机械臂上的方块入镜，因此不能用于相机—左基座联合求解。几何检查预期FAIL（保留深度异常点和边长偏差），曝光时间插值预期PROVISIONAL，动作开关必须false。

裁剪前后三帧的桌面变换和方块中心已对照，差异小于1e-12；这证明裁剪/内参/像素分组处理一致，不证明相机绝对测量精度。平放50mm模型的中心高度25mm是明确假设，不是新增测量。
