# 双臂协同框架首轮离线验证

日期：2026-11-10；基线main caac036f2c6218a11d2d9373501f34dd443cf9eb，API读取确认。Git连接两次超时，源码通过认证API快照取得，未建立/推送Git分支。新增内容单独位于brick-stacking-coordination，不覆盖两份视觉项目目录。

## 完成内容

- 显式xyz/方向离散样本、双侧/动作阶段可达性证据容器、上下文版本失效与中转点候选筛选；未执行真实IK/碰撞求解或输出实机可达区域。
- 复用现有HandoffFsm的双向桌面放取封装；STARTUP→RECOVERY→新观察重建，不默认物理区域为空。
- 同参考系重叠AABB互斥、单进程令牌、过期保留owner、故障/时钟回退/重启阻断及观察后恢复。
- 协调器组合FSM与租约，进入/完成时复核令牌；完成失败不自动清锁。没有真实动作执行端，也不自动退让。

## 结果

命令：python -m pytest -q tests/unit/coordination tests/unit/execution/test_handoff_fsm.py -p no:cacheprovider --junitxml artifacts/coordination-junit.xml

18 passed。覆盖位姿采样、仅IK拒绝、未知/不同阶段/版本失效、双方候选、重叠互斥、并发竞争只有一个获准、租约过期、旧令牌、场景变化、时钟回退、重启、双向完整桌面中转、失败退出保留锁及复用的3个旧FSM用例。未运行其余设备/视觉测试；未修改旧FSM。

Mock演示命令：python tools/coordination_demo.py --output artifacts/coordination-demo-20261110-01

结果：右放左取最终EMPTY，共4个阶段事件；motion_enabled=false、hardware_accessed=false、actual_reachability_verified=false。JSON中路径/碰撞标志为合成fixture，不是实际运行求解器的结果。没有相机/SSH/SDK/CAN或臂手访问。

## 边界和后续

共享区是抽象AABB，实际包络需C将手/持物/相机/线缆及误差余量纳入路径扫掠验证；不使用Mock盒子尺寸部署。物理区域clear不是仅TCP点在盒外，必须结合全臂/持物几何与新鲜证据。锁服务仅进程内，不能据此许可多电脑独立执行。地图候选不是permit，完整供料到目标路线、持物确认、真实停止/保持均未验收。

下一步对接C的左右路径/碰撞结果和具名场景，A/D的两侧状态与Permit、持物事务；补只读几何样例和事件日志适配，再由团队决定是否进入受控串行实测。视觉由其他成员接续，本轮不改变其接口实现。

## 发布准备更新（2026-11-10）

用户授权新建分支上传。Git连接仍超时，通过GitHub API重新读取main并取得完整源码快照：`d296447456c7461a01842fe140dd28e19339ff19`。上述caac036为最初开发基线；发布候选已迁移到这里的新主线并重新验证。仅新增协同文件，没有覆盖视觉或其他成员代码。
