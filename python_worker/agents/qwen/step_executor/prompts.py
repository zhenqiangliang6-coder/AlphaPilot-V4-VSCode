# -*- coding: utf-8 -*-
# step_executor/prompts.py
# ---------------------------------------------------------
# 所有步骤类型的 prompt 模板（v3.0 执行链版）
# ---------------------------------------------------------

__all__ = [
    # 核心步骤 prompt
    "analyze_prompt",
    "plan_prompt",
    "write_prompt",
    "creative_write_prompt",
    "refine_prompt",
    
    # 扩展步骤 prompt
    "test_prompt",
    "fix_prompt",
    "profile_prompt",
    "doc_prompt",
    "docstring_prompt",
    "optimize_prompt",

    # ⭐ v2.8 新增
    "optimize_prompt_v28",
]


def analyze_prompt(user_input: str, context: dict = None) -> str:
    memory_section = ""
    if context:
        mem = context.get("meta", {})
        task_goal = mem.get("task_goal", "")
        prior_files = mem.get("prior_changed_files", [])
        repair_rounds = mem.get("repair_rounds", 0)
        if task_goal or prior_files:
            memory_section = "\n\n【上下文记忆】：\n"
            if task_goal:
                memory_section += f"- 任务目标: {task_goal}\n"
            if prior_files:
                memory_section += f"- 之前修改的文件: {', '.join(prior_files)}\n"
            if repair_rounds:
                memory_section += f"- 已修复轮数: {repair_rounds}\n"

    return f"""
请分析下面的任务描述，并提取关键需求点：

【用户任务描述】：
{user_input}{memory_section}

请输出：
1. 任务的核心目标
2. 需要实现的功能点
3. 输入与输出要求
4. 可能的边界情况
5. 需要注意的风险点

请使用结构化的自然语言，不要生成代码。

---
【执行维度标记 — 必须输出】
在分析末尾附加一个 JSON 块，准确标记任务的执行维度。该 JSON 将被引擎解析并决定后续执行步骤。

[EXECUTION_PROFILE]
{{
  "output_mode": "text|document|code|mixed",
  "workspace_dependency": "none|read_only|read_write",
  "target_format": "py|md|txt|json|html|plain_text",
  "requires_fileops": true|false,
  "requires_workspace_scan": true|false,
  "requires_test": true|false,
  "estimated_complexity": "simple|moderate|complex"
}}

字段说明：
- output_mode: 纯文本文档用 "text"，需生成代码用 "code"，需输出 Markdown/文档用 "document"
- workspace_dependency: 无需访问项目文件用 "none"，只需读取用 "read_only"，需创建/修改文件用 "read_write"
- target_format: 输出的主要文件格式
- requires_fileops: 是否需要创建/修改文件
- requires_workspace_scan: 是否需要扫描项目文件
- requires_test: 是否需要生成和运行测试
- estimated_complexity: 任务复杂度评估

请严格按照你的任务理解填写，不要留空或使用占位符。
"""


def plan_prompt(analysis: str) -> str:
    return f"""
下面是对任务的分析结果，请根据这些内容生成代码结构规划：

【分析结果】：
{analysis}

请输出：
1. 代码的整体结构（模块/函数/类）
2. 每个函数的职责
3. 输入与输出设计
4. 伪代码（如果有必要）
5. 需要注意的边界情况
6. 若任务会修改代码，最后给出一条建议执行的测试命令，单独写成 `TEST_COMMAND: <完整命令>`；只提出命令，绝不执行。命令应使用项目已有的测试工具，不得包含命令链、管道或重定向。

请使用自然语言描述，不要生成完整代码。
"""


def mentor_plan_prompt(analysis: str) -> str:
    return f"""
根据下面的项目分析，为用户制定针对当前项目的人工测试流程。只提供说明，不生成代码、不运行命令、不修改文件。

【项目分析】：
{analysis}

请按以下标题输出：
1. 启动方式
2. 测试入口
3. 操作步骤
4. 预期结果
5. 失败判断

只陈述分析中有证据支持的项目事实。资料未提供的内容请明确标注“未从当前项目资料确认”，不要猜测。
"""


# =========================================================
# P1: 动态多语言示例构建器（确定性，零 LLM）
# =========================================================

