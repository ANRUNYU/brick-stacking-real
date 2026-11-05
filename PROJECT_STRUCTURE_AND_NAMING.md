# 真机双臂垒砖项目：目录结构与命名规范

> 状态：**提议版本 v1.0（待团队评审）**  
> 适用项目：LinkerArm（P7 候选）+ LinkerHand O6 ×2 + Orbbec Gemini 335L（头部）/ Gemini 335 ×2（腕部）的全自主垒砖真机系统。  
> 设计依据：`BRICK_STACKING_REAL_ROBOT_DESIGN_v0.2.md`；本规范是其第 12 章的详细化，不替代该系统设计基线。  
> 约束：独立真机仓库；Rabokit 仿真代码仅作为经验证的参考案例，不作为本仓库基础。所有未确认的设备接口、外参和工具坐标必须保留 `TBD`；默认 `dry_run=true`。

## 1. 设计目标与基本原则

1. **职责单一**：算法、ROS 2 通信、硬件驱动适配、配置标定、测试与实验结果分开，避免一个 `main.py` 包揽所有功能。
2. **统一格式**：Python 模块和测试源码采用 `snake_case`；类使用 `PascalCase`；常量使用 `UPPER_SNAKE_CASE`；ROS 2 topic 和 TF frame 使用统一小写命名。
3. **测试可复现**：测试**代码文件名固定**，每次运行生成**独立带时间戳的结果目录**。不为每次试验复制一份新的测试脚本。
4. **真机安全隔离**：默认离线/Mock；连接真机的测试必须明确标记并由人员授权，不在 CI 中自动执行。比赛运行与开发辅助运行的日志严格区分。
5. **配置与来源可追溯**：记录运行模式、SDK/代码 commit、设备序列号、标定版本、配置快照、时间与时区。不要把未审核的候选外参直接投产。
6. **兼容团队协作**：目录、函数、测试一一对应；Codex 增加新功能时同时增加测试、配置说明和运行证据。

## 2. 建议仓库结构（目标形态）

