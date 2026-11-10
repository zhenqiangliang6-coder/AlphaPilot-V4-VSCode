# -*- coding: utf-8 -*-
# python_worker/language_adapter.py — 语言工具链适配层
# ---------------------------------------------------------
# 架构定位（统一 CodingWorker 架构）
#
# LanguageAdapter 不调 LLM，不写代码，不做决策。
# 它只做确定性环境操作：依赖安装、编译、测试、Lint。
#
# 三层职责边界：
#   Python Worker（大脑）  → LLM 写代码 + 决策 + 编排
#   LanguageAdapter（适配器）→ 编译/测试/依赖，确定性工具链
#   Orchestrator（编排器）  → DAG 规划 + 统一执行 + 结果聚合
#
# 安全约束：
#   - 零 LLM 调用
#   - 所有子进程调用必须经过 command_executor.CommandExecutor
#   - CommandExecutor 提供白名单、工作区边界、环境隔离、审计
#   - 工具链不存在时优雅降级（不抛异常，返回 CommandResult）
# ---------------------------------------------------------

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Dict

from command_executor import CommandResult, get_executor


# =========================================================
# 1. 抽象基类
# =========================================================

class LanguageAdapter(ABC):
    language: str = "unknown"

    INSTALL_TIMEOUT: int = 300
    COMPILE_TIMEOUT: int = 300
    TEST_TIMEOUT: int = 600
    LINT_TIMEOUT: int = 120

    def run_command(
        self,
        cmd: List[str],
        cwd: str,
        timeout: int = 120,
    ) -> CommandResult:
        """执行命令 — 统一经过 CommandExecutor 治理。

        不再直接 subprocess.run()。
        所有调用经过白名单、工作区边界、环境隔离、审计日志。
        """
        executor = get_executor()
        return executor.run(cmd, workspace=cwd, timeout=timeout)

    @abstractmethod
    def detect(self, workspace_path: str) -> bool:
        """检测工作区是否属于此语言。"""

    def install_dependencies(self, workspace_path: str) -> CommandResult:
        """安装项目依赖。"""
        return CommandResult(error=f"{self.language}: install not implemented")

    def compile(self, workspace_path: str) -> CommandResult:
        """编译/类型检查。解释型语言默认跳过。"""
        return CommandResult(success=True, command="(skip — interpreted)")

    def run_tests(self, workspace_path: str) -> CommandResult:
        """运行测试套件。"""
        return CommandResult(error=f"{self.language}: test not implemented")

    def lint(self, workspace_path: str) -> Optional[CommandResult]:
        """运行 Lint（可选）。默认跳过。"""
        return None


# =========================================================
# 2. Python 适配器
# =========================================================

class PythonAdapter(LanguageAdapter):
    language = "python"

    def detect(self, workspace_path: str) -> bool:
        return os.path.isfile(os.path.join(workspace_path, "requirements.txt")) or \
            any(f.endswith(".py") for f in os.listdir(workspace_path) if os.path.isfile(os.path.join(workspace_path, f)))

    def install_dependencies(self, workspace_path: str) -> CommandResult:
        req = os.path.join(workspace_path, "requirements.txt")
        if not os.path.isfile(req):
            return CommandResult(success=True, command="pip install (no requirements.txt)")

        return self.run_command(
            ["pip", "install", "-r", "requirements.txt"],
            cwd=workspace_path,
            timeout=self.INSTALL_TIMEOUT,
        )

    def run_tests(self, workspace_path: str) -> CommandResult:
        cmd = ["pytest", "-v", "--tb=short", "--timeout=120"]
        return self._parse_pytest_result(
            self.run_command(cmd, cwd=workspace_path, timeout=self.TEST_TIMEOUT),
        )

    def _parse_pytest_result(self, cr: CommandResult) -> CommandResult:
        """从 pytest 输出解析测试计数。"""
        output = cr.stdout + cr.stderr
        import re
        m = re.search(r"(\d+)\s+passed", output)
        if m:
            cr.passed_tests = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", output)
        if m:
            cr.failed_tests = int(m.group(1))
        cr.total_tests = cr.passed_tests + cr.failed_tests
        return cr

    def lint(self, workspace_path: str) -> Optional[CommandResult]:
        return self.run_command(
            ["flake8", "--max-line-length=120", "."],
            cwd=workspace_path,
            timeout=self.LINT_TIMEOUT,
        )


