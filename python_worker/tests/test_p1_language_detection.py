# -*- coding: utf-8 -*-
# tests/test_p1_language_detection.py
# ---------------------------------------------------------
# P1: write_prompt 动态多语言示例检测测试（内联版，避开包导入问题）
# 函数逻辑与 write_step._detect_target_formats / prompts._build_* 完全一致
# ---------------------------------------------------------

import sys
import re
from pathlib import Path

# =========================================================
# 内联副本 — 与 write_step.py / prompts.py 逻辑完全一致
# =========================================================

_KNOWN_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".html", ".css",
    ".md", ".yaml", ".yml", ".toml", ".sql", ".sh", ".env",
}

_FORMAT_EXT_TO_SET = {ext.lstrip(".") for ext in _KNOWN_EXTENSIONS}


def _detect_target_formats(meta: dict, plan_text: str, user_request: str) -> list:
    formats = set()
    file_matches = re.findall(
        r'(?:EXPECTED_FILE|# FILE|路径)[:\s]*([a-zA-Z0-9_\-/.]+\.[a-z]{1,10})',
        plan_text, re.IGNORECASE)
    for path in file_matches:
        for ext in _KNOWN_EXTENSIONS:
            if path.endswith(ext):
                formats.add(ext.lstrip("."))
    if user_request:
        req_lower = user_request.lower()
        _keyword_map = {
            "react": "tsx", "vue": "ts", "angular": "ts",
            "typescript": "ts", "javascript": "js",
            "node.js": "js", "nodejs": "js",
            "fastapi": "py", "flask": "py", "django": "py", "python": "py",
            "frontend": "tsx", "前端": "tsx",
            "go": "go", "rust": "rs", "java": "java",
            "html": "html", "css": "css",
            "docker": "yaml", "ci/cd": "yaml", "github actions": "yaml",
        }
        for keyword, fmt in _keyword_map.items():
            if keyword in req_lower:
                formats.add(fmt)
    exec_profile = meta.get("execution_profile", {})
    target_format = exec_profile.get("target_format", "")
    if target_format and target_format in _FORMAT_EXT_TO_SET:
        formats.add(target_format)
    if not formats:
        return ["py"]
    return sorted(formats)


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
}


def _build_language_examples(target_formats: list) -> str:
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
                f"    {path2}")
    if not examples:
        examples.append(
            "  对于代码文件，例如：\n"
            f"    # FILE: src/module.{target_formats[0]}")
    return "【目标文件格式示例】：\n" + "\n\n".join(examples) + "\n"


def _build_cross_language_examples(target_formats: list) -> str:
    if not target_formats:
        target_formats = ["py"]
    sections = []
    if "py" in target_formats:
        sections.append(
            "示例 — Python 项目：\n"
            "# FILE: backend/main.py\n"
            "# FILE: backend/models/user.py\n"
            "# FILE: requirements.txt\n"
            "fastapi>=0.100.0\n"
            "uvicorn>=0.23.0")
    if "ts" in target_formats or "tsx" in target_formats:
        sections.append(
            "示例 — TypeScript/React 项目：\n"
            "# FILE: frontend/src/App.tsx\n"
            "# FILE: frontend/src/api/tasks.ts\n"
            "# FILE: package.json\n"
            '{\n  "dependencies": {\n    "react": "^18.0.0"\n  }\n}')
    if "js" in target_formats and "ts" not in target_formats and "tsx" not in target_formats:
        sections.append(
            "示例 — JavaScript 项目：\n"
            "# FILE: frontend/src/utils.js\n"
            "# FILE: frontend/src/api/client.js\n"
            "# FILE: package.json")
    config_only = all(f in ("json", "yaml", "yml", "toml", "env", "md") for f in target_formats)
    if config_only and not sections:
        sections.append(
            "示例 — 配置项目：\n"
            "# FILE: docker-compose.yml\n"
            "# FILE: .env.example\n"
            "# FILE: README.md")
    if not sections:
        sections.append("示例：\n# FILE: src/code.ext\n# FILE: config.ext")
    return "【常见任务示例】：\n" + "\n\n".join(sections)


def assert_contains(actual, *expected_substrings, label=""):
    missing = [s for s in expected_substrings if s not in actual]
    if missing:
        raise AssertionError(
            f"{label} 缺少: {missing}\n>>>实际输出:\n{actual[:500]}")

# =========================================================
# _detect_target_formats
# =========================================================


def test_python_only():
    plan = "EXPECTED_FILE: backend/main.py\nEXPECTED_FILE: backend/models/user.py"
    user = "帮我写一个 FastAPI 后端"
    assert _detect_target_formats({}, plan, user) == ["py"]


def test_typescript_react():
    plan = "EXPECTED_FILE: frontend/src/App.tsx\n文件路径：frontend/src/api/tasks.ts"
    user = "用 React 和 TypeScript 写一个前端"
    formats = _detect_target_formats({}, plan, user)
    assert "tsx" in formats
    assert "ts" in formats


def test_fullstack():
    plan = ("EXPECTED_FILE: backend/main.py\n"
            "EXPECTED_FILE: backend/models/task.py\n"
            "EXPECTED_FILE: frontend/src/App.tsx\n"
            "EXPECTED_FILE: frontend/src/api/tasks.ts")
    user = "需要同时修改后端（Python FastAPI）和前端（React TypeScript）"
    formats = _detect_target_formats({}, plan, user)
    assert "py" in formats
    assert "tsx" in formats
    assert "ts" in formats


def test_user_keyword_only():
    plan = "建议使用 React 前端 + FastAPI 后端架构"
    user = "用 React 和 FastAPI 创建全栈应用"
    formats = _detect_target_formats({}, plan, user)
    assert "tsx" in formats
    assert "py" in formats