_FORMAT_MAP = {
    "py":      ("Python",     "# FILE: backend/main.py",          "# FILE: backend/models/user.py"),
    "ts":      ("TypeScript", "# FILE: frontend/src/api/tasks.ts", "# FILE: frontend/src/types/index.ts"),
    "tsx":     ("React TSX",  "# FILE: frontend/src/App.tsx",     "# FILE: frontend/src/components/Header.tsx"),
    "jsx":     ("React JSX",  "# FILE: frontend/src/App.jsx",     "# FILE: frontend/src/components/Header.jsx"),
    "js":      ("JavaScript", "# FILE: frontend/src/utils.js",     "# FILE: frontend/src/api/client.js"),
    "json":    ("JSON",       "# FILE: package.json",             "# FILE: tsconfig.json"),
    "html":    ("HTML",       "# FILE: frontend/index.html",      "# FILE: frontend/src/template.html"),
    "css":     ("CSS",        "# FILE: frontend/src/styles.css",  "# FILE: frontend/src/components/Header.css"),
    "md":      ("Markdown",   "# FILE: README.md",                "# FILE: docs/api.md"),
    "yaml":    ("YAML",       "# FILE: docker-compose.yml",       "# FILE: .github/workflows/ci.yml"),
    "yml":     ("YAML",       "# FILE: docker-compose.yml",       "# FILE: .github/workflows/ci.yml"),
    "sql":     ("SQL",        "# FILE: schema.sql",               "# FILE: migrations/001_init.sql"),
    "sh":      ("Shell",      "# FILE: scripts/setup.sh",         "# FILE: scripts/deploy.sh"),
    "env":     ("环境变量",    "# FILE: .env.example",             "# FILE: .env"),
    "toml":    ("TOML",       "# FILE: pyproject.toml",           "# FILE: Cargo.toml"),
    "java":   ("Java",       "# FILE: src/main/java/com/example/App.java", "# FILE: src/main/java/com/example/model/Task.java"),
    "kt":     ("Kotlin",     "# FILE: src/main/kotlin/com/example/App.kt", "# FILE: src/main/kotlin/com/example/model/Task.kt"),
    "go":     ("Go",         "# FILE: cmd/server/main.go",      "# FILE: pkg/models/task.go"),
    "rs":     ("Rust",       "# FILE: src/main.rs",              "# FILE: src/models/task.rs"),
    "xml":    ("XML",        "# FILE: pom.xml",                  "# FILE: AndroidManifest.xml"),
}


def _build_language_examples(target_formats: list) -> str:
    """根据检测到的目标语言动态构造 # FILE: 示例

    核心原则：消除 Python 中心偏见 ——
    旧版永远只展示 # FILE: path/to/file.py，
    导致 LLM 在跨语言任务中被锚定到 Python 输出。

    现在：如果任务包含 TypeScript，展示 .ts 和 .tsx 示例；
    如果只有 Python，展示 .py 示例（保持向后兼容）。
    """
    if not target_formats:
        target_formats = ["py"]

    examples = []
    for fmt in target_formats:
        info = _FORMAT_MAP.get(fmt)
        if info:
            label, path1, path2 = info
            examples.append(
                f"  对于 {label} 文件，例如：\n"
                f"    {path1}\n"
                f"    {path2}"
            )

    if not examples:
        # 未知格式：回退到通用示例
        examples.append(
            "  对于代码文件，例如：\n"
            f"    # FILE: src/module.{target_formats[0]}"
        )

    return "【目标文件格式示例】：\n" + "\n\n".join(examples) + "\n"