# =========================================================
# 3. JavaScript 适配器
# =========================================================

class JavaScriptAdapter(LanguageAdapter):
    language = "javascript"

    def detect(self, workspace_path: str) -> bool:
        return os.path.isfile(os.path.join(workspace_path, "package.json"))

    def _detect_package_manager(self, workspace_path: str) -> str:
        if os.path.isfile(os.path.join(workspace_path, "package-lock.json")):
            return "npm"
        if os.path.isfile(os.path.join(workspace_path, "yarn.lock")):
            return "yarn"
        if os.path.isfile(os.path.join(workspace_path, "pnpm-lock.yaml")):
            return "pnpm"
        return "npm"

    def install_dependencies(self, workspace_path: str) -> CommandResult:
        if not os.path.isfile(os.path.join(workspace_path, "package.json")):
            return CommandResult(success=True, command="npm install (no package.json)")

        pm = self._detect_package_manager(workspace_path)
        return self.run_command(
            [pm, "install", "--no-audit", "--no-fund"],
            cwd=workspace_path,
            timeout=self.INSTALL_TIMEOUT,
        )

    def run_tests(self, workspace_path: str) -> CommandResult:
        test_cmd = self._resolve_test_command(workspace_path)
        return self._parse_jest_result(
            self.run_command(test_cmd, cwd=workspace_path, timeout=self.TEST_TIMEOUT),
        )

    def _resolve_test_command(self, workspace_path: str) -> List[str]:
        if os.path.isdir(os.path.join(workspace_path, "node_modules", ".bin")):
            if os.path.isfile(os.path.join(workspace_path, "node_modules", ".bin", "jest")):
                return ["npx", "jest", "--verbose", "--forceExit"]
            if os.path.isfile(os.path.join(workspace_path, "node_modules", ".bin", "mocha")):
                return ["npx", "mocha", "--reporter", "spec"]
        return ["npx", "jest", "--verbose", "--forceExit", "--passWithNoTests"]

    def _parse_jest_result(self, cr: CommandResult) -> CommandResult:
        output = cr.stdout + cr.stderr
        import re
        m = re.search(r"Tests:\s+(\d+)\s+passed,\s+(\d+)\s+total", output) or \
            re.search(r"(\d+)\s+passing", output)
        if m:
            cr.passed_tests = int(m.group(1))
        m = re.search(r"Tests:\s+\d+\s+failed,\s+(\d+)\s+total", output) or \
            re.search(r"(\d+)\s+failing", output)
        if m and "Tests:" not in (m.group(0) if hasattr(m, 'group') else ""):
            cr.failed_tests = int(m.group(1))
        m = re.search(r"Tests:\s+(\d+)\s+total", output)
        if m:
            cr.total_tests = int(m.group(1))
        return cr

    def lint(self, workspace_path: str) -> Optional[CommandResult]:
        return self.run_command(
            ["npx", "eslint", ".", "--ext", ".js,.jsx,.mjs"],
            cwd=workspace_path,
            timeout=self.LINT_TIMEOUT,
        )


# =========================================================
# 4. TypeScript 适配器
# =========================================================

class TypeScriptAdapter(JavaScriptAdapter):
    language = "typescript"

    def compile(self, workspace_path: str) -> CommandResult:
        tsconfig = os.path.join(workspace_path, "tsconfig.json")
        cmd = ["npx", "tsc", "--noEmit"]
        if not os.path.isfile(tsconfig):
            cmd = ["npx", "tsc", "--noEmit", "--skipLibCheck",
                   "--target", "ES2020", "--module", "commonjs",
                   "--esModuleInterop", "--strict"]
        return self.run_command(cmd, cwd=workspace_path, timeout=self.COMPILE_TIMEOUT)