def test_chinese_keyword():
    plan = "EXPECTED_FILE: App.tsx"
    user = "写一个前端页面"
    formats = _detect_target_formats({}, plan, user)
    assert "tsx" in formats


def test_execution_profile():
    formats = _detect_target_formats(
        {"execution_profile": {"target_format": "py"}},
        "生成代码", "")
    assert formats == ["py"]


def test_fallback_default():
    assert _detect_target_formats({}, "生成代码", "") == ["py"]


def test_deduplication():
    plan = ("# FILE: src/app.tsx\n# FILE: src/components/Header.tsx\n"
            "# FILE: src/components/Footer.tsx")
    user = "React TypeScript 前端"
    formats = _detect_target_formats({}, plan, user)
    assert formats.count("tsx") == 1

# =========================================================
# _build_language_examples
# =========================================================


def test_examples_python():
    result = _build_language_examples(["py"])
    assert_contains(result, "Python", "# FILE: backend/main.py",
                    "# FILE: backend/models/user.py", label="py example")


def test_examples_typescript():
    result = _build_language_examples(["ts", "tsx"])
    assert_contains(result, "TypeScript", "# FILE: frontend/src/api/tasks.ts",
                    "React TSX", "# FILE: frontend/src/App.tsx",
                    label="ts/tsx example")


def test_examples_fullstack():
    result = _build_language_examples(["py", "ts", "tsx", "json"])
    assert_contains(result, "Python", "# FILE: backend/main.py",
                    "TypeScript", "# FILE: frontend/src/api/tasks.ts",
                    "React TSX", "# FILE: frontend/src/App.tsx",
                    "JSON", "# FILE: package.json",
                    label="fullstack example")


def test_examples_empty():
    result = _build_language_examples([])
    assert_contains(result, "Python", label="empty fallback")


def test_examples_none():
    result = _build_language_examples(None)
    assert_contains(result, "Python", label="None fallback")

# =========================================================
# _build_cross_language_examples
# =========================================================


def test_cross_python():
    result = _build_cross_language_examples(["py"])
    assert_contains(result, "Python 项目", "requirements.txt",
                    "fastapi>=0.100.0", label="cross py")


def test_cross_react():
    result = _build_cross_language_examples(["tsx"])
    assert_contains(result, "TypeScript/React", "App.tsx",
                    "package.json", 'react', label="cross react")


def test_cross_fullstack():
    result = _build_cross_language_examples(["py", "tsx"])
    assert_contains(result, "Python 项目", "TypeScript/React 项目",
                    label="cross fullstack")


def test_no_py_bias():
    """["tsx"] 不含 Python 相关示例"""
    result = _build_cross_language_examples(["tsx"])
    assert "requirements.txt" not in result
    assert "fastapi" not in result

# =========================================================
# 集成测试：write_prompt 实际输出
# =========================================================


def test_write_prompt_fullstack():
    """模拟 write_step 中实际 write_prompt 调用流程"""
    from agents.qwen.step_executor.prompts import write_prompt

    plan = ("计划创建以下文件：\n"
            "EXPECTED_FILE: backend/models/task.py\n"
            "EXPECTED_FILE: backend/routers/tasks.py\n"
            "EXPECTED_FILE: frontend/src/api/tasks.ts\n"
            "EXPECTED_FILE: frontend/src/components/TaskList.tsx")
    user = "需求：为这个项目添加任务系统。后端 Python FastAPI，前端 React TypeScript。"

    formats = _detect_target_formats({}, plan, user)
    prompt = write_prompt(plan, user, formats)

    # 验证不存在 Python 中心偏见
    # 关键：不能只有 .py 的示例
    assert_contains(prompt,
                    "# FILE: frontend/src/App.tsx",      # React 示例
                    "# FILE: frontend/src/api/tasks.ts",  # TypeScript 示例
                    "# FILE: backend/main.py",            # Python 示例（仍然有）
                    "TypeScript/React 项目",              # 跨语言示例
                    "Python 项目",                        # Python 示例
                    label="fullstack prompt")

    # 验证路径扩展名提示（去掉了硬编码 .py）
    assert "path/to/file.ext" in prompt, "应该有通用扩展名提示"
    assert "# FILE: path/to/file.py" not in prompt or "file.ext" in prompt, \
        "不应该只有 .py 示例路径"


def test_write_prompt_python_only():
    """纯 Python 项目 — 保持向后兼容"""
    from agents.qwen.step_executor.prompts import write_prompt

    plan = "EXPECTED_FILE: main.py"
    user = "写一个 Python 脚本"
    prompt = write_prompt(plan, user, ["py"])

    assert_contains(prompt,
                    "# FILE: backend/main.py",
                    "Python 项目",
                    "requirements.txt",
                    label="python-only prompt")


# =========================================================
# Runner
# =========================================================

if __name__ == "__main__":
    tests = [
        test_python_only,
        test_typescript_react,
        test_fullstack,
        test_user_keyword_only,
        test_chinese_keyword,
        test_execution_profile,
        test_fallback_default,
        test_deduplication,
        test_examples_python,
        test_examples_typescript,
        test_examples_fullstack,
        test_examples_empty,
        test_examples_none,
        test_cross_python,
        test_cross_react,
        test_cross_fullstack,
        test_no_py_bias,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1

    print(f"\n{'─' * 35}")
    print(f"  通过: {passed}/{len(tests)}")
    print(f"  失败: {failed}/{len(tests)}")
    print(f"{'─' * 35}")
    sys.exit(0 if failed == 0 else 1)