def _build_cross_language_examples(target_formats: list) -> str:
    """根据检测到的语言组合生成跨语言常见任务示例"""
    if not target_formats:
        target_formats = ["py"]

    sections = []

    # Python 项目示例
    if "py" in target_formats:
        sections.append(
            "示例 — Python FastAPI 项目（关键模式必须遵守）：\n"
            "# FILE: backend/models/task.py\n"
            "from enum import Enum\n"
            "from pydantic import BaseModel\n"
            "class TaskStatus(str, Enum):  # ⚠️ 必须是 str+Enum，不能是纯 str 类\n"
            "    PENDING = \"pending\"\n"
            "    IN_PROGRESS = \"in_progress\"\n"
            "    DONE = \"done\"\n"
            "class Task(BaseModel):\n"
            "    id: str\n"
            "    title: str\n"
            "    status: TaskStatus = TaskStatus.PENDING\n"
            "\n"
            "# FILE: tests/test_tasks.py      # ⚠️ 测试必须在 tests/ 目录\n"
            "import pytest\n"
            "from fastapi.testclient import TestClient\n"
            "from backend.main import app\n"
            "@pytest.fixture  # ⚠️ 用 fixture 隔离测试数据\n"
            "def client():\n"
            "    return TestClient(app)\n"
            "def test_create_task(client):\n"
            "    response = client.post(\"/tasks\", json={\"title\": \"Test\"})\n"
            "    assert response.status_code == 200\n"
            "def test_nonexistent_task_404(client):  # ⚠️ 必须包含 404 测试\n"
            "    response = client.patch(\"/tasks/bad-id\", json={\"status\": \"done\"})\n"
            "    assert response.status_code == 404\n"
            "\n"
            "# FILE: requirements.txt\n"
            "fastapi>=0.100.0\n"
            "uvicorn>=0.23.0\n"
            "pytest>=7.0\n"
            "httpx>=0.24.0\n"
            "\n"
            "# FILE: backend/routers/tasks.py\n"
            "from fastapi import APIRouter, HTTPException\n"
            "from backend.models.task import Task, TaskCreate, TaskStatus\n"
            "router = APIRouter()\n"
            "@router.post(\"/tasks\")\n"
            "def create_task(data: TaskCreate):\n"
            "    task = Task(title=data.title, assignee=data.assignee)  # ⚠️ 不用 .dict()，直接传字段\n"
            "    return task"
        )

    # TypeScript / React 项目示例
    if "ts" in target_formats or "tsx" in target_formats:
        frontend_ext = "tsx" if "tsx" in target_formats else "ts"
        sections.append(
            f"示例 — TypeScript/React 项目（关键模式必须遵守）：\n"
            f"# FILE: frontend/src/App.tsx\n"
            f"# FILE: frontend/src/api/tasks.ts\n"
            f"// ⚠️ 健康检查不能用 no-cors，要用简单 GET 请求：\n"
            f"async function checkBackend(): Promise<boolean> {{\n"
            f"  try {{ await fetch('http://localhost:8000/'); return true; }} catch {{ return false; }}\n"
            f"}}\n"
            f"\n"
            f"# FILE: frontend/package.json\n"
            f'{{\n  "name": "app",\n'
            f'  "dependencies": {{\n    "react": "^18.0.0",\n    "react-dom": "^18.0.0"\n  }},\n'
            f'  "devDependencies": {{\n    "typescript": "^5.0.0",\n'
            f'    "@types/react": "^18.0.0"\n  }},\n'
            f'  "scripts": {{\n    "start": "react-scripts start",\n    "build": "react-scripts build"\n  }}\n'
            f'}}'
        )

    # Java 项目示例
    if "java" in target_formats:
        sections.append(
            "示例 — Java 项目：\n"
            "# FILE: src/main/java/com/example/App.java\n"
            "# FILE: src/main/java/com/example/model/Task.java\n"
            "# FILE: pom.xml"
        )

    # JavaScript 项目示例
    if "js" in target_formats and "ts" not in target_formats and "tsx" not in target_formats:
        sections.append(
            "示例 — JavaScript 项目：\n"
            "# FILE: frontend/src/utils.js\n"
            "# FILE: frontend/src/api/client.js\n"
            "# FILE: package.json"
        )

    # 纯配置项目示例
    config_only = all(f in ("json", "yaml", "yml", "toml", "env", "md") for f in target_formats)
    if config_only and not sections:
        sections.append(
            "示例 — 配置项目：\n"
            "# FILE: docker-compose.yml\n"
            "# FILE: .env.example\n"
            "# FILE: README.md"
        )

    if not sections:
        sections.append(
            "示例：\n"
            "# FILE: src/code.ext\n"
            "# FILE: config.ext"
        )

    return "【常见任务示例】：\n" + "\n\n".join(sections)


# ── 架构感知护栏 ──────────────────────────────────────────

def _build_architecture_guardrails(target_formats: list = None) -> str:
    """根据目标语言生成架构层隔离规则。

    当项目使用 Python 时，注入 SQLAlchemy ORM / Pydantic Schema / FastAPI Router
    的分层约束，防止 LLM 在重构时错误替换模型层。

    target_formats: 检测到的目标文件格式列表，如 ["py", "ts"]。
                    若包含 "py"，则注入 Python 架构规则。
    """
    if not target_formats:
        return ""

    if "py" not in target_formats:
        return ""

    return """
12. ⭐⭐ 架构层隔离规则（Python 项目强制执行）：
    AlphaPilot 项目采用严格的分层架构。每层有固定的文件类型和父类要求：

    ┌─────────────────────────────────────────────────┐
    │ 目录           │ 文件类型   │ 父类/特征          │
    ├─────────────────────────────────────────────────┤
    │ backend/models/ │ SQLAlchemy │ 类必须继承 Base   │
    │                 │ ORM 模型   │ 含 __tablename__  │
    │                 │            │ 含 Column 导入    │
    ├─────────────────────────────────────────────────┤
    │ backend/schemas/│ Pydantic   │ 类必须继承 BaseModel│
    │                 │ Schema     │ 不含 SQLAlchemy    │
    ├─────────────────────────────────────────────────┤
    │ backend/routers/│ FastAPI    │ 定义 APIRouter    │
    │                 │ 路由       │ 无业务逻辑         │
    ├─────────────────────────────────────────────────┤
    │ backend/services/│ 业务逻辑  │ 可被 routers 调用  │
    │                 │ 服务层     │ 不定义 ORM/Schema  │
    └─────────────────────────────────────────────────┘

    必须遵守的铁律：
    a) 重构/提取 service 层时，绝不修改 backend/models/ 中的 ORM 模型文件
       - ORM 模型继承 Base（来自 backend.database）
       - 使用 Column(String/Integer/Float) 定义字段
       - 设置 __tablename__ 表明表名
       - 如果 models/ 文件只包含 Pydantic BaseModel（没有继承 Base），数据库操作将完全失败
    b) 重构/提取 service 层时，绝不修改 backend/schemas/ 中的 Pydantic schema 文件
       - Schema 继承 BaseModel（来自 pydantic）
       - Schema 中不包含 SQLAlchemy Column 或 __tablename__
    c) 提取 service 层时，只做以下操作：
       - 新建 backend/services/xxx_service.py（业务逻辑）
       - 修改 backend/routers/xxx.py（路由层，移除业务逻辑，改为调用 service）
       - 如需更新 backend/main.py 中的路由注册
    d) ORM 模型 ≠ Pydantic schema：它们是不同类型，不能互换
       - 错误示例：# FILE: backend/models/inventory.py → class Inventory(BaseModel):  ⚠️ 致命错误！
       - 正确示例：# FILE: backend/models/inventory.py → class Inventory(Base): ... __tablename__ = "inventory"

    如果你的任务涉及架构变更（新增功能/重构），必须先在脑海中明确：
    - 哪些文件属于 models/（不能改）
    - 哪些文件属于 schemas/（不能改）
    - 哪些文件属于 routers/（可以改）
    - 哪些文件需要新创建在 services/（可以创建）
"""