# =========================================================
# 5. Java 适配器
# =========================================================

class JavaAdapter(LanguageAdapter):
    language = "java"

    def detect(self, workspace_path: str) -> bool:
        return os.path.isfile(os.path.join(workspace_path, "pom.xml")) or \
            os.path.isfile(os.path.join(workspace_path, "build.gradle")) or \
            os.path.isfile(os.path.join(workspace_path, "build.gradle.kts"))

    def _detect_build_system(self, workspace_path: str) -> str:
        if os.path.isfile(os.path.join(workspace_path, "pom.xml")):
            return "maven"
        if os.path.isfile(os.path.join(workspace_path, "build.gradle.kts")):
            return "gradle_kts"
        if os.path.isfile(os.path.join(workspace_path, "build.gradle")):
            return "gradle"
        return "unknown"

    def install_dependencies(self, workspace_path: str) -> CommandResult:
        bs = self._detect_build_system(workspace_path)
        if bs == "maven":
            return self.run_command(
                ["mvn", "dependency:resolve", "-q"],
                cwd=workspace_path,
                timeout=self.INSTALL_TIMEOUT,
            )
        elif bs in ("gradle", "gradle_kts"):
            return self.run_command(
                ["gradle", "dependencies", "-q"],
                cwd=workspace_path,
                timeout=self.INSTALL_TIMEOUT,
            )
        else:
            return CommandResult(error="java: no build system detected")

    def compile(self, workspace_path: str) -> CommandResult:
        bs = self._detect_build_system(workspace_path)
        if bs == "maven":
            return self.run_command(
                ["mvn", "compile", "-q"],
                cwd=workspace_path,
                timeout=self.COMPILE_TIMEOUT,
            )
        elif bs in ("gradle", "gradle_kts"):
            return self.run_command(
                ["gradle", "compileJava", "-q"],
                cwd=workspace_path,
                timeout=self.COMPILE_TIMEOUT,
            )
        else:
            return CommandResult(error="java: no build system for compile")

    def run_tests(self, workspace_path: str) -> CommandResult:
        bs = self._detect_build_system(workspace_path)
        if bs == "maven":
            return self._parse_maven_test(
                self.run_command(
                    ["mvn", "test"],
                    cwd=workspace_path,
                    timeout=self.TEST_TIMEOUT,
                ),
            )
        elif bs in ("gradle", "gradle_kts"):
            return self._parse_gradle_test(
                self.run_command(
                    ["gradle", "test"],
                    cwd=workspace_path,
                    timeout=self.TEST_TIMEOUT,
                ),
            )
        else:
            return CommandResult(error="java: no build system for test")

    def _parse_maven_test(self, cr: CommandResult) -> CommandResult:
        output = cr.stdout + cr.stderr
        import re
        m = re.search(r"Tests run:\s*(\d+).*?Failures:\s*(\d+).*?Errors:\s*(\d+).*?Skipped:\s*(\d+)", output)
        if m:
            cr.total_tests = int(m.group(1))
            cr.failed_tests = int(m.group(2)) + int(m.group(3))
            cr.skipped_tests = int(m.group(4))
            cr.passed_tests = cr.total_tests - cr.failed_tests - cr.skipped_tests
        return cr

    def _parse_gradle_test(self, cr: CommandResult) -> CommandResult:
        output = cr.stdout + cr.stderr
        import re
        m = re.search(r"(\d+)\s+tests?\s+completed", output)
        if m:
            cr.total_tests = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", output)
        if m:
            cr.failed_tests = int(m.group(1))
        cr.passed_tests = cr.total_tests - cr.failed_tests
        return cr

    def lint(self, workspace_path: str) -> Optional[CommandResult]:
        return self.run_command(
            ["mvn", "checkstyle:check", "-q"],
            cwd=workspace_path,
            timeout=self.LINT_TIMEOUT,
        )


