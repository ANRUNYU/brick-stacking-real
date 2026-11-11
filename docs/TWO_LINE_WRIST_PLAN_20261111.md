# 两线开发计划：手腕目标交接（2026-11-11）

**状态**：当前人员分工与交接格式。真机仍 `executable=false`、`control_ready=false`。  
**范围**：左臂 P7 + 左手 O6。先固定位置的单块抓放，再允许木块在桌面上换位置；比赛时桌子高度固定、平面位置不固定，用桌面棋盘格重定桌子坐标系。不含十块阶梯、双臂、腕相机主定位。  
**取代**：人员分工以本文为准。[POSE_HANDOFF_FOR_PATH_20261111.md](team/B/POSE_HANDOFF_FOR_PATH_20261111.md) 里的悬停证据和「−Z 不可规划」仍然有效；其中要求协作者携带 `hand_event`、由本侧交出全部中间关键帧的约定，改由本文替换。误差门仍用 [THREE_TRACK_GRASP_DEV_PLAN.md](THREE_TRACK_GRASP_DEV_PLAN.md) §0.2、§3.4，不在本文放宽。

两条线每次交接的只有**手腕目标**。棋盘格、木块像素、手指百分数不进入路径线。

---

## 1. 分工

| | 线 H（本侧） | 线 P（协作者） |
|---|---|---|
| 负责 | 三指抓取预设；固定姿态的手腕相对关系；头相机定位木块；棋盘格重定桌子 | 按手腕目标做左臂七轴路径 |
| 交出 | `wrist-target`：准备抓取、放置，各一份基座系手腕位姿 + 七轴种子 | `wrist-path`：引用该目标文件的关节轨迹 |
| 不负责 | 目标之间的插值、避桌中间点 | 手指开合、棋盘格、改抓取姿态、另选悬停点 |

手腕目标指法兰连杆 `L8_Link` 在左臂基座 `L_arm_root` 中的位姿。J6、J7 是腕部两个转动关节，不是这个位置；它们和 J1–J5 一起出现在种子和路径里。

灵巧手准备姿态和闭合姿态保持不变，冻结在木块坐标系上。桌子只平移时，基座系里的转角可以不变；桌子有转角时，线 H 把相对姿态乘上本场桌子位姿，连转角一起写入目标。线 P 不保存「今天这张桌子」的绝对坐标。

完整动作顺序：

```text
头相机识别木块
  → 线 H 生成 grasp_ready / place_ready
  → 线 P 规划并移到 grasp_ready
  → 线 H 闭合手指
  → 线 P 规划并移到 place_ready
  → 线 H 张开手指
```

手指动作发生在路径停稳之后，由线 H 另行下发，不写进 `wrist-path`。

---

## 2. 坐标

公共约定沿用 [CONTRACTS.md](CONTRACTS.md)：长度米，角度弧度，时间秒。`T_A_B` 把 B 系中的点变到 A 系。旋转的权威表达是四元数 `xyzw`。示教阅读可以并列外旋 ZYX 的 `rz, ry, rx`（弧度，`R = Rz(rz) Ry(ry) Rx(rx)`）；两套同时存在时以四元数为准。

| 名字 | 含义 | 谁产生 | 何时更新 |
|---|---|---|---|
| `L_arm_root` | 左臂 URDF 基座 | 模型 | 不随桌子移动 |
| `L8_Link` | 法兰，手腕目标的 child | 模型 | — |
| `camera_CP2L863000KL_color_optical_frame` | 头相机光学帧 | 固定外参 C35 | 不随桌子移动。C35 仍是拟合，不是执行许可 |
| `table_board` | 指定棋盘格坐标系 | 线 H，每次摆桌 | 桌子挪动后重算 |
| `table_black_cross_20mm` | 20 mm 黑十字，放置槽中心 | 相对棋盘格测一次 | 随 `table_board` 带走 |
| `block` | 50 mm 木块 | 头相机现测 | 每次抓取 |

指定棋盘格用实测格长 **0.01938 m**（标称 20 mm 的打印件会差出约 26 mm 的尺度）。桌面上有两张棋盘格时，标定入口只认 `board_id` 指向的那一张，并且它相对十字的位置在一场比赛中不再挪动。