def write_prompt(plan: str, user_request: str = "", target_formats: list = None) -> str:
    """
    write 步骤的 prompt：根据规划生成代码（多文件协议 v3.0）

    包含用户原始请求以保持上下文连贯。
    
    target_formats: 检测到的目标文件格式列表，如 ["py", "ts", "tsx", "json"]
                    用于动态生成 # FILE: 示例，消除 Python 中心偏见。
                    若为 None 或空，默认使用 ["py"]（向后兼容）。
    """
    if not target_formats:
        target_formats = ["py"]
    user_section = ""
    if user_request:
        user_section = f"""
====================
【用户的原始请求 — 这是你最需要满足的目标】：
{user_request}

"""
    
    # === 动态多语言示例 ===
    language_examples = _build_language_examples(target_formats)
    
    # === 跨语言常见任务示例 ===
    cross_lang_examples = _build_cross_language_examples(target_formats)
    
    return f"""你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成结果：

==========================
# FILE: <相对路径>
<代码内容>

# TEST: <测试文件路径>
<测试代码内容>

# DOC: <文档路径>
<文档内容>

# META:
{{"version": "1.0", "author": "AlphaPilot"}}

# DEPENDS:
{{"requirements": ["dependency>=version"]}}

# DELETE: <用户明确指定的工作区相对路径>
==========================
{user_section}
【代码规划】：
{plan}

{language_examples}

⭐⭐⭐ 强制要求（必须遵守）：

1. 必须使用 "# FILE:" 开头声明文件路径  
   - 格式：# FILE: path/to/file.ext
   - 路径必须是相对路径，从项目根目录开始
   - 扩展名必须匹配实际文件类型（.py / .ts / .tsx / .js / .json 等）
   
2. 每个文件必须单独一个 # FILE: 块  
   - 不要将多个文件合并到一个块中
   - 每个文件之间用空行分隔
   
3. 支持新协议：
   - # TEST: 用于生成单元测试
   - # DOC: 用于生成文档说明
   - # META: 用于声明元数据（JSON格式）
   - # DEPENDS: 声明依赖后必须生成对应的依赖文件（见规则10）
   
4. 不得省略 # FILE:  
   - Worker 将根据 # FILE: 自动生成 FileOps
   - 没有 # FILE: 会导致多文件功能失效
   
5. 不得输出未声明路径的代码  
   - 所有代码必须在 # FILE: 块内

6. 代码完整性（最高优先级）：
   - 每个函数必须有完整的、可运行的实际实现
   - 严禁使用 pass、...、raise NotImplementedError 作为函数体
   - 即使是最简单的工具函数也要给出实际逻辑
   - 如果确实无法确定实现细节，给出最合理的实现并添加注释

7. 代码质量要求：
   - 代码必须可运行
   - 变量命名清晰
   - 逻辑结构与规划一致
   - 包含必要的注释和文档字符串

8. ⭐ 包结构完整性（工业级强制）：
   生成的代码必须保证完整的包/模块结构，确保项目可直接运行：
   - Python: 每个目录必须生成 __init__.py（即使是空文件），确保 "from backend.models.task import Task" 可正常工作
   - Java: 包路径必须对应目录结构（如 com.example.model → src/main/java/com/example/model/）
   - TypeScript/JavaScript: 如有需要生成 index.ts/js 作为 barrel export
   - 前端项目: 包导入路径必须与生成的文件路径一致
   - 每生成一个 # FILE: 子目录下的 Python 文件，必须同时生成对应目录的 __init__.py
   - 示例：生成 backend/routers/tasks.py 时，必须同时生成 backend/__init__.py, backend/routers/__init__.py

9. 删除任务规则：
   - 仅当用户明确要求删除且提供了明确相对路径时，才为每个目标输出一行 "# DELETE: 相对路径"
   - DELETE 行不跟随文件内容；不得输出 shell 命令、代码删除逻辑或其他文件操作
   - 路径不明确时不要猜测，要求用户澄清

10. ⭐ 依赖文件强制生成（工业级要求）：
    # DEPENDS: 声明是不够的——你必须同时生成真实的依赖文件：
    - Python 项目: 必须生成 # FILE: requirements.txt，内容为每行一个包名（如 fastapi>=0.100.0）
    - Node.js / React 项目: 必须生成 # FILE: package.json，包含 dependencies 和 devDependencies
    - Java / Kotlin (Maven): 必须生成 # FILE: pom.xml
    - Java / Kotlin (Gradle): 必须生成 # FILE: build.gradle
    - Go 项目: 必须生成 # FILE: go.mod
    - Rust 项目: 必须生成 # FILE: Cargo.toml
    - 规则: 每当你使用 # DEPENDS: 声明依赖，你必须紧接着生成对应的依赖文件 # FILE: 块
    - 示例组合:
      # DEPENDS:
      {{"requirements": ["fastapi>=0.100.0", "uvicorn>=0.23.0", "pytest>=7.0"]}}

      # FILE: requirements.txt
      fastapi>=0.100.0
      uvicorn>=0.23.0
      pytest>=7.0
      httpx>=0.24.0

11. ⭐ 测试质量门槛（弱模型也需达标）：
    无论模型能力如何，测试代码必须满足以下最低标准：
    - 测试文件必须放在 tests/ 目录，不能放在 backend/ 等源码目录
    - 使用 @pytest.fixture 创建 TestClient，在每个测试前重置状态
    - 每个 API 端点至少覆盖：成功场景 + 异常场景（404/400）
    - 至少包含以下测试用例：
      * test_root: GET / 返回 200
      * test_create_task: POST 创建任务返回 200，断言返回字段
      * test_get_tasks_empty: GET 空列表返回 []
      * test_get_tasks_with_data: 创建后 GET 返回非空列表
      * test_update_nonexistent_task: PATCH 不存在的 ID 返回 404
      * test_delete_nonexistent_task: DELETE 不存在的 ID 返回 404

{_build_architecture_guardrails(target_formats)}

{cross_lang_examples}

12. ⚠️ 格式污染防护（工业级强制）：
    以下标记是 Worker 内部步骤名，严禁作为代码内容输出：
    - 禁止在 # FILE: 块内输出 refine:、test:、write:、fix:、plan:、analyze: 等步骤标记
    - 禁止在代码块内输出 Markdown 标题（如 ## Refine、### Test）
    - 代码文件的每一行都必须是合法代码或注释，不得混入 CoT/chain-of-thought 文本
    - 如果需要对代码进行评估或审查，请确保这些文字在 # FILE: 块之外
    - 反面示例（禁止）：
      # FILE: backend/models/order.py
      ...（正常代码）...
      refine:
      The code looks solid. 1. func is imported.
      test:
      import pytest
      ...
    - 正面示例（正确）：
      # FILE: backend/models/order.py
      ...（完整的合法 Python 代码，无多余内容）...

只输出多文件协议内容，不要任何解释性文字。
"""