# =========================================================
# 6. Go 适配器（按需扩展）
# =========================================================

class GoAdapter(LanguageAdapter):
    language = "go"

    def detect(self, workspace_path: str) -> bool:
        return os.path.isfile(os.path.join(workspace_path, "go.mod"))

    def install_dependencies(self, workspace_path: str) -> CommandResult:
        return self.run_command(
            ["go", "mod", "download"],
            cwd=workspace_path,
            timeout=self.INSTALL_TIMEOUT,
        )

    def compile(self, workspace_path: str) -> CommandResult:
        return self.run_command(
            ["go", "build", "./..."],
            cwd=workspace_path,
            timeout=self.COMPILE_TIMEOUT,
        )

    def run_tests(self, workspace_path: str) -> CommandResult:
        return self._parse_go_test(
            self.run_command(
                ["go", "test", "./...", "-v", "-count=1"],
                cwd=workspace_path,
                timeout=self.TEST_TIMEOUT,
            ),
        )

    def _parse_go_test(self, cr: CommandResult) -> CommandResult:
        output = cr.stdout + cr.stderr
        import re
        passes = len(re.findall(r"--- PASS:", output))
        fails = len(re.findall(r"--- FAIL:", output))
        cr.passed_tests = passes
        cr.failed_tests = fails
        cr.total_tests = passes + fails
        return cr

    def lint(self, workspace_path: str) -> Optional[CommandResult]:
        return self.run_command(
            ["go", "vet", "./..."],
            cwd=workspace_path,
            timeout=self.LINT_TIMEOUT,
        )


# =========================================================
# 7. Rust 适配器（按需扩展）
# =========================================================

class RustAdapter(LanguageAdapter):
    language = "rust"

    def detect(self, workspace_path: str) -> bool:
        return os.path.isfile(os.path.join(workspace_path, "Cargo.toml"))

    def compile(self, workspace_path: str) -> CommandResult:
        return self.run_command(
            ["cargo", "build"],
            cwd=workspace_path,
            timeout=self.COMPILE_TIMEOUT,
        )

    def run_tests(self, workspace_path: str) -> CommandResult:
        return self._parse_cargo_test(
            self.run_command(
                ["cargo", "test"],
                cwd=workspace_path,
                timeout=self.TEST_TIMEOUT,
            ),
        )

    def _parse_cargo_test(self, cr: CommandResult) -> CommandResult:
        output = cr.stdout + cr.stderr
        import re
        m = re.search(r"test result:.*?(\d+)\s+passed;\s*(\d+)\s+failed", output)
        if m:
            cr.passed_tests = int(m.group(1))
            cr.failed_tests = int(m.group(2))
            cr.total_tests = cr.passed_tests + cr.failed_tests
        return cr

    def lint(self, workspace_path: str) -> Optional[CommandResult]:
        return self.run_command(
            ["cargo", "clippy", "--", "-D", "warnings"],
            cwd=workspace_path,
            timeout=self.LINT_TIMEOUT,
        )


# =========================================================
# 8. 工厂函数
# =========================================================

_ADAPTER_REGISTRY: Dict[str, LanguageAdapter] = {}

def _build_registry():
    global _ADAPTER_REGISTRY
    if _ADAPTER_REGISTRY:
        return
    for cls in [PythonAdapter, JavaScriptAdapter, TypeScriptAdapter,
                JavaAdapter, GoAdapter, RustAdapter]:
        instance = cls()
        _ADAPTER_REGISTRY[instance.language] = instance


def get_adapter(language: str) -> Optional[LanguageAdapter]:
    _build_registry()
    return _ADAPTER_REGISTRY.get(language.lower())


def detect_language(workspace_path: str) -> Optional[str]:
    _build_registry()
    for lang, adapter in _ADAPTER_REGISTRY.items():
        try:
            if adapter.detect(workspace_path):
                return lang
        except Exception:
            continue
    return None