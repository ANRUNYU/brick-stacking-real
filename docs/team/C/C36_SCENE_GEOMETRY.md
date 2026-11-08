# C36 当前桌面 → 左臂基座 → 抓放几何

C1-04/C1-05/C2-01/C2-03，M2a/M3/M4。使用当前头部相机实拍第一帧和用户接受的C35拟合外参，不再增加验证组或重复哈希审查。

- 近处黄块基座中心约(0.41584,0.05257,-0.51426)m，距基座原点0.663m。
- 远处红块基座中心约(0.58123,-0.27609,-0.50737)m，距基座原点0.819m。
- 距离仅用于候选排序，不能据此宣称IK可达。两个目标均为手选ROI的frame-local候选，不替代D的持久block_id。
- 复用cube_face_grasps，各生成2个相向面抓取几何。5mm侧间隙/80mm接近距离沿用既有明确synthetic示例，等待D用真实预设和手部几何替换；不是实测安全参数。
- 复用build_stacking_slots，以用户50mm尺寸生成红4、黄3、蓝2、绿1共10个槽位，支撑DAG保留。空白桌面候选落点来自像素(600,630)与当前桌面交点；不是已提交场景。
- 未用单位阵补TCP。tool_release_goal=null；IK=NOT_CHECKED、joint_trajectory=NOT_GENERATED、full_collision=UNKNOWN，motion_enabled=false。

原3mm传感器内部诊断的最大桌面误差3.366mm、顶面误差3.315mm原样保留，不把用户接受10mm拟合误差改写成全部像素/放置精度均已验收。抓放与十块实机尚未执行。

## 调用

```bash
python tools/c_scene_geometry.py calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json docs/team/C/evidence/table_observation_C36.json RECORDED_frame_000.npz calibration/examples/c_scene_geometry_design.json artifacts/C36_geometry.json
```

原帧在机器人/home/qwer/c_calibration_runs/c36_scene01/frame_000.npz；本地artifacts/c_real_calibration/c36_scene01/。已实际运行一次，输出2目标、各2抓取候选、10槽位；不扩大测试。结果见evidence/scene_geometry_C36.json。工具复用既有RigidTransform、BlockPose、桌面几何、抓取及槽位接口。

## 下一项真正需要的输入

|来源|最小内容|用途|
|---|---|---|
|A → C，M2a/M3|左臂J1…J7具名rad、新鲜host_monotonic/epoch、映射/控制限制版本|从实际起点做IK与带时间关节路径。当前五轴标定读数不能补成七轴|
|D → C，M3/M4|能稳定夹50mm块的左O6预设、percent/raw单位、版本、实际手几何/持物关系|把几何抓取帧换为真实flange/TCP目标；不能把临时L5标定块偏移当抓握偏移|
|B/D → C，M3/M4|具版本的目标/槽位及桌面、邻块、机器人/手/持物碰撞场景|完整路径与碰撞检查；不能把目标距离或局部包围盒当完整避碰|

这些输入齐备后继续实际抓放联调；本次未发机械臂或手指动作。
