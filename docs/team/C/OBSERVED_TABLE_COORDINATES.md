# 相机识别、桌面建系与机械臂外参的区别

2026-11-08，C33，C1-01/C1-02/C1-03，M1/M2a。50×50×50 mm 已作为用户实测尺寸使用，不再要求重复测量。无标记立方体可以建立几何坐标代表；不需要为了相机定位先完成笔尖TCP。

相机实际可观测：配准RGB-D中的桌面法向/表面和方块相对相机的位置。机械臂执行还需要同一时刻的 T_base_camera；桌面或50mm尺寸本身不包含机器人基座的位置。T_base_table=T_base_camera T_camera_table，缺失项保持null，禁止填单位阵。

## 当前实现

复用既有 fit_table_plane、CameraFrame、BlockDetection、localize_top_face、BlockPose、RigidTransform 和 backproject。新增 localization/table_coordinates.py 构造局部观测桌面系；observe_table_cube.py 从明确标注的桌面区域/单块顶面边界提取几何并输出实拍叠图。没有另立公共模型或修改B的分割接口。

桌面原点：指定像素射线与拟合桌面的交点；+Z为朝外法向；+X为相机光学X轴在桌面上的投影；+Y=Z×X。该 frame 名称 table_camera_defined_C33，不能当已验收左臂基座系。相机移动后重建/失效，桌面完整边界与工作区安全边界未验收。

方块：明确“平放桌面”假设，用实测边长0.05m及四个顺序顶面边界射线，得到一个几何坐标代表。无标记规则方块的桌面内转角具有pi/2对称性，不能声称恢复了永久面编号。现有BlockPose仍orientation_xyzw=null、control_ready=false；另附具名代表RigidTransform用于几何分析。中心z=0.025m由平放50mm模型给出，不是额外实测精度证据。

## 最小调用与验证

设置PYTHONPATH=src：

```powershell
python tools/observe_table_cube.py FRAME.npz CONFIG.json OBSERVATION.json --preview PREVIEW.png
```

CONFIG显式包含camera_serial、edge_m=.05、edge_source、roi_source、rests_on_table、table_polygon_xy、top_corners_xy、table_origin_xy、top_erosion_px、plane_threshold_m、max_holdout_m、max_edge_error_m、max_adjacent_edge_abs_cos、table_frame、candidate_id、version、color。真实配置保存在evidence/observed_table_cube_C33.json的每帧config，不能改source冒充实测。

桌面训练/检查像素分离；保留全部检查深度异常值，不以RANSAC训练内点充作验证。检查方块顶面深度是否接近50mm高度、顶面边长和直角约束。失败也可输出诊断坐标，但始终approved=false/motion_enabled=false；T_base_camera/T_base_table为null。

测试命令：`artifacts/planning_venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp-c33-final`，289 passed。新增右手系/原点/已知尺寸/退化拒绝测试，以及复用BlockPose和保持synthetic来源的记录式集成测试。preview已实际渲染复核。

## 本次真实结果

对 c32_clock_probe01 三帧已录RGB-D进行分析，无新增硬件动作。第一轮2mm RANSAC/90%支持未通过；保留失败。第二轮仅为诊断，拟合阈值3mm，独立检查门槛仍3mm；三帧总体全部FAIL，没有批准。

右侧红块在此局部桌面系的中心候选约(-0.255,+0.083,+0.025)m，25mm高度依赖平放模型。顶面实测中位高度48.999–49.469mm；顶面独立深度最大误差3.564–6.222mm，手选顶面边界对应边约44.8–50.5mm，可能存在边界/倒角/测量误差，不能擅自改50mm实测尺寸。桌面检查P95约2.48–2.64mm，但存在约0.756–0.782m的孤立深度异常，全部保留，因此max门槛FAIL。这不是可执行目标。

实拍图：artifacts/c_real_calibration/c33_table_cube_preview.png；完整结果/配置/原帧SHA：evidence/observed_table_cube_C33.json。原始帧不进入源码ZIP。

## 交接与剩余依赖

|合并点/接收方|可用交付|仍缺|
|---|---|---|
|M1/M2a B|ROI/provenance、桌面系构造、BlockPose兼容结果、训练/检查误差及帧SHA|可靠自动分割/边界、深度异常处理及独立精度证据|
|M2a A|T_camera_table和相机内目标候选，未知T_base_camera明确null|不能下发；仍需相机—左臂对应观测和完整七轴执行上下文|
|M3/M4 D|50mm平放模型、桌面原点/轴定义、方块对称性与候选代表矩阵|稳定实际抓握、完整场景/桌面边界、真实base变换和释放验收|

手托联合标定已准备SDK曝光时间配对插值工具，不再要求整段5s绝对静止。此步骤仍需物块与已知机械臂参考段之间的刚性关联或其他独立base参考；单独把块拿到相机前只会改善相机内观测，不会自动补出base变换。
