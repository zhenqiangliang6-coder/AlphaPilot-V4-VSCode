# 工作记录（Worklog）

记录项目中的重要变更与里程碑，便于回溯与审计。

## 2026-04-02

- 增强 `planner` 的 JSON 修复器（`python_worker/planner.py`）
  - 解决 LLM 返回非严格 JSON（单引号、尾随逗号、缺失分隔符、冗余括号等）导致解析失败的问题。
  - 实现策略：快速 regex 清理 -> 插入缺失逗号 -> 单引号替换 -> ast.literal_eval 回退 -> 基于括号计数提取顶层对象并逐一解析。
  - 相关文件：`python_worker/planner.py`（更新）

- 添加单元测试以覆盖坏 JSON 场景
  - 文件：`python_worker/test_planner_repair.py`
  - 覆盖示例：多余右大括号、对象间缺少逗号、单引号 + 尾随逗号
  - 本地运行结果：3 tests passed（修复器通过代表性场景验证）

- 为 Step Executor 添加受控测试套件
  - 文件：`python_worker/test_step_executor_agents.py`
  - 覆盖 agent：`qwen`、`Volcengine`、`deepeek`
  - 覆盖步骤类型：`analyze`、`plan`、`write`、`refine`、`test`
  - 测试策略：使用 `monkeypatch` 替换 LLM/运行器为安全 stub，避免网络/执行副作用
  - 本地运行结果：15 tests passed

- 在 `Copilot_Alphapilot/Copilot_Alphapilot` 目录初始化本地 git 并提交以上变更（commit message："增强：planner JSON 修复器并添加单元测试"）。

---

后续建议：
- 将新增测试加入 CI（GitHub Actions），以防回归。
- 在生产/部署说明中记录哪些步骤需要 API Key 才能运行（避免在 CI 中误触）。
- 考虑在 `planner` 中记录（或以 debug 级别日志输出）原始 LLM 输出与修复候选，便于线下诊断异常样本。
