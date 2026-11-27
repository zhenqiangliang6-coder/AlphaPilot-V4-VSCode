# vv84 R5–R10 隔离端到端验收报告

## 最终结论：PASS

在干净的隔离工作区中，R5 至 R10 六轮在**同一次 pytest 运行**中全部通过。最终命令退出码为 **0**：6 passed、0 failed、1 deselected，用时 18 分 10 秒。唯一 deselected 项不属于 R5–R10 六轮。

## 完整 R5–R10 运行结果

| 轮次 | 任务 ID | 结果 |
|---|---|---|
| R5 架构设计 | `453f1469-e705-4263-aa35-58ec04ca6875` | PASS；链路、执行、质量、治理四项通过 |
| R6 核心实现 | `69151743-37c4-4cc7-bdcd-cc2c6b053fdf` | PASS；四项通过 |
| R7 Bug 修复 | `3de746a6-5a27-4858-9f11-15c07b5519ec` | PASS；注入的语法错误被修复，四项通过 |
| R8 库存功能 | `cbeb977d-1252-4960-a208-6705e2a36335` | PASS；四项通过，交付门新增的 service 路径已授权 |
| R9 级联修改 | `dd6da514-14cf-480c-957a-1aa5e1b1acba` | PASS；四项通过 |
| R10 服务层重构 | `0a0d1175-1725-4b75-a05d-7e58460a8567` | PASS；四项通过 |

实际执行命令：

```text
python -u -m pytest python_worker/tests/test_observe_task_system.py::TestShopFlowProductionPath -k "round5 or round6 or round7 or round8 or round9 or round10" -v -s
```

最终结果：

```text
================ 6 passed, 1 deselected in 1090.88s (0:18:10) =================
pytest_exit_code=0
```

## 隔离环境与证据

- Node API：`http://127.0.0.1:3303`；这是本次验收使用的隔离端口，不代表前端必须改用 3303。
- Redis：隔离容器 `alphapilot-vv84-redis`，端口 `16382`。
- PostgreSQL：测试数据库 `alphapilot_test_vv84`。
- 工作区：`D:\Copilot_Alphapilot\vv84_shopflow_isolated`。
- 逐轮任务 ID 和运行参数：[r5_r10_retry_runtime.json](./r5_r10_retry_runtime.json)。
- 完整 pytest、Node API 与 Worker 原始日志保留在本地验收目录；本次 GitHub 更新不包含原始日志，仅提交中文报告、工作摘要和运行元数据。

## 修复与架构契约核验

R8 的根因是：交付门可能在处理后续步骤时追加 FileOps，但此前授权范围和生成文件清单计算得过早，导致 Node API 拒绝未进入授权范围的 service 文件。现在在所有交付门完成后，才从最终 FileOps 生成授权范围和 manifest。

最终 R8 授权记录确认包含：

- `backend/services/__init__.py`
- `backend/services/inventory_service.py`

两文件均已落盘。此结果符合架构信条：Worker 保持任务执行和结果的真相源地位，Node API 负责协议与映射；没有绕过授权或删除安全边界。之前 Docker 中断的那次运行中，R9/R10 因 R8 产物缺失而 fail-closed；恢复隔离容器后，本报告记录的完整重跑通过。

## 历史失败运行说明

此前一次完整重跑在 R5–R7 通过后，因 Docker 服务中断、Redis 连接被拒绝而未完成 R8；R9/R10 随后因缺少 R8 产物而失败关闭。该次运行退出码为 1，历史日志仍保留在本地验收目录。之后恢复隔离 Redis/PostgreSQL，并从同一基线完成了本报告记录的全量 R5–R10 通过运行。

此前另有一次仅运行 R8–R10 的成功恢复运行；它作为补充证据保留，不替代本报告中的完整六轮成功运行。

## 后续专家建议

1. 保留“交付门之后生成最终授权范围”的回归测试，防止 FileOps 与授权范围再次漂移。
2. 修正无效的 ModelScope 模型别名 `deepseek-v4.1-flash`，避免无效调用造成额外等待；本次运行中降级到 `Qwen/Qwen3.8-27B` 后仍成功。
3. 明确授权并应用 FileOps 后的任务生命周期：R8 的授权已批准且文件已应用，但 Redis 中 Worker 结果仍为 `awaiting_authorization`。应明确这一状态与最终 `COMPLETED` 的转换契约。
