# -*- coding: utf-8 -*-
# step_executor/verification_governor.py
# ---------------------------------------------------------
# v3.5: Intelligent Verification Governance — Step 1 Shadow Mode
#
# 职责：
#   - 分析 final_file_ops 中的文件变更，输出结构化 impact_profile
#   - 区分 scope（影响范围）与 risk_level（风险等级）
#   - Shadow Mode：不改变任何现有测试执行行为，仅观察和记录
#
# 约束：
#   - 零 LLM 依赖（纯确定性分析：AST + 规则 + 文件系统）
#   - 不产生执行副作用
#   - 不拥有独立任务状态机
#   - 降级路径：PASS_THROUGH（失败不阻断执行链）
#
# G10.2 能力注册：
#   能力名称：verification_governance
#   输入：context（含 final_file_ops, workspace_path）
#   输出：impact_profile
# ---------------------------------------------------------

import ast
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ================================================================
#  v3.5: VerificationGovernor — 智能验证治理器
# ================================================================

class VerificationGovernor:
    """Step 1 Shadow Mode: 分析变更影响，不改变测试行为。"""

    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self._start_time = time.monotonic()

        workspace_info = context.get("workspace_info") or {}
        self.workspace_path = workspace_info.get("path") or ""

    # ────────────────────────────────────────────────────────
    #  公共入口
    # ────────────────────────────────────────────────────────

    def analyze_impact(self) -> Dict[str, Any]:
        """核心入口：分析 final_file_ops 变更，返回 impact_profile。

        Shadow Mode 保证：任何异常都不会向上传播，返回降级 profile。
        """
        try:
            changes = self._collect_file_changes()
            if not changes:
                return self._no_changes_profile()

            categories = self._classify_file_types(changes)
            signals = self._analyze_diff_signals(changes)
            symbols = self._detect_changed_symbols(changes)
            blast = self._estimate_blast_radius(changes, symbols)

            profile = self._build_initial_profile(
                changes, categories, signals, symbols, blast,
            )
            risk_level, confidence = self._calculate_risk(profile)
            profile["risk_level"] = risk_level
            profile["confidence"] = round(confidence, 2)
            profile["duration_ms"] = round(
                (time.monotonic() - self._start_time) * 1000,
            )

            # v3.5: 写入 context.meta 审计记录（Shadow Mode）
            self.context.setdefault("meta", {})["verification_governance"] = {
                "impact_profile": profile,
                "governor_version": "1.0.0-shadow",
                "shadow_mode": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            return profile

        except Exception as exc:
            return {
                "version": "1.0",
                "mode": "shadow",
                "scope": "unknown",
                "risk_level": "unknown",
                "analysis_failed": True,
                "error": str(exc),
                "duration_ms": round(
                    (time.monotonic() - self._start_time) * 1000,
                ),
            }

    # ────────────────────────────────────────────────────────
    #  1. 收集文件变更
    # ────────────────────────────────────────────────────────

    def _collect_file_changes(self) -> List[Dict[str, Any]]:
        """从 final_file_ops 收集所有 create / modify / delete 操作。

        排除 _internal 标记的操作（如自动生成的 __init__.py）。
        对 MODIFY 操作，尝试从磁盘读取原始内容以便 diff 分析。
        """
        file_ops = self.context.get("final_file_ops") or []
        changes: List[Dict[str, Any]] = []

        for op in file_ops:
            if op.get("_internal"):
                continue

            op_type = op.get("op", "")
            if op_type not in ("create", "modify", "delete"):
                continue

            path_str = op.get("path", "")
            if not path_str:
                continue

            change: Dict[str, Any] = {
                "path": path_str,
                "op": op_type,
                "new_content": op.get("content", ""),
                "old_content": "",
                "extension": Path(path_str).suffix.lower(),
                "basename": Path(path_str).name,
            }

            if op_type == "modify" and self.workspace_path:
                old_path = Path(self.workspace_path) / path_str.lstrip("/\\")
                try:
                    if old_path.is_file():
                        change["old_content"] = old_path.read_text(
                            encoding="utf-8", errors="replace",
                        )
                except Exception:
                    pass

            # 回退：磁盘读取失败时，使用 file_op 中携带的 old_content
            if not change["old_content"] and op.get("old_content"):
                change["old_content"] = op.get("old_content")

            changes.append(change)

        return changes

    # ────────────────────────────────────────────────────────
    #  2. 文件类型分类
    # ────────────────────────────────────────────────────────

    @staticmethod
    def _classify_file_types(
        changes: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """按扩展名分类计数，不假设项目目录结构。

        返回：{"python": N, "markdown": N, "config": N, "test": N, ...}
        """
        counts: Dict[str, int] = {}
        for c in changes:
            ext = c.get("extension", "")
            base = c.get("basename", "").lower()

            if ext == ".py":
                if base.startswith("test_") or base.endswith("_test.py"):
                    counts["test"] = counts.get("test", 0) + 1
                counts["python"] = counts.get("python", 0) + 1
            elif ext in (".md", ".mdx"):
                counts["markdown"] = counts.get("markdown", 0) + 1
            elif ext in (".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env"):
                counts["config"] = counts.get("config", 0) + 1
            elif ext in (".sql", ".sqlite", ".db"):
                counts["sql"] = counts.get("sql", 0) + 1
            elif ext in (".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".vue"):
                counts["frontend"] = counts.get("frontend", 0) + 1
            elif ext in (".go", ".rs", ".java", ".c", ".cpp", ".h"):
                counts["compiled"] = counts.get("compiled", 0) + 1
            elif not ext:
                counts["no_extension"] = counts.get("no_extension", 0) + 1
            else:
                counts["other"] = counts.get("other", 0) + 1

        return counts

    # ────────────────────────────────────────────────────────
    #  3. 变更信号分析（diff_signals）
    # ────────────────────────────────────────────────────────

    def _analyze_diff_signals(
        self, changes: List[Dict[str, Any]],
    ) -> List[str]:
        """从文件内容和类型中提取变化信号。

        对 Python 文件使用 AST 判断变更性质：
        - docstring_only: 只修改了 docstring 或注释
        - function_signature: 修改了函数/方法签名
        - class_definition: 修改了类定义
        - import_change: 修改了 import 语句
        - decorator_change: 修改了装饰器（路由、权限等）
        - api_surface_change: 对外接口发生变化
        - schema_change: 数据模型变更
        """
        signals: List[str] = []
        code_changes = 0
        non_code_changes = 0
        has_api = False
        has_schema = False

        for c in changes:
            ext = c.get("extension", "")
            path_str = c.get("path", "").lower()
            old = c.get("old_content", "")
            new = c.get("new_content", "")

            if ext == ".py":
                py_signals = self._analyze_python_diff(old, new, path_str)
                for sig in py_signals:
                    if sig not in signals:
                        signals.append(sig)

                if py_signals:
                    code_changes += 1
                    if "api_surface_change" in py_signals:
                        has_api = True
                    if "schema_change" in py_signals:
                        has_schema = True
                else:
                    non_code_changes += 1

            elif ext in (".md", ".mdx"):
                non_code_changes += 1
                if "markdown_change" not in signals:
                    signals.append("markdown_change")

            elif ext in (".yml", ".yaml", ".json", ".toml"):
                code_changes += 1
                if "config_change" not in signals:
                    signals.append("config_change")

            elif ext in (".sql", ".sqlite"):
                code_changes += 1
                has_schema = True
                if "schema_change" not in signals:
                    signals.append("schema_change")

        if code_changes == 0 and non_code_changes > 0:
            if "cosmetic_only" not in signals:
                signals.append("cosmetic_only")
        if has_api and "api_surface_change" not in signals:
            signals.append("api_surface_change")
        if has_schema and "schema_change" not in signals:
            signals.append("schema_change")

        return signals

    @staticmethod
    def _analyze_python_diff(
        old: str, new: str, path_str: str,
    ) -> List[str]:
        """对比两个 Python 源码版本的 AST，输出变更信号。

        能识别：
        - 纯 docstring / 注释修改（cosmetic）
        - 函数/类签名变化
        - 导入变化
        - 装饰器变化（含 FastAPI 路由装饰器）
        - Schema / Pydantic 模型变更
        """
        signals: List[str] = []

        if not new:
            return signals

        try:
            new_tree = ast.parse(new)
        except SyntaxError:
            signals.append("syntax_error")
            return signals

        old_tree = None
        if old:
            try:
                old_tree = ast.parse(old)
            except SyntaxError:
                pass

        # 提取顶层符号
        new_funcs = _extract_function_names(new_tree)
        new_classes = _extract_class_names(new_tree)
        new_imports = _extract_import_names(new_tree)
        new_decorators = _extract_decorator_names(new_tree)

        if old_tree:
            old_funcs = _extract_function_names(old_tree)
            old_classes = _extract_class_names(old_tree)
            old_imports = _extract_import_names(old_tree)
            old_decorators = _extract_decorator_names(old_tree)

            # 比较函数签名
            func_added = new_funcs - old_funcs
            func_removed = old_funcs - new_funcs
            if func_added or func_removed:
                if _is_docstring_only_change(old_tree, new_tree, old_funcs, new_funcs):
                    signals.append("docstring_only")
                else:
                    signals.append("function_signature")
            elif new_funcs == old_funcs and new_funcs:
                # 函数名无变化，但函数体可能变了——
                # 通过 docstring 剥离后的 AST 对比判定
                if _is_docstring_only_change(old_tree, new_tree, old_funcs, new_funcs):
                    signals.append("docstring_only")
                else:
                    signals.append("function_signature")

            # 比较类定义
            class_added = new_classes - old_classes
            class_removed = old_classes - new_classes
            if class_added or class_removed:
                if not _is_docstring_only_change(old_tree, new_tree, old_classes,
                                                 new_classes):
                    signals.append("class_definition")

            # 比较导入
            if new_imports != old_imports:
                signals.append("import_change")

            # 比较装饰器
            if new_decorators != old_decorators:
                signals.append("decorator_change")
                # 检查是否是 FastAPI 路由装饰器变更
                route_decos = {"get", "post", "put", "delete", "patch", "router",
                               "app", "api_route", "websocket"}
                new_routes = new_decorators & route_decos
                old_routes = old_decorators & route_decos
                if new_routes != old_routes or func_added or func_removed:
                    signals.append("api_surface_change")
        else:
            # 全新文件
            if new_funcs:
                signals.append("function_signature")
            if new_classes:
                signals.append("class_definition")

            # v3.5: 全新文件也要检测 API surface（路由装饰器）
            if new_decorators:
                route_decos = {"get", "post", "put", "delete", "patch", "router",
                               "app", "api_route", "websocket"}
                if new_decorators & route_decos:
                    signals.append("api_surface_change")

        # 检查 Pydantic / SQLAlchemy 模型
        _is_schema = _check_schema_file(new_tree, path_str)
        if _is_schema:
            signals.append("schema_change")

        # 如果没有实质性代码变更，检查是否是纯 cosmetic
        if not signals:
            signals.append("cosmetic_only")

        return signals

    # ────────────────────────────────────────────────────────
    #  4. 符号变化检测
    # ────────────────────────────────────────────────────────

    def _detect_changed_symbols(
        self, changes: List[Dict[str, Any]],
    ) -> List[str]:
        """检测所有变化的函数/类/变量符号名。

        返回：["create_order", "OrderService", "get_db"] 等
        """
        symbols: List[str] = []
        for c in changes:
            if c.get("extension") != ".py":
                continue
            old = c.get("old_content", "")
            new = c.get("new_content", "")
            changed = _compare_ast_symbols(old, new)
            for sym in changed:
                if sym not in symbols:
                    symbols.append(sym)
        return symbols

    # ────────────────────────────────────────────────────────
    #  5. Blast Radius 估算
    # ────────────────────────────────────────────────────────

    def _estimate_blast_radius(
        self,
        changes: List[Dict[str, Any]],
        symbols: List[str],
    ) -> List[str]:
        """基于模块导入关系估算影响范围。

        扫描项目所有 .py 文件，查找导入了变更模块的文件。
        返回受影响的文件/模块路径列表。
        """
        if not self.workspace_path:
            return []

        changed_modules: Set[str] = set()
        for c in changes:
            if c.get("extension") != ".py":
                continue
            p = c.get("path", "")
            mod = _path_to_module(p)
            if mod:
                changed_modules.add(mod)

        if not changed_modules:
            return []

        affected: List[str] = []
        ws = Path(self.workspace_path)
        try:
            for py_file in ws.rglob("*.py"):
                # 跳过 .venv / node_modules / __pycache__
                parts = py_file.parts
                if any(skip in parts for skip in
                       (".venv", "venv", "node_modules", "__pycache__",
                        ".git", ".pytest_cache")):
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                tree = _safe_parse(content)
                if tree is None:
                    continue

                imports = _extract_import_modules(tree)
                if imports & changed_modules:
                    rel = str(py_file.relative_to(ws)).replace("\\", "/")
                    affected.append(rel)
        except Exception:
            pass

        return affected

    # ────────────────────────────────────────────────────────
    #  6. 风险计算
    # ────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_risk(profile: Dict[str, Any]) -> Tuple[str, float]:
        """综合所有信号计算 risk_level 和 confidence。

        决策规则（确定性，不调用 LLM）：
        - syntax_error → high (0.95)
        - schema_change → high (0.85)
        - api_surface_change → high (0.85)
        - schema_change + api_surface_change → high (0.90)
        - function_signature + blast_radius >= 3 → high (0.80)
        - function_signature → medium (0.70)
        - cosmetic_only → low (0.90)
        - 无代码变化 → low (0.95)
        - 默认 → medium (0.60)
        """
        signals = profile.get("signals", [])
        blast = profile.get("blast_radius", [])
        scope = profile.get("scope", "module")

        has_schema = "schema_change" in signals
        has_api = "api_surface_change" in signals
        has_func = "function_signature" in signals
        has_class = "class_definition" in signals
        has_decorator = "decorator_change" in signals
        cosmetic = "cosmetic_only" in signals
        syntax_err = "syntax_error" in signals
        has_code = has_func or has_class or has_decorator or has_schema or has_api

        if syntax_err:
            return "high", 0.95

        if has_schema and has_api:
            return "high", 0.90

        if has_schema:
            return "high", 0.85

        if has_api:
            return "high", 0.85
        if scope == "wide":
            return "high", 0.80

        if has_func and len(blast) >= 3:
            return "high", 0.80

        if has_func or has_class or has_decorator:
            return "medium", 0.70

        if cosmetic:
            return "low", 0.90

        if not has_code:
            return "low", 0.95

        return "medium", 0.60

    # ────────────────────────────────────────────────────────
    #  7. 构建 Impact Profile
    # ────────────────────────────────────────────────────────

    def _build_initial_profile(
        self,
        changes: List[Dict[str, Any]],
        categories: Dict[str, int],
        signals: List[str],
        symbols: List[str],
        blast: List[str],
    ) -> Dict[str, Any]:
        """组装 impact_profile 的骨架（不含 risk_level 和 confidence）。"""
        scope = self._compute_scope(categories, signals, blast)

        return {
            "version": "1.0",
            "mode": "shadow",
            "scope": scope,
            "risk_level": "unset",
            "changed_files": [
                {
                    "path": c["path"],
                    "op": c["op"],
                    "category": (
                        "python" if c["extension"] == ".py"
                        else "markdown" if c["extension"] in (".md", ".mdx")
                        else "config" if c["extension"] in (
                            ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env")
                        else "other"
                    ),
                    "has_old_content": bool(c.get("old_content")),
                }
                for c in changes
            ],
            "file_categories": categories,
            "changed_symbols": symbols,
            "blast_radius": blast,
            "signals": signals,
            "confidence": 0.0,
            "analysis_evidence": self._build_evidence(changes, signals, symbols, blast),
        }

    @staticmethod
    def _compute_scope(
        categories: Dict[str, int],
        signals: List[str],
        blast: List[str],
    ) -> str:
        """判定改动范围级别。"""
        py_count = categories.get("python", 0)
        test_count = categories.get("test", 0)

        non_test_py = py_count - test_count

        if non_test_py >= 5 or len(blast) >= 5:
            return "wide"
        if non_test_py >= 2:
            return "multi_module"
        if "cosmetic_only" in signals or "docstring_only" in signals \
        or "markdown_change" in signals:
            if not any(
                s in signals for s in ("function_signature", "class_definition",
                                       "api_surface_change", "schema_change",
                                       "import_change", "decorator_change",
                                       "config_change")
            ):
                return "cosmetic"
        if non_test_py == 0 and py_count > 0:
            return "test_only"
        return "module"

    @staticmethod
    def _build_evidence(
        changes: List[Dict[str, Any]],
        signals: List[str],
        symbols: List[str],
        blast: List[str],
    ) -> List[str]:
        """构建人类可读的分析证据链。"""
        evidence: List[str] = []
        py_changes = [c for c in changes if c.get("extension") == ".py"]
        non_py = [c for c in changes if c.get("extension") != ".py"]

        if py_changes:
            evidence.append(
                f"{len(py_changes)} Python file(s) changed: "
                + ", ".join(c["basename"] for c in py_changes),
            )
        if non_py:
            evidence.append(
                f"{len(non_py)} non-Python file(s) changed: "
                + ", ".join(c["basename"] for c in non_py),
            )
        if signals:
            evidence.append(f"Signals: {', '.join(signals)}")
        if symbols:
            evidence.append(f"Changed symbols: {', '.join(symbols[:10])}")
        if blast:
            evidence.append(
                f"Blast radius ({len(blast)} modules): "
                + ", ".join(blast[:5]),
            )
        if not evidence:
            evidence.append("No identifiable changes detected.")
        return evidence

    @staticmethod
    def _no_changes_profile() -> Dict[str, Any]:
        return {
            "version": "1.0",
            "mode": "shadow",
            "scope": "none",
            "risk_level": "low",
            "confidence": 1.0,
            "changed_files": [],
            "file_categories": {},
            "changed_symbols": [],
            "blast_radius": [],
            "signals": ["no_changes"],
            "analysis_evidence": ["No final_file_ops or empty operations list."],
        }


# ================================================================
#  AST 工具函数（模块级，无状态）
# ================================================================

def _safe_parse(source: str) -> Optional[ast.AST]:
    """安全解析 Python 源码，失败返回 None。"""
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _extract_function_names(tree: ast.AST) -> Set[str]:
    """提取顶层函数名。"""
    names: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def _extract_class_names(tree: ast.AST) -> Set[str]:
    """提取顶层类名。"""
    names: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def _extract_import_names(tree: ast.AST) -> Set[str]:
    """提取导入的模块/符号名。"""
    names: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            for alias in node.names:
                names.add(alias.name)
    return names


def _extract_decorator_names(tree: ast.AST) -> Set[str]:
    """提取装饰器名称（用于检测路由/权限装饰器变更）。"""
    names: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        decorators = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            decorators = node.decorator_list

        for deco in decorators:
            if isinstance(deco, ast.Name):
                names.add(deco.id)
            elif isinstance(deco, ast.Attribute):
                names.add(deco.attr)
            elif isinstance(deco, ast.Call):
                if isinstance(deco.func, ast.Name):
                    names.add(deco.func.id)
                elif isinstance(deco.func, ast.Attribute):
                    names.add(deco.func.attr)
    return names


def _extract_import_modules(tree: ast.AST) -> Set[str]:
    """提取所有 import 的模块名（用于 blast radius 分析）。"""
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def _compare_ast_symbols(old: str, new: str) -> Set[str]:
    """比较两个 Python 源码版本的顶层符号变化。

    返回发生变化的符号名集合。
    """
    if not old or not new:
        old_funcs: Set[str] = set()
        old_classes: Set[str] = set()
    else:
        old_tree = _safe_parse(old)
        if old_tree:
            old_funcs = _extract_function_names(old_tree)
            old_classes = _extract_class_names(old_tree)
        else:
            old_funcs = set()
            old_classes = set()

    new_tree = _safe_parse(new)
    if not new_tree:
        return set()

    new_funcs = _extract_function_names(new_tree)
    new_classes = _extract_class_names(new_tree)

    changed: Set[str] = set()
    added_funcs = new_funcs - old_funcs
    removed_funcs = old_funcs - new_funcs
    changed.update(added_funcs)
    changed.update(removed_funcs)

    added_classes = new_classes - old_classes
    removed_classes = old_classes - new_classes
    changed.update(added_classes)
    changed.update(removed_classes)

    return changed


def _is_docstring_only_change(
    old_tree: ast.AST,
    new_tree: ast.AST,
    old_names: Set[str],
    new_names: Set[str],
) -> bool:
    """判断是否仅修改了 docstring / 注释，未改动任何代码结构。

    判断逻辑：
    1. 顶层符号名集合完全一致
    2. 移除所有 docstring 和注释后，AST 结构一致
    """
    if old_names != new_names:
        return False

    try:
        old_stripped = _strip_docstrings(old_tree)
        new_stripped = _strip_docstrings(new_tree)
        return ast.dump(old_stripped, annotate_fields=False) == ast.dump(
            new_stripped, annotate_fields=False,
        )
    except Exception:
        return False


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """递归移除 AST 中所有节点的 docstring，返回新树。"""

    class DocstringStripper(ast.NodeTransformer):
        def visit_FunctionDef(self, node):  # pragma: no cover (self 参数是接口约定)
            node = self.generic_visit(node)
            if (
                isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
            return node

        def visit_AsyncFunctionDef(self, node):
            node = self.generic_visit(node)
            if (
                isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
            return node

        def visit_ClassDef(self, node):
            node = self.generic_visit(node)
            if (
                isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
            return node

        def visit_Module(self, node):
            node = self.generic_visit(node)
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
            return node

    return DocstringStripper().visit(tree)


def _check_schema_file(tree: ast.AST, path_str: str) -> bool:
    """检查是否是数据模型/Schema 文件。

    判断依据：
    - 文件名含 model/schema/entity
    - 或 AST 中有 Pydantic BaseModel 继承
    - 或 AST 中有 SQLAlchemy declarative_base
    """
    lower = path_str.lower()
    if any(kw in lower for kw in ("model", "schema", "entity", "types")):
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in (
                    "BaseModel", "Base", "SQLModel", "DeclarativeBase",
                ):
                    return True
                if isinstance(base, ast.Attribute) and base.attr in (
                    "BaseModel", "Base",
                ):
                    return True

    return False


def _path_to_module(path_str: str) -> str:
    """将文件路径转换为 Python 模块名。

    例：backend/routers/orders.py → backend.routers.orders
    """
    p = path_str.replace("\\", "/").rstrip("/")
    if p.endswith(".py"):
        p = p[:-3]
    # 跳过 __init__
    parts = [x for x in p.split("/") if x]
    if not parts:
        return ""
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return ""
    return ".".join(parts)