# ── P3: 聚焦写 Prompt（串行多轮写） ────────────────────────────

def write_prompt_focused(
    plan: str,
    user_request: str = "",
    file_group: list = None,
    target_formats: list = None,
    round_context: str = "",
    round_idx: int = 1,
    total_rounds: int = 1,
) -> str:
    """P3 聚焦写 prompt：只针对指定文件组生成代码。

    与 write_prompt 的区别：
    - 明确列出本轮要生成的文件路径
    - 注入前几轮的上下文（已生成文件列表）
    - 提示 LLM 只生成本轮文件，不重复
    - token 占用显著减少（plan 被裁剪为 focused_plan）

    参数:
        plan: 已聚焦的计划文本（只含当前轮相关描述）
        user_request: 用户原始请求
        file_group: 本轮要生成的文件路径列表
        target_formats: 目标格式列表
        round_context: 前几轮已生成文件的摘要
        round_idx: 当前轮次（1-based）
        total_rounds: 总轮数
    """
    file_group = file_group or []

    user_section = ""
    if user_request:
        user_section = f"""
====================
【用户的原始请求 — 这是你最需要满足的目标】：
{user_request}

"""

    language_examples = _build_language_examples(target_formats)

    # 本轮文件清单
    file_list_str = "\n".join(f"  - {f}" for f in file_group)
    round_hint = ""
    if total_rounds > 1:
        round_hint = f"""
══════════════════════════════════════
【第 {round_idx}/{total_rounds} 轮 — 只生成本轮指定的文件】
{round_context}

本轮需要生成的文件（共 {len(file_group)} 个）：
{file_list_str}

⚠️ 重要：
- **只生成上面列出的 {len(file_group)} 个文件**，不要生成其它文件
- 不要重复前几轮已生成的文件
- 每个文件使用 # FILE: 声明路径
══════════════════════════════════════
"""

    return f"""你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成结果：

==========================
# FILE: <相对路径>
<代码内容>

# TEST: <测试文件路径>
<测试代码内容>

# DEPENDS:
# DELETE: <用户明确指定的工作区相对路径>
==========================
{user_section}
【代码规划（已聚焦到本轮文件）】：
{plan}

{language_examples}
{round_hint}

⭐⭐⭐ 强制要求（必须遵守）：

1. 必须使用 "# FILE:" 开头声明文件路径
2. 每个文件必须单独一个 # FILE: 块
3. 不得省略 # FILE:
4. 不得输出未声明路径的代码
5. 代码完整性（最高优先级）：
   - 每个函数必须有完整的、可运行的实际实现
   - 严禁使用 pass、...、raise NotImplementedError 作为函数体
   - 即使是最简单的工具函数也要给出实际逻辑
6. 代码质量要求：
   - 代码必须可运行
   - 变量命名清晰
   - 逻辑结构与规划一致
   - 包含必要的注释和文档字符串
7. ⭐ 包结构完整性：Python 项目每个子目录必须生成 __init__.py；Java 项目包路径对应目录结构

8. ⭐ 依赖文件强制生成：# DEPENDS: 声明后必须生成真实依赖文件：
   - Python → # FILE: requirements.txt（每行一个包名）
   - Node.js/React → # FILE: package.json（含 dependencies）
   - 示例：声明 # DEPENDS: 之后紧跟 # FILE: requirements.txt

9. ⭐ 测试质量门槛：测试文件必须放在 tests/ 目录；使用 @pytest.fixture；每个端点至少成功+异常两个场景

{_build_architecture_guardrails(target_formats)}

10. ⚠️ 格式污染防护：代码块内禁止出现步骤标记（refine:、test:、write:、fix:、plan:、analyze:）或 CoT 文本

只输出多文件协议内容，不要任何解释性文字。
"""


