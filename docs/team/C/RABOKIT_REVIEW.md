# Rabokit 手册与当前现场接入差异

来源https://www.rabokit.com/manual，读取2026-11-07。页面为动态应用；通过其公开/v1/api/manual/docs目录及docs/<slug>读取body_md。原文仅保存在artifacts供本机审阅，不复制整篇入交接。所读章节lbot_dual_arm、linkerhand_o6、05-interface、06-sensors、rabo_dev_kit；索引显示文档更新日期，并非当前设备验收日期。

## C使用的结论

1. LBot章节get_pose口径为base_link、m/rad；七轴冗余下pose_check本地解与执行端选解可能不同。C向A交明确关节轨迹，不能把位姿预检解当作实际执行全路径。linear在仿真与真机插补方式也有差异，不能用接口同名推断路径相同。
2. 05-interface/06-sensors中，仿真深度为optical-Z、m、无命中NaN，光学轴x右/y下/z前，与项目基础契约相容；但仿真使用理想针孔/仿真时钟，不能覆盖现场335L的K/D、设备时钟或配准验证。用户确认安装数值匹配，不等于有文档未给出的相机矩阵数值。
3. LBot整机手通道与独立USB-CAN手通道反馈能力不同。D不能从整机文档“无反馈”推断现场独立O6无反馈，也不能把单手能力用于整机通道；必须保留adapter/capability版本。具体手指单位/参考位由D审查，不在C内新建转换。
4. 手册描述平台API/ROS桥，不证明当前机器人主机已安装或运行这些节点。没有启动rabo_robolib、控制器、ROS业务节点、任何使能/回零/停止示例。源码P7构造Flash副作用结论仍按现场SDK版本保留，不用另一平台构造API推断安全。

## 用户实测确认

用户表示全部机械安装数值已实测且与厂家一致，接受此声明，不再重复安排这些尺寸测量。结构化记录calibration/installation/user_confirmed_vendor_geometry_20261107.json保存确认来源和厂商左肩安装变换；将vendor_base_link与项目world明确区分。未提供逐点读数/量测不确定度，保持未知。仿真stand的1.2m仍不是独立现场数值。没有在来源中找到实际头部335L到base的矩阵/TCP，不生成假值；后续优先读取已有场景导出TF/标定记录，而非再次要求重复量尺寸。
