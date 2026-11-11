# V/M → main 合并预检清单（2026-11-10）

**范围**：只做合入预检与清理，**不开臂 / 不发 CAN / 不大动臂**。  
**对比**：`codex/v-vision-20261110` @ `0df1d7c`（含 merge `origin/main`） vs `origin/main` @ `e9b5493`。

**预检测试**：
- 相关子集 **74 passed**（execution/safety_gate/pre_grasp/shadow/verify/vision/arm + e2e FSM Mock；无设备）
- 全量 `tests/unit`：**536 passed, 1 skipped**（`fcl` 缺模块，与合入无关）

## 裁决摘要

| 项 | 结论 |
| --- | --- |
| 合入 main 就绪度 | **高** |
| 路径冲突风险 | **无**（演练 `git merge origin/main` 干净 ort；冲突文件 = 0） |
| 缺宿主文件 | **已消除**：`tools/host_monitor/`（9 文件 + static）经 merge 进入本分支；`python -c "import tools.host_monitor"` OK |
| 运动默认 | **安全**：reporter/`SafetyGate` dry-run 恒 `control_ready=false`、`motion_enabled=false`；`host_monitor --enable-motion` 为 `store_true`（默认关） |
| 证据体积 | 已跟踪 `docs/team/B/evidence` ≈ **21 MB / ~101 files**（含 zip/npz/png）；未跟踪 junk **未**加入提交 |

## 1. 冲突与宿主

- [x] `git fetch`；演练前 `origin/main...HEAD` ≈ **4 behind / 33 ahead**
- [x] 无同路径双方修改 → 三方合并干净
- [x] **合并演练完成**：`git merge origin/main` → `0df1d7c`（ort，无冲突）
  - 吃进：`tools/host_monitor/**`（9 路径）+ `docs/DEPLOYMENT.md`（+4）
  - 冲突点：**无**
- [x] 合入后冒烟：`python -c "import tools.host_monitor"` / 存在 `tools/host_monitor/README.md`（**未**加 `--enable-motion`，**未**发 CAN）

## 2. 证据 / junk（该留 vs 勿加）

| 类别 | 建议 |
| --- | --- |
| 机读 JSON 门禁/handoff（`pre_grasp_*`、`host_control_readiness_*`、`verify_*_handoff_*`、shadow） | **保留**（合入叙事与复现需要） |
| 已跟踪 raw zip / npz / 大图（slot_reference / slot_contrast） | **暂留**；后续并行线可迁 LFS 或外存，**本轮不大删** |
| 未跟踪 `fail212542_*`、`slot_contrast_*214000.zip`、`slot_reference_*` 展开目录、`.test-tmp-*` | **勿强加进仓库**（已写入 `.gitignore`；本轮未 `git add`） |
| `stash@{0}: wip-safetygate-parallel` | **勿混进合入提交**；未 pop；交并行线 |

## 3. 合入 main 前最小清单

### 测试（离线，无设备）

- [x] `pytest tests/unit/execution/test_host_control_readiness.py tests/unit/execution/test_safety_gate_dry_run_issuance.py -q`
- [x] `pytest tests/unit/coordination/test_pre_grasp_gates.py tests/unit/planning/test_shadow_plan_bundle.py -q`
- [x] `pytest tests/unit/vision/test_verify_export.py tests/unit/vision/test_vision_service.py tests/unit/arm/ -q`
- [x] `pytest tests/e2e/test_single_block_fsm.py -q` — Mock only
- [x] 合并后全量 `tests/unit`：**536 passed, 1 skipped**（本地；CI 仍待 PR 检查）

### 文档 / 契约

- [x] `docs/CONTRACTS.md` 在 V tip 侧（本分支相对 main 的新增/更新，合入随 PR）
- [x] 本清单更新为演练结果；`HOST_CONTROL_READY_20261110.md` / `PRE_GRASP_GATES_20261110.md` / `M_PERMIT_AUTHORITY_20261110.md` 指向 V tip 叙事

### WIP / stash

- [x] 工作区无已修改跟踪文件；仅未跟踪 field junk（未加入提交）
- [x] stash `wip-safetygate-parallel` **保留隔离**，未 pop、未混入
- [x] 无未跟踪 fail* / slot_reference 展开目录被 `git add .`

### 危险默认值（合入门禁）

- [x] 任意路径默认 **不得** `motion_enabled=true` / `control_ready=true`
- [x] dry-run SafetyGate：`hardware_enabled=False`、`executable=false`、`live_permit=null`
- [x] `host_monitor`：无 `--enable-motion` 则关节控制拒绝使能（`store_true`；`JointController` 显式拒绝）
- [x] 合入后扫 `enable_motion` / `hardware_enabled=True` / `control_ready=True`：仅见 checklist 文案与「须显式 flag」拒绝路径，无默认抬升

## 4. 「不大动臂」相关风险点

1. **合入后 main 带上 `host_monitor`**：有人误加 `--enable-motion` + UI `READY`/`ENABLE` 会真使能单关节（步长默认数度）——合入说明写清：**默认只读遥测**。
2. **`ArmStateReader` / live-readonly 探针**：只读开 CAN 通道；当前实现声明不 Rest、不 enable-motion，但仍是真机总线接触——合入验收用 Mock/recorded，**不要**把 live-readonly 当必跑 CI。
3. **`vision_pre_grasp_ready=true` ≠ 可动臂**：正式抓取仍卡在 live Permit + host 策略抬升 + 执行器使能；勿把视觉就绪误读成 `control_ready`。
4. **证据 zip 体积**：膨胀 clone；不直接影响运动，但拖慢 CI/评审。

## 5. 阻塞项（相对「可合 main」）

| 优先级 | 阻塞 | 说明 |
| --- | --- | --- |
| ~~P0 流程~~ | ~~尚无 merge 演练~~ | **已解除**：`0df1d7c` 干净吃进 `host_monitor` |
| ~~P0 卫生~~ | ~~WIP/stash 混入风险~~ | **已控制**：stash 未 pop；junk 未跟踪未提交 |
| P1 产品 | live `Permit` + host 策略抬 `control_ready` **故意未做** | **不阻塞合入代码**；阻塞「真机正式抓取」 |
| P2 | 大证据 blob；CI 绿待 PR 检查 | 文档与 LFS 可后置；开 PR 后跟 CI |
| P2 卫生 | 本地仍有 `stash@{0}` 与未跟踪 slot_* junk | 勿误 pop / 勿 `git add .` |

## 6. 演练记录（2026-11-10）

```text
git fetch origin
# status: clean tracked; untracked slot_contrast/slot_reference junk ONLY
# stash@{0}: wip-safetygate-parallel (left alone)
git merge origin/main
# → Merge made by ort; 10 files, +1919; conflicts=0
# host_monitor present; import OK
py -3.12 -m pytest <related+e2e> -q   # 74 passed
py -3.12 -m pytest tests/unit -q      # 536 passed, 1 skipped
```

合入后**禁止**默认启动：

```text
python -m tools.host_monitor.server --enable-motion   # 不要作为冒烟默认
```

冒烟请用无 motion 标志或 `--mock`。

## 7. 合入就绪结论

- **就绪度：高** — 可开 PR 合入 main（dry-run / Mock 路径；**≠** 正式抓取验收）。
- **剩余阻塞合入**：无硬阻塞；建议开 PR 后等 CI，评审时强调默认不使能运动。
- **正式抓取**：仍 **否**（需 live Permit + host 策略抬升 + 显式使能；本轮不做）。