桌子挪动时重算的是 `T_L_arm_root_board`，不是头相机外参，也不是腕相机外参：

```text
T_L_arm_root_board = T_L_arm_root_camera · T_camera_board
T_L_arm_root_block = T_L_arm_root_camera · T_camera_block
T_L_arm_root_L8   = T_L_arm_root_block · inverse(T_L8_block)     # grasp_ready
T_L_arm_root_L8   = T_L_arm_root_cross · inverse(T_L8_cross)     # place_ready
```

`T_L8_block`、`T_L8_cross` 在固定块上示教一次。旧 C49（两指捏持）不用于三指。头相机给出抓取前的木块位置。左腕相机可以和示教同步存图，不参与把木块变到基座系：那条链要乘 J6/J7 的正解，而这两轴的弧度尚未审计。

左肩 J1 的轴心还没有被确认等于 `L_arm_root`。尺量里的十字系坐标不能直接发给线 P。

关节名固定为 `J1`…`J7`，对应左臂 CAN `can2` 电机 `61`…`67`，也对应 URDF 的 `L1_Joint`…`L7_Joint`。`L8_Joint` 是固定关节，没有电机。

手指不进入交接文件。线 H 自用的预设顺序是 `thumb_flex, thumb_abd, index, middle, ring, pinky`，单位字段写明 `percent`（0–100）或 `raw_u8`，二者不混用。百分数不是弧度。

---

## 3. 交接格式

样例：[examples/wrist_target_v0.1.example.json](examples/wrist_target_v0.1.example.json)、[examples/wrist_path_v0.1.example.json](examples/wrist_path_v0.1.example.json)。样例里的悬停数来自已记录的手摆姿态，只说明字段，不是抓取指令。

### 3.1 线 H → 线 P：`wrist-target-0.1`

一次抓放一个文件，至少两个目标，顺序即执行顺序。

| 字段 | 要求 |
|---|---|
| `schema_version` | `wrist-target-0.1` |
| `side` | `left` |
| `executable` | `false`，直到另一次真机授权 |
| `parent_frame` / `child_frame` | `L_arm_root` / `L8_Link` |
| `urdf_sha256` | 与 `config/models/p7_left/LOCK.json` 一致。当前锁为 `233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce` |
| `targets[].name` | `grasp_ready` 或 `place_ready`。可选一次共用的起点 `hang` |
| `translation_m` | 3 个数，米 |
| `quaternion_xyzw` | 4 个数，模长 1 |
| `rpy_extrinsic_zyx_rad` | 可选，`[rz, ry, rx]` |
| `seed_q_rad` | 7 个数，弧度，示教姿态。七轴解不唯一，种子选定肘和腕 |
| `seed_provenance` | 每轴 `sdk_audited` 或 `sdk_report_not_audited`。在量程审计完成前，J6、J7 只能是后者 |
| `table_board_hash` | 生成该目标时使用的棋盘格标定哈希。固定桌阶段也要有，便于桌子挪动后整文件作废 |
| `limits` | 见下表。线 P 不得放宽 |

`limits` 取自既有门控，不是新指标：

| 字段 | 值 | 含义 |
|---|---|---|
| `cartesian_arrival_max_m` | 0.010 | 末端相对目标的到位门 |
| `level_travel_clearance_m` | 0.080 | 水平段不低于桌面以上 80 mm |
| `lift_before_travel_m` | 0.030 | 闭合后先竖直抬起再侧移 |
| `max_tcp_speed_m_s` | 0.020 | 本阶段低速上限，尚未用真机改写前不得提高 |
| `table_height_check_max_m` | 0.008 | 棋盘格解出的桌面高度与约定高度之差超过此值则线 H 不得发目标 |

路径中间点由线 P 生成。中间点要停在同一族解上，不得改写目标的姿态。任一中间点逆解失败则整段拒绝，不把目标改到「大概在桌子上方」。

### 3.2 线 P → 线 H：`wrist-path-0.1`