def creative_write_prompt(plan: str, user_request: str = "", intent: str = "creative_writing") -> str:
    """
    创意/对话类意图的纯文本输出 prompt（跳过 FileOps，零浪费）
    不生成 FILE/TEST/DOC/META/DEPENDS 结构，直接输出自然语言内容
    """
    intent_label = {
        "creative_writing": "创作任务",
        "translate": "翻译任务",
        "summarization": "摘要任务",
        "chat": "对话任务",
        "mentor_explain": "教学讲解任务",
    }.get(intent, "内容生成任务")

    user_section = ""
    if user_request:
        user_section = f"\n【用户原始请求】：\n{user_request}\n"
    
    analyze_section = ""
    if plan:
        analyze_section = f"\n【分析参考】：\n{plan}\n"

    return f"""你正在执行一个 {intent_label}。

这是纯文本输出模式，请不要生成任何代码文件、测试文件、文档文件或元数据。
禁止使用以下格式标记：
- 禁止 # FILE:
- 禁止 # TEST:
- 禁止 # DOC:
- 禁止 # META:
- 禁止 # DEPENDS:
- 禁止 # DELETE:
- 禁止代码块包装（除非内容本身是代码片段示例）
{user_section}{analyze_section}
【输出要求】：
1. 直接输出最终内容，不要任何格式包装
2. 内容自然流畅，符合 {intent_label} 场景
3. 不要添加解释、说明或备注
4. 不要模拟文件结构，不要写函数定义包装内容
5. 如果用户要的是诗，直接输出诗；要的是文章，直接输出文章

现在请直接输出："""


def refine_prompt(code: str, exec_summary: str) -> str:
    """
    旧版 refine（单文件为主，兼容多文件提示）
    """
    return f"""
下面是一段 Python 代码及其执行结果，请在保持语义不变的前提下优化代码。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

【执行结果】：
{exec_summary}

要求：
1. 在保证语义不变的前提下优化代码
2. 输出优化后的完整代码（使用 \\`\\`\\`python 代码块）
3. 如果你发现这是多文件项目，请优先使用 v3.0 协议（# FILE:, # TEST:, # DOC:, # META:, # DEPENDS:）
4. 【负向约束】代码块内禁止出现步骤标记（refine:、test:、write:、fix:、plan:）或 CoT 文本，每行必须是合法代码或注释
5. 不要输出任何解释性文字。
"""


