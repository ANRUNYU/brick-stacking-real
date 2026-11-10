# V/M → main 合并预检清单（2026-11-10）

**范围**：只做合入预检与清理，**不开臂 / 不发 CAN / 不大动臂**。  
**对比**：`codex/v-vision-20261110` @ `f84974b` vs `origin/main`（fetch 后）。

**预检测试**：`py -3.12 -m pytest` 相关子集 **51 passed**（execution/safety_gate/pre_grasp/shadow/verify/vision/arm；无设备）。

## 裁决摘要

| 项 | 结论 |
| --- | --- |
| 合入 main 就绪度 | **中** |
| 路径冲突风险 | **低**（`merge-base` 起双方无重叠改动路径；`<<<<<<` = 0） |
| 缺宿主文件 | **`tools/host_monitor/` 仅在 main（9 文件），V tip 为 0** — 合入 main 会保留；单独检出 V 无 LAN 关节控制 UI |
| 运动默认 | **安全**：reporter/`SafetyGate` dry-run 恒 `control_ready=false`、`motion_enabled=false`；main 的 `host_monitor --enable-motion` 为 `store_true`（默认关） |
| 证据体积 | 已跟踪 `docs/team/B/evidence` ≈ **21 MB / ~101 files**（含 zip/npz/png） |

## 1. 冲突与宿主

- [x] `git fetch`；`origin/main...HEAD` ≈ **4 behind / 31 ahead**（main 多 host_monitor 四连提交）
- [x] 无同路径双方修改 → 预期可干净三方合并
- [ ] **合入前**：用 PR 把 V 合进 main（或先 `merge origin/main` 进 V 再 PR），确认 `tools/host_monitor/` 仍在
- [ ] 合入后冒烟：`python -c "import tools.host_monitor"` / 读 `tools/host_monitor/README.md`（**勿**加 `--enable-motion`）

## 2. 证据 / junk（该留 vs 勿加）

| 类别 | 建议 |
| --- | --- |
| 机读 JSON 门禁/handoff（`pre_grasp_*`、`host_control_readiness_*`、`verify_*_handoff_*`、shadow） | **保留**（合入叙事与复现需要） |
| 已跟踪 raw zip / npz / 大图（slot_reference / slot_contrast） | **暂留**；后续并行线可迁 LFS 或外存，**本轮不大删** |
| 未跟踪 `fail212542_*`、失败包 zip/目录、`.test-tmp-*` | **勿强加进仓库**（已写入 `.gitignore`） |
| `stash@{wip-safetygate-parallel}` / 本地 WIP | **勿混进合入提交**；交并行线 |

## 3. 合入 main 前最小清单

### 测试（离线，无设备）

- [x] `pytest tests/unit/execution/test_host_control_readiness.py tests/unit/execution/test_safety_gate_dry_run_issuance.py -q`
- [x] `pytest tests/unit/coordination/test_pre_grasp_gates.py tests/unit/planning/test_shadow_plan_bundle.py -q`
- [x] `pytest tests/unit/vision/test_verify_export.py tests/unit/vision/test_vision_service.py tests/unit/arm/ -q`
- [ ] （可选）`pytest tests/e2e/test_single_block_fsm.py -q` — Mock only
- [ ] 合入后全量或 CI 绿

### 文档 / 契约

- [ ] `docs/CONTRACTS.md` 与 V tip 一致
- [ ] 本清单 + `HOST_CONTROL_READY_20261110.md` / `PRE_GRASP_GATES_20261110.md` / `M_PERMIT_AUTHORITY_20261110.md` 指向 tip

### WIP / stash

- [ ] 工作区干净或仅并行线明确 WIP；**清空/隔离** `wip-safetygate-parallel` stash，避免误 pop
- [ ] 无未跟踪 fail* 被 `git add .`

### 危险默认值（合入门禁）

- [x] 任意路径默认 **不得** `motion_enabled=true` / `control_ready=true`
- [x] dry-run SafetyGate：`hardware_enabled=False`、`executable=false`、`live_permit=null`
- [x] `host_monitor`：无 `--enable-motion` 则关节控制拒绝使能
- [ ] 合入 diff 再扫一遍 `enable_motion` / `hardware_enabled=True` / `control_ready=True` 赋值

## 4. 「不大动臂」相关风险点

1. **合入后 main 带上 `host_monitor`**：有人误加 `--enable-motion` + UI `READY`/`ENABLE` 会真使能单关节（步长默认数度）——合入说明写清：**默认只读遥测**。
2. **`ArmStateReader` / live-readonly 探针**：只读开 CAN 通道；当前实现声明不 Rest、不 enable-motion，但仍是真机总线接触——合入验收用 Mock/recorded，**不要**把 live-readonly 当必跑 CI。
3. **`vision_pre_grasp_ready=true` ≠ 可动臂**：正式抓取仍卡在 live Permit + host 策略抬升 + 执行器使能；勿把视觉就绪误读成 `control_ready`。
4. **证据 zip 体积**：膨胀 clone；不直接影响运动，但拖慢 CI/评审。

## 5. 阻塞项（相对「可合 main」）

| 优先级 | 阻塞 | 说明 |
| --- | --- | --- |
| P0 流程 | 尚无针对本 tip 的合入 PR / 未与 main 做一次真实 merge 演练 | 冲突预检通过 ≠ 已合 |
| P0 卫生 | 本地可能仍有并行 WIP / stash | 合入提交应干净 |
| P1 产品 | live `Permit` + host 策略抬 `control_ready` **故意未做** | **不阻塞合入代码**；阻塞「真机正式抓取」 |
| P2 | 大证据 blob / host_monitor 仅在合入后出现 | 文档与 LFS 可后置 |

## 6. 建议合入命令（操作员执行；本预检不开臂）

```text
git fetch origin
git checkout codex/v-vision-20261110
# 可选：git merge origin/main   # 先吃进 host_monitor
# 再开 PR → main，或 merge --no-ff
```

合入后**禁止**默认启动：

```text
python -m tools.host_monitor.server --enable-motion   # 不要作为冒烟默认
```

冒烟请用无 motion 标志或 `--mock`。