| 字段 | 要求 |
|---|---|
| `schema_version` | `wrist-path-0.1` |
| `request_sha256` | 所消费的 `wrist-target` 文件的 SHA-256。目标一改，旧路径作废 |
| `segments[].from` / `to` | `hang`→`grasp_ready`，以及 `grasp_ready`→`place_ready` |
| `joint_names` | `J1`…`J7` |
| `points[].time_from_start_s` | 秒，从该段起点计，单调增加 |
| `points[].q_rad` | 7 个数。段首应接近种子或上一段段尾，段尾的正解应回到该目标的位姿，平移误差不超过 `cartesian_arrival_max_m` |
| `interpolation` | `joint` 或 `cartesian`。贴桌的最后一段下降使用 `cartesian`，并保持目标姿态 |
| `rejected` | 失败时给出段名和 `ik_failed` / `clearance` / `joint_limit` / `orientation_changed`，不另造一个手腕目标 |
| `motion_enabled` | `false` |

线 H 核对段尾正解与目标位姿后再考虑下发。下发仍走本仓的使能与许可，不在路径文件里打开。

### 3.3 线 H 自用、不交给线 P

桌子标定 `table-board-0.1`，每次摆桌一份：

```json
{
  "schema_version": "table-board-0.1",
  "board_id": "table_checkerboard_primary",
  "square_size_m": 0.01938,
  "inner_corners": [9, 6],
  "parent_frame": "L_arm_root",
  "child_frame": "table_board",
  "translation_m": [0.0, 0.0, 0.0],
  "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
  "table_height_m": 0.0,
  "nominal_table_height_m": 0.0,
  "camera_extrinsic_hash": "c35-fit-only",
  "approved_for_motion": false
}
```

相对抓取 `grasp-relative-0.1`，固定块示教成功后冻结：`T_L8_block`、`T_L8_cross`，同为 `translation_m` + `quaternion_xyzw`，并记下三指预设版本号。预设本体使用已有 `GraspPreset`：六路带单位、带速度或时长。三指同时接触要求准备姿态（`preshape`）和闭合（`close`）分开存，无名指和小指也要有百分数。

---

## 4. 开发顺序

线 P 可以用样例文件先把读取和逆解接上。第一份真实 `grasp_ready` 要等线 H 在块上示教完成。贴块的路径在那之前不做。

| 步 | 线 | 完成时有什么 |
|---|---|---|
| 1 | H | 固定红块上确认三指准备角与闭合：闭合后和微抬后块仍在指间正中。冻结 `T_L8_block`、`T_L8_cross` 和预设版本 |
| 2 | H | 发出 `executable=false` 的 `wrist-target`，含 `grasp_ready` 与 `place_ready`，种子带每轴来源 |
| 3 | P | 交回 `wrist-path`。水平段满足 80 mm 净空，闭合后的侧移发生在竖直抬起之后。逆解失败则退回，不改目标 |
| 4 | H | 另一次授权下，固定块低速抓起、放到十字、松开。到位按 10 mm 门核对。未授权不把样例或悬停记录当指令 |
| 5 | H | 棋盘格入口：挪动桌子后只重算 `table-board`，用原相对姿态重发 `wrist-target`。桌面高度与约定值之差大于 8 mm 则不发 |
| 6 | H | 木块改位置：头相机更新块的位置；姿态仍用冻结的相对关系。块的转角不是 90° 的倍数时，在目标的四元数里反映，路径格式不变 |

第 4 步之前不进入不固定位置。第 5 步的入口在第 1 步就要按「桌子位姿是输入」来存相对关系，避免把今天的基座系坐标写成常数。

---

## 5. 仍阻断真机的事实

格式统一不取消这些缺口：

- J6/J7 没有已审计弧度。种子可以用来规划，不能写成已验证的腕角。
- C35 是拟合，独立验证未做。头相机链可以算目标，不算执行许可。
- 整臂碰撞仍是 `UNKNOWN`。80 mm 净空是路径约束，不是碰撞已通过。
- 右臂、右手在左臂运动期间保持失能并停在已记录的位置。`hang` 使用一份记录下来的七轴角，不用松手后的重力垂落代替。