def test_prompt(code: str) -> str:
    return f"""
下面是一段 Python 代码，请你为它生成 pytest 风格的单元测试代码。

【被测试代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

要求：
1. 使用 pytest 风格（assert + pytest.raises）
2. 不要 import pytest（Worker 会自动注入 fake pytest）
3. 覆盖正常情况、边界情况、异常情况
4. 包含清晰的断言
5. 输出完整的测试代码（使用 \\`\\`\\`python 代码块）
6. 输出必须是合法 Python 代码，不要包含解释性文字。
"""


def fix_prompt(path: str, code: str, error_message: str, test_code: str = "") -> str:
    """
    生成自动修复代码的 prompt

    参数:
        path: 文件路径
        code: 原始代码字符串
        error_message: 执行错误信息
        test_code: 测试代码（可选，用于测试驱动修复）

    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    base_prompt = f"""
下面是一段代码和它的执行错误，请分析错误原因并给出修复后的完整代码。

文件路径：{path}

【原始代码】：
```python
{code}
```

【执行错误】：
{error_message}
"""

    # ⭐ 新增：如果有测试代码，添加到 prompt 中
    if test_code:
        base_prompt += f"""

【测试代码】（你的修复必须通过以下测试）：
```python
{test_code}
```

⚠️ 重要提示：
- 测试代码定义了接口期望（方法名、参数签名、返回值类型）
- 请确保修复后的代码与测试代码中的调用方式完全匹配
- 如果测试使用了特定的 fixture 或 mock，请参考其使用方式
"""

    base_prompt += """

要求：
1. 分析错误的根本原因
2. 给出修复后的完整代码（使用 ```python 代码块）
3. 简要说明修复了什么问题（可以用注释形式写在代码里）
4. 【负向约束】代码块内禁止出现步骤标记（refine:、test:、write:、fix:、plan:）或 CoT 文本
5. 不要输出解释性自然语言。
"""

    # ⭐ v3.8 动态框架知识注入：根据代码内容识别框架，注入针对性提示
    framework_hints = _detect_framework_hints(code, error_message)
    if framework_hints:
        base_prompt += "\n【框架特定提示】⚠️ 请特别注意以下框架行为：\n" + framework_hints

    return base_prompt


# ═══════════════════════════════════════════════════════════════
# v3.8 动态框架知识注入引擎（确定性规则，零 LLM）
# 根据代码内容自动识别框架并注入针对性提示，提升 fix 准确度
# ═══════════════════════════════════════════════════════════════

_FRAMEWORK_HINTS = {
    "fastapi": [
        "FastAPI 路径参数校验：{task_id} 类型为 str 时，FastAPI 不会自动校验 UUID 格式。"
        "任何字符串都会进入路由处理函数。如果测试期望 404 返回 'Task not found'，"
        "确保你的 HTTPException(status_code=404, detail='Task not found') 在函数体内部抛出，"
        "而非被 FastAPI 路径校验层拦截。",

        "FastAPI TestClient: 测试中的 self.client.patch 或 client.patch 路径末尾不要加 '/'，"
        "否则 FastAPI 会自动 307 重定向，导致 status_code 变为 307 而非 404。",

        "FastAPI 路由注册: 确保 app.include_router(router) 在 main.py 中。"
        "如果 router 定义在 routers/tasks.py 而 include_router 在 main.py，"
        "这是正确的跨文件注册模式，不要试图在 routers/tasks.py 内部重复 include_router。",

        "FastAPI 响应验证: 如果 response_model 为 Task (Pydantic model)，"
        "返回的对象会经过 Pydantic 验证和序列化。确保返回字段与模型定义一致。",
    ],
    "flask": [
        "Flask 路由: 使用 @app.route 装饰器，确保函数名不重复，路由路径以 '/' 开头。",
        "Flask 请求数据: 使用 request.json 或 request.get_json() 获取 JSON body。",
    ],
    "django": [
        "Django views: 确保在 urls.py 中注册了所有 view。",
        "Django ORM: 查询后检查 .exists() 或处理 DoesNotExist 异常。",
    ],
    "pytest": [
        "pytest 测试发现: 测试文件必须以 test_ 开头，测试函数必须以 test_ 开头。",
        "pytest 导入: 确保 from backend.main import app 能正确解析，"
        "需要 backend/__init__.py 和 backend/models/__init__.py 等包初始化文件。",
        "pytest 断言: assert response.json() == {'detail': 'Task not found'} 检查实际返回值。"
        "如果 FastAPI 返回 {'detail': 'Not Found'}，说明请求未到达路由层，检查 URL 格式。",
    ],
}


def _detect_framework_hints(code: str, error_message: str) -> str:
    code_lower = (code or "").lower()
    err_lower = (error_message or "").lower()
    hints = []

    for framework, tips in _FRAMEWORK_HINTS.items():
        if framework == "pytest":
            if "pytest" in err_lower or "assert" in err_lower or "test_" in code_lower:
                hints.extend(tips[:2])
            continue

        if framework == "fastapi" and (
            "fastapi" in code_lower
            or "httpexception" in code_lower
            or "testclient" in err_lower
            or "testclient" in code_lower
            or "fastapi" in err_lower
        ):
            hints.extend(tips)
            continue

        if framework in code_lower or framework in err_lower:
            hints.extend(tips)

    return "\n".join(f"- {h}" for h in hints)


def profile_prompt(code: str) -> str:
    return f"""
请对下面的 Python 代码进行性能分析：

【代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

请分析：
1. 时间复杂度（大 O 表示法）
2. 空间复杂度
3. 性能瓶颈在哪里
4. 如何优化（给出具体的优化建议）
5. 如果可能，提供优化后的代码示例

输出为结构化自然语言分析，不要生成代码。
"""


def doc_prompt(code: str) -> str:
    return f"""
请为下面的 Python 代码生成完整的文档：

【代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

请生成：
1. 模块级别的文档字符串说明
2. 每个函数的完整文档（参数、返回值、异常）
3. 类的文档（如果有类）
4. 使用示例代码（用 \\`\\`\\`python 代码块包裹）
5. 注意事项

