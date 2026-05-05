# 智能体执行引擎目标（2026-03-02）

1) 打造真正的“智能体执行引擎”
让我的助手不仅能执行任务，还能：

自主拆解任务

规划步骤

监控执行状态

失败自动恢复

多 worker 协同

这是从“工具”到“智能体”的关键跨越。

# ModelRouter / 模型路由器

## 简要说明 / Overview
**中文：** ModelRouter 是一个基于 FastAPI 的轻量服务，目标是统一路由多个 AI 模型请求、管理缓存、对模型进行打分并生成重构计划。／**English:** ModelRouter is a FastAPI-based lightweight service for routing requests across multiple AI model providers, managing caching, scoring models, and generating refactor plans.

---

## 主要特性 / Key features ✅
- 支持多模型路由（本地适配器、Hugging Face、OpenAI 等）／Route requests to multiple model providers (adapters, HF, OpenAI).
- 响应缓存与缓存管理／Response caching to improve latency and throughput.
- 模型评分与自动选择最优模型／Model scoring to pick the best-performing model automatically.
- 重构计划生成（用于分析与建议）／Refactor-plan generation for analysis and recommendations.
- 可扩展的 adapter 层便于新增模型或存储后端／Extensible adapter layer to add new models or storage backends.

---

## 快速开始 / Quick start 🚀
1. 克隆仓库 / Clone the repo:
   ```bash
   git clone <repo-url>
   cd model-router
   ```
2. 创建并激活虚拟环境（Windows 示例）/ Create & activate venv (Windows):
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```
3. 安装依赖 / Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. 本地运行 API / Run locally:
   ```bash
   uvicorn model_router_api:app --reload
   ```
5. （可选）使用 Docker / With Docker:
   ```bash
   docker build -t model-router .
   docker run -p 8000:8000 model-router
   ```

---

## 配置 / Configuration 🔧
- 环境变量样例见 `.env.example`。
- 主要依赖在 `requirements.txt`，项目配置在 `pyproject.toml`。

---

## 运行与测试 / Run & Test ✅
- 启动开发服务器：`uvicorn model_router_api:app --reload`
- 运行单元与集成测试：
  ```bash
  pytest -q
  ```
- 填充缓存（示例脚本）：`python scripts/seed_cache.py`
- 评估模型：`python scripts/evaluate_models.py`

---

## 项目结构（概要） / Project structure (brief)
- `model_router_api.py` — FastAPI 入口 / FastAPI entrypoint
- `router/` — 核心路由、评分、缓存与计划生成逻辑 / core routing, scoring, caching, plan generation
- `adapters/` — 模型与存储适配器（Redis、SQLite、HF 等）/ adapters for models & storage
- `scripts/` — 辅助脚本（seed、evaluate）/ helper scripts
- `tests/` — 单元与集成测试 / unit & integration tests
- `docs/`, `examples/` — 文档与示例 / docs & examples

---

## 贡献 / Contributing 🤝
欢迎提交 issue 或 PR。请遵循仓库现有的代码风格并补充测试。／Please open an issue or PR — follow existing code style and add tests where applicable.

> 如果你希望 README 使用“中英并列（每段并排）”或只要英文/中文版本，告诉我我可以调整。／If you prefer side-by-side bilingual layout or a single-language README, tell me and I'll adjust.

---

## 部署到 Hugging Face（Spaces） / Deploy to Hugging Face Spaces 🚀
- 推荐使用 **Docker Space**（部署完整 FastAPI 服务 —— 与本地行为一致）。
- 上传方式：把整个仓库推到 HF Space（连接 GitHub repo 或直接上传）；**不要提交密钥或 .env**。
- 环境变量：在 Space Settings -> Secrets 中添加所需密钥（例如 OPENAI_API_KEY、HF_TOKEN、REDIS_URL 等）。
- 端口：Spaces 会注入 `PORT` 环境变量，容器需监听该端口（仓库已支持读取 `PORT`）。
- Demo：仓库包含 `app.py`（Gradio demo），可单独部署为非-Docker Space 或本地演示。
- 注意事项：资源与配额有限 — 若需要高可用/吞吐/企业 SLA，请考虑 Hugging Face Inference Endpoints 或云服务（GCP/AWS/Azure）。

---

## 联系 / Contact
遇到问题请打开 GitHub issue，或参考 `docs/` 目录中的文档。／Open a GitHub issue for problems or consult the `docs/` folder.

---

## 许可证 / License
请查看仓库中的 `LICENSE`（若存在）。／Check the repository `LICENSE` file if present.
