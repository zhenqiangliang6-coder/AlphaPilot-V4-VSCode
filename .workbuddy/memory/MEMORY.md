# Alphapilot 项目长期约定

## 用户目标与协作偏好（2026-11-17 明确）

- **总目标**：推进 Alphapilot 进化成为优秀的编程助手。用户以全栈专家标准要求执行，重视"工业级自愈 + 简洁交付"。
- **操作简洁化**：用户经过一年已深刻理解底层，**不再需要早期"三条独立命令逐步观察"的模式**。验收驱动统一封装为单脚本 `python_worker/tests/_run_shopflow_pass.sh`，一条命令完成"清旧实例 → 起 Node/Worker → 等 READY → 两遍循环 → 一遍红 STOP → 收尾清理"。三个进程照常启动，只是不再手动逐个敲命令。
- **不要再退化回手工分步骤**：除非脚本本身故障需诊断，否则不要拆成多个独立后台命令让用户观察中间态。

## 验收铁律（不可更改）

- ShopFlow 验收 = R5–R10 六轮 + summary 汇总，pytest 每遍收集 **7 个用例**；通过标准唯一：`7 passed, 0 failed`，**连续两遍**（用户 2026-11-17 从三遍改为两遍口径）。一遍红即 STOP，不烧剩余遍数。
- 被取消/失败的后台任务不得重启；每代只启动加载新代码的**全新** Worker/Node 实例（精确按 3000 端口 + qwen_worker_v2 命令行清理旧实例）。
- 判卷契约（`test_observe_task_system.py` 端点集合、状态码、禁止 OrderItem、冻结模型、Column 契约等）不得放宽；修复只能落在生产侧确定性守卫（`delivery_gate.py`），FAIL-CLOSED。
- 一遍红即由助手自主定位 → G10.4x 修复 → 起新实例 → 重跑完整两遍，不等待用户确认；仅资源层硬阻塞（额度 429/DNS）需如实报卡点。

## 代码规模与分包约定（2026-11-17 用户明确）

- **硬约束**：单个源码文件尽量不超过 1800 行（软告警线 1800，硬线 1900）。理由：VSCode/语言服务器对 2000 行以上文件的语义解析、跳转、补全明显变差，且不符合 Python 优雅。
- **分包方式**：超过阈值时以专家式"能力分包"自动拆分；**功能性平行的模块尽量平级放置，不要深嵌套**（如 `gate/imports.py`、`gate/syntax.py`、`gate/contracts.py` 平级，而非 `gate/contract/model/inventory/repair.py` 深层路径）。
- **专家 nuance**：行数是信号不是教条，按内聚职责切、不按行数均分；切分不得制造循环导入或破坏共享状态。
- **当前超标实况（2026-11-17 实测）**：Python 仅 2 个破线——`tests/test_observe_task_system.py` 2803 行（判卷文件，最高敏感）、`delivery_gate.py` 2543 行（生产守卫）；次级 `step_runner.py` 1375、`memory_service.py` 1361；JS 最大 `node-api/index.js` 1454（未破线）。
- **执行时机**：这两个超标文件恰是判卷与守卫核心，且被每代跑批加载；**必须在两遍验收收官后的独立窗口专项分包**，全程回归 + 重新三/两遍验收，绝不在跑批中途动、绝不放宽判卷语义。拆分判卷文件时特别保护模块级共享状态（verdict 登记、baseline、fixture）。

## 运行通道与环境

- 当前 LLM 通道：魔搭 ModelScope（`LLM_PROVIDER=modelscope`，主模型 `Qwen/Qwen3.8-Flash-Next`，直连无代理，A/B/C 三个 key 轮转）；dashscope 曾间歇 ConnectTimeout 导致级联失败。切换前备份 `.env.bak_v32`。
- Worker 必须以包模块方式启动：`PYTHONPATH=ROOT python -u -m python_worker.agents.qwen.qwen_worker_v2`（相对导入 + `-u` 消除 stdout 块缓冲）。
- 工作区 `C:/Users/49772/Desktop/shopflow_ecommerce`；基线快照 `python_worker/tests/_shopflow_baseline.json` 含 `.db` 的 base64，每遍 `setup_class` bit-for-bit 复位。
- 核心回归 G10 集 179 passed；既有 3 个失败（`test_intent_router` / `test_incremental_contract` / `test_traceback_boundary`）与 G10 改动无关。