```text
brick-stacking-real/
├── README.md                            # 快速开始、前提条件、开发流程
├── DESIGN.md                            # 真机系统设计基线（当前 v0.2）
├── PROJECT_STRUCTURE_AND_NAMING.md      # 本文档
├── AGENTS.md                            # Codex 的持续指令、禁令与任务流程
├── CHANGELOG.md
├── CONTRIBUTING.md                       # 分支/PR/Review/测试要求
├── pyproject.toml                        # Python 依赖/打包、pytest、ruff 等
├── .gitignore
├── .env.example                          # 仅示例；不得提交真实凭证
│
├── config/                               # 可读、可审查的业务配置（非测试产物）
│   ├── defaults.yaml                    # 无硬件危险动作的默认配置
│   ├── schema/                          # 配置类型、范围、合法性约束
│   ├── modes/
│   │   ├── development_test.yaml        # 可安全停机后人工介入
│   │   ├── autonomy_trial.yaml          # 全自主试跑
│   │   └── competition_autonomous.yaml  # 正式全自主，不允许人工恢复
│   ├── cameras/
│   │   ├── head_gemini_335l.yaml
│   │   ├── left_wrist_gemini_335.yaml
│   │   └── right_wrist_gemini_335.yaml
│   ├── robots/
│   │   ├── left_arm.yaml                # 型号 TBD；不能假定 P7 已核验
│   │   ├── right_arm.yaml
│   │   ├── left_hand_o6.yaml
│   │   └── right_hand_o6.yaml
│   ├── scenes/
│   │   ├── stacking_4_3_2_1.yaml        # 目标槽位及支撑依赖
│   │   └── handoff_zone.yaml           # 经实测可达性验证后才启用
│   └── vision_profiles/
│       ├── normal_light.yaml
│       └── difficult_reflection.yaml
│
├── calibration/                          # 标定记录，必须区分草案和批准版本
│   ├── README.md
│   ├── candidates/                       # 未验收的外参/TCP，默认不允许执行
│   └── approved/                         # 经签名/审查的版本；附误差报告
│       └── CAL_YYYYMMDD_R01/            # 结构示例，非真实标定数据
│           ├── manifest.yaml
│           ├── head_to_world.yaml
│           ├── left_wrist_to_flange.yaml
│           ├── right_wrist_to_flange.yaml
│           ├── arm_mounts.yaml
│           ├── tcp.yaml
│           └── validation.json
│
├── src/brick_stacking/                   # 可脱离 ROS 2 测试的核心 Python 包
│   ├── __init__.py
│   ├── models/                           # 纯数据契约，不依赖硬件
│   │   ├── camera_frame.py
│   │   ├── block_detection.py
│   │   ├── block_pose.py
│   │   ├── scene_state.py
│   │   └── task_state.py
│   ├── hardware/                         # SDK 适配层，所有真机 I/O 的唯一入口
│   │   ├── protocols.py                  # Arm/Hand/Camera Protocol
│   │   ├── linkerarm_adapter.py
│   │   ├── linkerhand_o6_adapter.py
│   │   ├── orbbec_adapter.py
│   │   └── mock_devices.py
│   ├── vision/                           # 仅识别、分割、质量评价
│   │   ├── color_segmentation.py
│   │   ├── block_instance_segmentation.py
│   │   ├── depth_processing.py
│   │   ├── tabletop_segmentation.py
│   │   ├── heightmap.py
│   │   └── tracking.py
│   ├── localization/                     # 空间定位及标定数学
│   │   ├── camera_projection.py
│   │   ├── rigid_transforms.py
│   │   ├── handeye_calibration.py
│   │   ├── table_plane.py
│   │   └── pose_fusion.py
│   ├── scene/                            # 当前积木、槽位、支撑关系
│   │   ├── object_registry.py
│   │   ├── scene_manager.py
│   │   └── stacking_slots.py
│   ├── planning/
│   │   ├── reachability.py
│   │   ├── grasp_planner.py
│   │   ├── task_scheduler.py
│   │   ├── handoff_planner.py
│   │   └── motion_planner.py
│   ├── execution/
│   │   ├── execution_manager.py
│   │   ├── handoff_fsm.py
│   │   ├── recovery_policy.py
│   │   └── safety_gate.py
│   ├── verification/
│   │   ├── grasp_verification.py
│   │   ├── placement_verification.py
│   │   └── structure_verification.py
│   ├── runtime/
│   │   ├── config_loader.py
│   │   ├── mode_manager.py
│   │   └── run_recorder.py
│   └── app/
│       └── task_runner.py
│
├── ros2_ws/                               # ROS 2 适配/部署工作空间，不与核心算法混写
│   └── src/
│       ├── brick_stacking_ros/           # ament_python 包（实际环境确定后落地）
│       │   ├── brick_stacking_ros/
│       │   │   ├── camera_node.py
│       │   │   ├── perception_node.py
│       │   │   ├── localization_node.py
│       │   │   ├── execution_node.py
│       │   │   └── diagnostics_node.py
│       │   ├── launch/
│       │   │   ├── cameras.launch.py
│       │   │   ├── perception.launch.py
│       │   │   └── robot_stack.launch.py
│       │   ├── config/
│       │   ├── package.xml
│       │   ├── setup.py
│       │   └── resource/
│       └── brick_stacking_interfaces/    # 可选：确有需求时新增 ROS msg/action
│           ├── msg/
│           ├── action/
│           ├── CMakeLists.txt
│           └── package.xml
│
├── tests/                                 # 测试源码；名称稳定、可 pytest 收集
│   ├── conftest.py
│   ├── unit/
│   │   ├── vision/
│   │   │   ├── test_color_segmentation.py
│   │   │   └── test_adjacent_block_segmentation.py
│   │   ├── localization/
│   │   │   ├── test_camera_projection.py
│   │   │   └── test_rigid_transforms.py
│   │   ├── planning/
│   │   │   ├── test_reachability.py
│   │   │   └── test_stacking_dependencies.py
│   │   ├── execution/
│   │   │   └── test_handoff_fsm.py
│   │   └── verification/
│   │       └── test_placement_verification.py
│   ├── integration/                      # 多模块 + Mock/录制数据
│   │   ├── test_rgbd_to_world_pose.py
│   │   ├── test_scene_to_task_plan.py
│   │   └── test_handoff_with_mock_arms.py
│   ├── regression/                       # 用已确认的历史问题防回归
│   │   ├── test_same_color_touching_blocks.py
│   │   └── test_stale_tf_rejected.py
│   ├── e2e/                              # 完整流程的离线/Mock 演练
│   │   └── test_ten_blocks_mock_run.py
│   ├── hardware/                         # 真机测试，CI 默认排除并受硬件安全门控
│   │   ├── test_arm_feedback_readonly.py
│   │   ├── test_camera_rgbd_stream.py
│   │   ├── test_index_finger_mobility.py
│   │   ├── test_single_block_pick_place.py
│   │   └── test_handoff_interlock.py
│   └── fixtures/                         # 小型、脱敏、可入 Git 的测试样本
│       ├── rgbd/
│       ├── known_transforms/
│       ├── scenes/
│       └── expected_outputs/
│
├── experiments/                           # 人工设计的实验协议、计划、工具
│   ├── README.md
│   ├── protocols/
│   │   ├── mobility_index_finger.md
│   │   ├── perception_adjacent_blocks.md
│   │   ├── localization_multi_point.md
│   │   └── handoff_shared_zone.md
│   ├── scripts/                          # 有独立入口的实验运行器（优先复用 src）
│   │   ├── run_camera_latency.py
│   │   ├── run_arm_reachability.py
│   │   └── run_grasp_repeatability.py
│   └── registry.csv                      # 试验 ID、状态、结论、结果路径索引
│
├── data/                                  # 大体积离线数据；默认不提交 Git
│   ├── recordings/                       # ROS bag / RGB-D/关节状态
│   ├── labels/                           # 图像标注
│   └── synthetic/                        # 标明来源的合成数据
│
├── artifacts/                             # 自动生成的运行记录；默认不提交 Git
│   └── test_runs/
│       └── 2026-11-05/
│           └── Mobility_IndexFinger_ID_202611051347/
│               ├── manifest.yaml        # 实验信息、时间、操作者/设备、环境
│               ├── config_snapshot.yaml # 配置快照，脱敏
│               ├── metrics.json         # 可机器解析的指标
│               ├── result.md            # 人可读结论（PASS/FAIL/INCONCLUSIVE）
│               ├── events.jsonl         # 状态变更与异常事件
│               ├── rosbag2/             # 按需存储相机/TF/关节状态
│               └── media/               # 按需存储截图/视频
│
├── tools/                                 # 不可直接发动作的审计/诊断工具
│   ├── check_config.py
│   ├── inspect_topics.py
│   ├── validate_calibration.py
│   └── summarize_test_runs.py
│
├── docs/
│   ├── HARDWARE_INVENTORY.md
│   ├── API_AUDIT.md
│   ├── TF_CONVENTIONS.md
│   ├── OPEN_QUESTIONS.md
│   ├── SIMULATION_LESSONS.md
│   ├── TEST_PLAN.md
│   ├── TEST_NAMING.md
│   └── SAFETY_CHECKLIST.md
└── .github/workflows/
    └── offline_ci.yml                  # lint + unit + mock integration，不碰真机
```

