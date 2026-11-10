# Windows CI：标定文件字节哈希与UTF-8测试读取修复

失败提交：be50b37。GitHub Actions run 42793695598（PR）及42793690189（push）。

## 实际失败原因

Windows的pytest失败于 `test_target_request_never_uses_candidate_hash_as_approval_or_observed_pose_as_goal`：目标请求模板预期C35候选原始文件sha256为 `a8711b804660ff8888e85e07b836bb336832ab04a31bf5337e7b64157a003461`，Windows检出后因LF→CRLF变为 `2339af8daa000ef986b68b3faa6e26a63c91b74c563c78e1ccbcb39590e28a62`。Linux两个任务通过。另一Windows任务因矩阵快速失败而取消，不是另一独立功能错误。

本次新增模板遗漏了仓库既有的按字节保真策略，责任在M此次提交；不以忽略校验或改期望哈希来通过。Node.js弃用警告不是该断言失败的原因。

## 修改

- `.gitattributes` 对 `calibration/candidates/**` 使用 `-text`，与已有按字节索引的录制/交接资料策略一致。保持标定数值和文件指纹不变，不将换行规范化后的语义哈希冒充原始字节哈希。
- 新回归测试在临时本地Git仓库中add并checkout-index，分别测试core.autocrlf=true/false，实际检查输出文件hash及Git属性。不开网络、不修改用户Git配置。
- 完整本地中文路径验证另外发现 `test_offline_runner.py` 以区域默认GBK读取已知UTF-8报告；改为显式UTF-8，保留原断言。

## 本地验证

隔离venv按 `python -m pip install -e ".[dev]"` 安装项目声明依赖，避免旧离线辅助目录中的OpenCV5覆盖项目声明的OpenCV4。运行于Windows中文项目路径，PYTHONUTF8=0（未依赖全局UTF-8模式修复读取错误）：

```text
python experiments/scripts/run_offline_validation.py
python -m brick_stacking.app.task_runner
```

完整测试 **639 passed, 1 skipped**（未安装可选python-fcl，对应原有mesh测试按原规则跳过）；十块Mock流程PASS。后者仅软件位置/状态演练，没有视觉流水线、物理抓握或硬件验收。

远端验证以本修复提交对应GitHub Actions的Windows/Linux、Python3.11/3.12四格状态为准。没有禁用Windows、删除失败断言或放宽任何运动/定位门槛。未连接机器人，control_ready=false。
