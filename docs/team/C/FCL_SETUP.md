# FCL 独立规划环境与验证

现场已配置：`/home/qwer/c_planning_venv`，Python3.12.3；python-fcl0.7.0.11、numpy2.2.6、Cython3.3.1。无sudo安装、不改p7_sdk_venv、brick_vision_venv或第三方SDK。2026-11-07用户明确授权按需求配置环境。

本地Windows独立环境：项目下artifacts/planning_venv；额外含pytest/PyYAML/OpenCV以运行项目测试。锁文件evidence/windows_planning_C17.lock。项目增加可选planning extra，默认安装不强制FCL。

## 重建

Linux：
```
python3 -m venv /home/qwer/c_planning_venv
/home/qwer/c_planning_venv/bin/python -m pip install --only-binary=:all: -r config/planning/requirements-linux-fcl.txt
/home/qwer/c_planning_venv/bin/python -m pip check
```

如索引响应截断或主机慢，可在联网电脑用pip download指定cp312/manylinux平台预取wheel，经SHA256核对后在主机用`--no-index --find-links=<wheel目录>`安装。C17传入wheel逐个哈希见evidence/linux_fcl_wheel_lock_C17.json，主机sha256sum已逐项一致。未关闭TLS验证、未使用trusted-host绕过证书、未修改系统pip配置。

完整项目测试环境可在独立venv安装`.[dev,planning]`。本机实际先固定NumPy/FCL，再安装PyYAML6.0.3/OpenCV4.12.0.88和pytest8.4.2，最终全套134 passed。仅Linux最小FCL环境尚未部署整个项目，不宣称Linux全套134项已跑。

## 本次验证

- 主机sphere separation=1m、相交sphere=true；BVH tetra mesh separation=1m、相交mesh=true；均有assert通过，pip check无冲突。真实SSH运行的是合成几何，非硬件动作。远端证据/home/qwer/c_calibration_runs/fcl_environment_C17.json和c_planning_environment_C17.lock，本地remote_fcl_environment_C17.json。
- 本机FclMeshChecker测试覆盖mesh相交/分离/距离余量、缺pose/错误排除和非法三角索引。
- `PYTHONPATH=src python tools/audit_p7_fcl.py <C16资产目录> config/planning/p7_sdk_to_vendor_collision_candidate.json <新报告.json>`。
- 实际8份已锁厂家mesh建立BVH，两组synthetic关节姿态各查询28个pair，无任何排除；各有6组表面相交，详见p7_fcl_mesh_audit_C17.json。这可包含模型安装接缝/声明几何重叠，不能判定实体碰撞，未为了通过去除pairs。

## 范围

FCL后端为所给三角表面在所给姿态的相交与距离。未实现关节非线性轨迹的连续认证；闭合物体互相包含而表面不相交的体积包含问题也需另查。未包含手、相机、机身、持物和真实环境。结果无接触时status仍UNKNOWN，完整碰撞/动作许可不通过。原粗包络继续用于保守诊断，不再把它当唯一mesh碰撞依据。

参考实现接口：https://github.com/BerkeleyAutomation/python-fcl 。不启动任何Robot/Arm/Hand对象。
