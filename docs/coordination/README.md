# 双臂协同离线框架（2026-11-10）

## 基线与范围

通过GitHub API核实main为caac036f2c6218a11d2d9373501f34dd443cf9eb，并下载该提交的源码快照；Git HTTPS两次超时，不能把旧本地main当最新。工作目录brick-stacking-coordination与视觉实验目录分开，保留UPSTREAM_SNAPSHOT.txt。本轮没有Git对象/分支建立或远程推送，不以快照冒充已创建远程分支。

当前设计v0.3原将双臂列作延后方向；用户本轮明确授权开始搭建，因此新增离线扩展框架，但没有提升单臂或双臂真机能力。视觉已交接，不改视觉模块。不连接SSH、相机、臂/手/CAN，不启动SDK/ROS，不更新第三方代码。

## 模块与已有接口

- coordination/reachability.py：复用BlockPose生成显式xyz+xyzw采样，按臂/位姿ID/动作阶段保存UNKNOWN、UNREACHABLE、CANDIDATE。没有样本不插值，缺证据不推断可达。CANDIDATE必须声明完整阶段路径和碰撞检查及plan_ref；source=mock不代表真正运行了求解器。context含frame、模型/标定/TCP/scene/另一臂状态版本；版本变化令查询失效。地图不直接授予动作许可或实现在线反馈时效检查。
- route_candidates.py：桌面中转点需绑定共同物体位姿、donor放下撤离TCP位姿ID、receiver抓取撤离位姿ID与共享区。两臂阶段地图均有候选才进入候选列表；不声称“供料→中转→目标”整条运输路线已验证，不替代C全路径规划。
- table_relay.py：复用现有execution/HandoffFsm（原逻辑左放右取）并映射为任意实际donor/receiver；启动先RECOVERY，需要新观测重建。完成放置需具名物体占用，完成取出需区域为空、两臂撤离。EMPTY只表示中转区为空，不证明接收手已稳握；持物事务仍归D。
- shared_zone.py：同frame AABB含边界接触也冲突；重叠区域互斥，启动UNKNOWN，显式新鲜清场证据后可预约。UUID fencing token校验持有者；过期保留owner并BLOCKED，故障/重启/时钟回退不自动当物理区域清空。恢复必须故障后新证据和同scene/epoch。
- relay_coordinator.py：组合两者，进入/完成前均校验共享区令牌；组合中途失败统一保留恢复/阻断状态。进程内协调，不是跨电脑分布式锁；生产系统必须单一协调者或另加可靠锁服务，不能各电脑各建manager后宣称互斥。

没有导入或覆盖A/C/D的新执行接口；D公共契约包含PlanResult/Permit/VerificationEvidence，后续需以适配器关联这些真实引用。现有ZoneEvidence缺scene字段，组合入口要求显式scene_version，由调用方负责真实观测来源，不静默把旧证据当当前scene。

## 可运行示例

安装现有项目及开发依赖后，在本目录运行：

```bash
python -m pytest -q tests/unit/coordination tests/unit/execution/test_handoff_fsm.py
python tools/coordination_demo.py --output artifacts/coordination-demo-01
```

输出目录须未存在。demo仅使用虚构mock_table、尺寸与能力固定样例，展示右放左取及区域状态。它不运行IK、碰撞或实际设备，report.motion_enabled=false；地图里的检查标志只是Mock fixture，不能加载到真实动作许可。

## 真正可达性图还需要什么

C提供左右安装/TCP/夹持物变换、关节限位与当前起点、抓放方向、桌面与全机障碍；A提供两侧具名反馈、执行/保持/取消边界，D提供持物状态与预设。地图要覆盖接近/抓取/抬升/转运/放置/撤离，不仅终点IK。持物和另一臂姿态改变均使旧证据失效。采样点之间不可默认连续可达，真实完整路径必须单独求解/校验，定位误差与安全余量分开。

config/coordination.template.json保留所有未知实物参数null/空，不从Mock尺寸或历史相机坐标猜共享区。可选评估不同中转点的耗时/额外抓放风险，优先直接单臂路线；没有合法交集时拒绝，不能靠锁让不可达路线可行。

## 后续里程碑

1. K0：本轮类型/离散样例/双向中转/互斥/故障负例，通过离线软件检查。
2. K1：与C左右路径回调及D场景/持物/Permit适配，输出可追溯真实几何候选；仍不发动作。
3. K2：确认中转区物理位置、落台稳定/颜色/物体身份与两臂撤离证据，重启与租约故障回放。
4. K3：A/C/D共同确认两侧保持/急停/退路、完整碰撞和执行所有者后，受控串行桌面放取实测；不能用进程退出当安全停止。
5. K4：仅在串行可靠且有收益证据后研究区域外并发，不默认实现手递手或双臂同时入区。

本框架未实现分布式一致性、真实碰撞/IK或自动移动到观察/停放姿态；场景不明时阻断，不盲目撤离。测试记录见本目录VALIDATION_20261110.md。

## 发布准备更新（2026-11-10）

用户授权新建分支上传。Git连接仍超时，通过GitHub API重新读取main并取得完整源码快照：`d296447456c7461a01842fe140dd28e19339ff19`。上述caac036为最初开发基线；发布候选已迁移到这里的新主线并重新验证。仅新增协同文件，没有覆盖视觉或其他成员代码。