**逐步落地**：上面是目标结构，不要求初始提交一次性创建所有空目录。M0 阶段先创建 `src/brick_stacking/{models,hardware,localization,vision,runtime}`、`tests/{unit,integration,fixtures}`、`config/`、`docs/`、`experiments/`；ROS 2 package、自定义 msg/action 及其他复杂模块应在接口确定后创建。不要为了目录完整而生成无法工作的假实现。

## 3. 命名规范（统一约定）

### 3.1 基础代码文件

| 对象 | 规范 | 正确示例 | 避免 |
|---|---|---|---|
| Python 源文件 | `snake_case.py`，表达职责 | `block_instance_segmentation.py` | `FinalCode.py`, `test2new.py` |
| 类 / Protocol | `PascalCase` | `BlockDetector`, `ArmController` | `blockDetector`, `arm_controller` |
| 函数 / 变量 | `snake_case` | `estimate_table_plane()` | `EstimatePlane()` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` | `maxRetry` |
| 测试源码 | `test_<behavior_or_module>.py` | `test_handoff_fsm.py` | `test_20261105.py` |
| 配置 | `snake_case.yaml`，分运行模式/设备 | `left_wrist_gemini_335.yaml` | `config_final2.yaml` |
| ROS topic | 小写 `/domain/name`；以官方接口为准 | `/perception/blocks`（建议新接口） | 任意改厂商原始 topic |
| TF frame | 小写 `snake_case`，见 `TF_CONVENTIONS.md` | `world`, `left_wrist_camera` | 同一坐标混用不同单位 |
| 文档 | 稳定命名 + Git 历史管理 | `TEST_PLAN.md` | `TEST_PLAN_latest_final.md` |

### 3.2 测试命名：保留你希望的四段结构

**测试运行记录与结果目录**统一采用：

```text
<Objective>_<Object>_<InterfaceCode>_<YYYYMMDDHHmm>
```

例：

```text
Mobility_IndexFinger_ID_202611051347
Perception_AdjacentBlocks_RGBD_202611051410
Localization_HeadCamera_TF2_202611051425
Verification_Pyramid3D_RGBD_202611051501
Handoff_LeftToRight_ROS2_202611051540
```

四段释义：

- `Objective`：测试目标，使用短而稳定的英文 PascalCase 标识，如 `Mobility`、`Perception`、`Localization`、`Verification`、`Handoff`、`Safety`。
- `Object`：目标对象，使用 PascalCase，如 `IndexFinger`、`AdjacentBlocks`、`HeadCamera`、`Pyramid3D`。
- `InterfaceCode`：**项目自定义的接口代码**，如 `RGBD`、`TF2`、`ROS2`、`CAN`、`SDK`。用户示例中的 `ID` 暂保留为**待定义代号**，只有团队在 `docs/TEST_NAMING.md` 明确了 `ID` 具体代表什么后才投入正式使用；**不得将其误认为设备序列号或积木实例 ID**。
- `YYYYMMDDHHmm`：本地记录时间（24 小时制，分钟级）；具体时区同时写入 `manifest.yaml` 的 ISO 8601 带偏移时间戳，如 `2026-11-05T13:47:00+08:00`。

**处理重名**：相同分钟运行多次时，在末尾加 `_R02`、`_R03`；或者将时间升级为 `YYYYMMDDHHmmss`，但同一团队/阶段应选定一种方式并保持一致。推荐默认四段主体 + `_R02` 作为冲突消解，不改动主体模板。

**为什么不把日期写入 pytest 测试源码？** `tests/hardware/test_index_finger_mobility.py` 是稳定、可维护的测试逻辑；每次运行才产生 `artifacts/test_runs/.../Mobility_IndexFinger_ID_202611051347/`。这样源码不会因测试时间变化而不断复制，CI、覆盖率、历史比较也更容易。若是一次性的实验脚本，也应固定脚本名，版本由 Git 管理，日期体现在运行记录中。

### 3.3 测试场景代码和结果的对应关系

| 测试目标 | 稳定代码 | 一次运行的产物目录（示例） |
|---|---|---|
| 食指活动 | `tests/hardware/test_index_finger_mobility.py` | `Mobility_IndexFinger_ID_202611051347/` |
| 紧贴积木分割 | `tests/regression/test_same_color_touching_blocks.py` | `Perception_AdjacentBlocks_RGBD_202611051410/` |
| 头部相机标定 | `tests/integration/test_rgbd_to_world_pose.py` | `Localization_HeadCamera_TF2_202611051425/` |
| 四层结构验收 | `tests/unit/verification/test_placement_verification.py` | `Verification_Pyramid3D_RGBD_202611051501/` |
| 左放右取交接 | `tests/integration/test_handoff_with_mock_arms.py` | `Handoff_LeftToRight_ROS2_202611051540/` |

### 3.4 单次运行记录的最低必填字段

`manifest.yaml`（格式示例，**非真实实验**）：

```yaml
run_id: Mobility_IndexFinger_ID_202611051347
objective: Mobility
object: IndexFinger
interface_code: ID  # TBD: 在接口代号表定义后才作为正式记录
started_at: "2026-11-05T13:47:00+08:00"
mode: DEVELOPMENT_TEST
hardware_enabled: false
operator: "team_member_alias"
source_commit: "<git_sha>"
config_hash: "<sha256>"
calibration_id: null
hardware_inventory_id: null
sdk_versions: {}
result: INCONCLUSIVE
manual_intervention_count: 0
notes: "Example only; no device was controlled."
```

所有日志至少区分：`PASS`、`FAIL`、`INCONCLUSIVE`、`SKIPPED`、`ABORTED`；在 `COMPETITION_AUTONOMOUS` 中需单独保存 `manual_intervention_count=0` 的验证证据。**不要将 `TEST_ASSISTED` 的试验结果统计为完全自主成功。**

## 4. 测试类型、工具与安全边界

| 层级 | 目录 | 主要测试方式 | 是否连接真机 | CI |
|---|---|---|---|---|
| Unit | `tests/unit/` | pytest + 小型 fixtures | 否 | 默认执行 |
| Integration | `tests/integration/` | Mock SDK、录制 RGB-D/TF | 默认否 | 可执行 |
| Regression | `tests/regression/` | 真实失败样本离线重放 | 否 | 默认执行 |
| E2E Offline | `tests/e2e/` | 模拟整套 10 块任务 | 否 | 可执行 |
| Hardware Read-only | `tests/hardware/` | 真相机流、状态读取 | 是（不发运动命令） | 默认禁止 |
| Hardware Motion | `tests/hardware/` + `experiments/protocols/` | 关节/手/抓放/交接 | 是（有运动） | 永不自动执行 |

建议 `pyproject.toml` 中声明 `pytest` markers：`unit`、`integration`、`regression`、`e2e`、`hardware`、`motion`、`slow`。真机测试在代码层检查显式授权、急停可用、配置模式和限速；即使 `-m hardware` 也不能直接放行实体运动。初始 `pytest` 默认排除 `hardware` 和 `motion`，不能让 Codex 或 CI 在无授权时触发动作。

## 5. 数据、日志、标定与 Git 管理

- `tests/fixtures/`：只保留体积可控、许可清楚的最小验证样本。每个 fixture 附预期输出和采集/生成来源。
- `data/`：RGB-D、ROS bag、大视频、图像标注等较大数据；以 DVC/共享目录/对象存储管理，Git 中只保留索引、必要的轻量样本。用户个人信息、敏感环境画面及时脱敏。
- `artifacts/`：每次运行自动生成的报告、快照、图像、日志。统一不直接纳入 Git；需要提交结果时，在 `docs/TEST_REPORTS/` 写摘要并附结果索引、校验和或长期存储链接。
- `calibration/candidates/`：未经验证的候选参数；只作离线分析。`calibration/approved/`：经多点实测、记录设备、标定人员/日期、误差报告和版本审查后的参数，才允许被真机控制门控读取。具体提交策略由团队确定，避免泄露设备配置或污染通用仓库。
- `config/` 只存默认值与约束，不保存用户私钥、个人凭证、具体 CAN 设备身份等敏感项。
- `ros2_ws/build/`、`install/`、`log/`、`__pycache__/`、`.pytest_cache/`、`artifacts/`、`data/recordings/` 等进入 `.gitignore`；但不应忽略必要的版本化配置、测试源码或标定索引。

## 6. Codex 协作与新增功能的最小交付规范

每当 Codex 实现一个功能，至少产出或更新：

1. **实现文件**：在 `src/brick_stacking/<module>/`，只做该模块的职责。
2. **测试源码**：在对应 `tests/unit/` 或 `tests/integration/`；关键 bug 配 `tests/regression/`。
3. **配置与约束**：如涉及新参数，更新 `config/` 中的 schema、默认值和说明。
4. **运行证据**：离线结果存入 `artifacts/test_runs/<date>/<Objective>_<Object>_<InterfaceCode>_<timestamp>/`；输出 PASS/FAIL 等结果与证据。
5. **文档和风险**：修改 `README.md`、`docs/API_AUDIT.md`、`docs/OPEN_QUESTIONS.md` 或相关功能说明；若涉及实际硬件，报告控制指令是否真正执行、授权是否满足。

**Codex 初始任务示例**：

> 请先阅读 `DESIGN.md`、`PROJECT_STRUCTURE_AND_NAMING.md` 与 `AGENTS.md`，检查是否位于独立的真机仓库。只创建当前 M0/M1 所需的基础项目骨架，勿一次性写完整系统。首先实现可离线运行的 `BlockDetection` 数据模型、`color_segmentation.py`、`test_color_segmentation.py` 和固定命名的测试运行记录器。所有硬件适配器先创建 Protocol/Mock，不允许调用真实关节运动。运行 pytest 后列出测试结果、缺失接口和新增文件。

## 7. 需要团队在建仓时确定的决策

- [ ] 当前是否已创建**独立真机仓库**？不能直接重构旧 Rabokit 仿真仓库。
- [ ] 最终 ROS 2 版本和安装方式，是否使用 `ros2_ws/src` 的 `ament_python` 包方案？
- [ ] `ID` 在用户给出的命名例子中具体指哪种接口或检测方法？应写入 `docs/TEST_NAMING.md` 字典。
- [ ] 日期使用哪一时区、分钟内多次运行采用 `_R02` 还是秒级时间戳？
- [ ] 实验结果存本机、NAS 或对象存储？谁负责备份和长期保存？
- [ ] 哪些标定文件可以版本化进 Git，谁拥有批准权限？
- [ ] 真机测试授权方式、人工监护与物理急停责任人是谁？

---

**最终建议**：将本文件加入新真机仓库根目录。保留 `DESIGN.md` 描述“做什么以及为什么”，本文件规定“代码放哪里、文件怎么命名、如何测试和留证”。以 `M0 → M1` 逐步创建目录，而不是先塞满未实现的节点。