输出必须是合法 Markdown 文档，不要包含多余解释性文字。
"""


def docstring_prompt(code: str) -> str:
    return f"""
请在下面这段 Python 代码中添加完整的文档字符串（docstring），保持代码功能不变。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

要求：
1. 为模块添加顶部的文档字符串（如果合适）
2. 为每个函数添加完整的文档字符串
3. 为每个类及其方法添加文档字符串
4. 输出添加了文档的完整代码（使用 \\`\\`\\`python 代码块）
5. 不要输出解释性自然语言。
"""


def optimize_prompt(code: str, exec_summary: str) -> str:
    """
    单文件优化版（兼容旧 refine_step 调用）
    """
    return f"""
下面是一段 Python 代码和它的执行结果，请你在保证语义不变的前提下进行优化。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

【执行结果】：
{exec_summary}

要求：
1. 在保证语义不变的前提下优化代码
2. 输出优化后的完整代码（使用 \\`\\`\\`python 代码块）
3. 【负向约束】代码块内禁止出现步骤标记或 CoT 文本
4. 不要输出解释性自然语言。
"""


# =========================================================
# ⭐ v2.8：多文件优化 + 自动生成测试文件（v3.0 主力）
# =========================================================

def optimize_prompt_v28(all_code_context: str, exec_summary: str) -> str:
    """
    v2.8/v3.0：多文件优化 + 自动生成测试文件（支持 FileOps Parser 3.0）
    """
    return f"""
你是一名专业的软件工程师，负责优化一个多文件 Python 项目，并自动生成测试。

下面是项目的全部文件内容（由 # FILE: 标记）：
============================================================
{all_code_context}
============================================================

下面是执行结果（stdout / stderr / error）：
============================================================
{exec_summary}
============================================================

你的任务：
1. 分析整个项目结构（不是单个文件）
2. 根据执行结果修复错误
3. 优化代码结构、命名、可读性、健壮性
4. 自动生成 pytest 测试文件（tests/test_xxx.py）
5. 测试文件必须覆盖：
   - 正常情况
   - 边界情况（空列表、单元素、重复元素）
   - 异常情况（非法输入、不支持的算法）
6. 如需修改多个文件，请使用 v3.0 协议输出：

# FILE: path/to/file.py
<文件内容>

# TEST: tests/test_xxx.py
<测试内容>

# DOC: docs/README.md
<文档内容>

7. 测试文件必须放在 tests/ 目录下（绝对不能放在 backend/ 源码目录）。
   使用 @pytest.fixture 创建 TestClient；测试覆盖至少：成功 + 异常（404/400）

8. 关于 # META: 和 # DEPENDS: 的严格要求（必须遵守）：
   - # META: 后面必须紧跟纯 JSON 对象，不能有任何其他文本
   - # DEPENDS: 声明依赖后必须生成真实的依赖文件，不能只声明 JSON：
     * Python 项目 → # FILE: requirements.txt（每行一个包名）
     * Node.js/React → # FILE: package.json（含 dependencies 和 devDependencies）
   - 示例格式：
     # META:
     {{"version": "1.0", "author": "AlphaPilot"}}

     # DEPENDS:
     {{"requirements": ["fastapi>=0.100.0", "pytest>=7.0"]}}

     # FILE: requirements.txt
     fastapi>=0.100.0
     uvicorn>=0.23.0
     pytest>=7.0
     httpx>=0.24.0

   - 如果不确定是否需要 META/DEPENDS，可以省略这两个指令

⚠️ 格式污染防护：# FILE: / # TEST: 代码块内禁止出现步骤标记（refine:、test:、write:、fix:、plan:）或 CoT 文本

只输出多文件协议内容，不要任何解释性文字。
"""