# -*- coding: utf-8 -*-
# python_worker/skill_registry.py — 技能工具注册表
# ---------------------------------------------------------
# 架构定位
#
# SkillRegistry 不再只是 LanguageAdapter 的薄包装。
# 它是契约驱动的能力执行层。
#
# 三层职责：
#   1. 契约查询    — get_skill_contract("compile") → SkillContract
#   2. 自动检测    — detect_project_metadata(ws) → ProjectMetadata
#   3. 契约执行    — execute_skill("compile", ws) → SkillResult + Evidence
#
# 概念关系：
#   SkillContract — 定义这个技能是什么、需要什么证据、怎样才算成功
#   ProjectMetadata — 描述当前项目的语言/构建/测试工具
#   LanguageAdapter — 将契约命令转为具体工具调用（mvn / pytest / npm ...）
#   CommandExecutor — 安全执行（白名单、边界、审计）
#
# 提醒：
#   Skill Registry 负责发现和选择能力，不负责绕过执行治理。
#   CodingWorker 的计划不等于执行授权。
# ---------------------------------------------------------

from __future__ import annotations

import re
import time
from typing import Optional, Dict, List

from command_executor import CommandResult, get_executor
from language_adapter import get_adapter, LanguageAdapter
from contracts.skill_contract import (
    SkillContract, SkillResult, SkillStatus, EvidenceSet,
    get_skill_contract, register_skill_contract,
)
from contracts.project_metadata import (
    ProjectMetadata, detect_project_metadata as _detect_project_metadata,
)


_SKILL_REGISTRY: Dict[str, str] = {}


# =========================================================
# 1. 项目检测（委托给 contracts）
# =========================================================

def _auto_detect_adapter(workspace: str) -> Optional[LanguageAdapter]:
    import os

    for marker in ["pom.xml", "build.gradle", "build.gradle.kts"]:
        if os.path.isfile(os.path.join(workspace, marker)):
            return get_adapter("java")

    if os.path.isfile(os.path.join(workspace, "Cargo.toml")):
        return get_adapter("rust")

    if os.path.isfile(os.path.join(workspace, "go.mod")):
        return get_adapter("go")

    if os.path.isfile(os.path.join(workspace, "tsconfig.json")):
        return get_adapter("typescript")

    if os.path.isfile(os.path.join(workspace, "package.json")):
        return get_adapter("javascript")

    if os.path.isfile(os.path.join(workspace, "requirements.txt")) or \
       any(f.endswith(".py") for f in os.listdir(workspace)
           if os.path.isfile(os.path.join(workspace, f))):
        return get_adapter("python")

    return None


def detect_project_type(workspace: str) -> Optional[str]:
    adapter = _auto_detect_adapter(workspace)
    return adapter.language if adapter else None


def detect_project_metadata(workspace: str) -> ProjectMetadata:
    return _detect_project_metadata(workspace)


# =========================================================
# 2. 原始技能执行（内部：返回 CommandResult）
# =========================================================

def run_skill(
    skill_name: str,
    workspace: str,
    adapter: Optional[LanguageAdapter] = None,
    timeout: Optional[int] = None,
) -> CommandResult:
    skill_name = skill_name.lower()

    if adapter is None:
        adapter = _auto_detect_adapter(workspace)
    if adapter is None:
        return CommandResult(
            error=f"skill_registry: cannot detect project type in {workspace}",
        )

    if skill_name == "compile":
        return adapter.compile(workspace)
    elif skill_name == "test":
        return adapter.run_tests(workspace)
    elif skill_name == "lint":
        result = adapter.lint(workspace)
        return result if result is not None else CommandResult(
            success=True, command="(lint not configured)", error="",
        )
    elif skill_name == "deps":
        result = adapter.install_dependencies(workspace)
        if not result.success and not result.error:
            result.error = result.stderr[:200] if result.stderr else "dependency install failed"
        return result
    else:
        return CommandResult(
            error=f"skill_registry: unknown skill '{skill_name}'. "
                  f"Available: compile, test, lint, deps",
        )


# =========================================================
# 3. 契约驱动的技能执行（外部接口：返回 SkillResult）
# =========================================================

def execute_skill(
    skill_name: str,
    workspace: str,
    adapter: Optional[LanguageAdapter] = None,
    timeout: Optional[int] = None,
) -> SkillResult:
    """按契约执行一个技能，返回结构化结果 + 证据包。

    流程：
      1. 查找 SkillContract
      2. 自动检测适配器
      3. 执行原始 CommandResult
      4. 提取证据（extract_evidence）
      5. 用 success_criteria 判定状态
      6. 返回 SkillResult

    证据不足 → SkillStatus.INCONCLUSIVE，不强行标记成功。
    """
    skill_name = skill_name.lower()
    contract = get_skill_contract(skill_name)
    t0 = time.time()

    cmd_result = run_skill(
        skill_name=skill_name,
        workspace=workspace,
        adapter=adapter,
        timeout=timeout or (contract.timeout_seconds if contract else 120),
    )
    duration = time.time() - t0

    # 被 CommandExecutor 拦截
    if cmd_result.blocked:
        return SkillResult(
            capability=skill_name,
            status=SkillStatus.BLOCKED,
            evidence=EvidenceSet(),
            contract=contract,
            error=cmd_result.block_reason or "execution blocked by governance",
            duration_seconds=duration,
        )

    evidence = _extract_evidence(skill_name, cmd_result, workspace)

    # 用契约判定状态
    if contract and contract.evidence_policy:
        evidence_passed, missing, low_conf = contract.evidence_policy.validate(evidence)
        if not evidence_passed:
            return SkillResult(
                capability=skill_name,
                status=SkillStatus.INCONCLUSIVE,
                exit_code=cmd_result.exit_code,
                stdout=cmd_result.stdout,
                stderr=cmd_result.stderr,
                duration_seconds=duration,
                evidence=evidence,
                contract=contract,
                error=f"insufficient evidence: missing={missing}, low_confidence={[i.key for i in low_conf]}",
            )

    status = _evaluate_status(cmd_result, contract, evidence)

    return SkillResult(
        capability=skill_name,
        status=status,
        exit_code=cmd_result.exit_code,
        stdout=cmd_result.stdout,
        stderr=cmd_result.stderr,
        duration_seconds=duration,
        evidence=evidence,
        contract=contract,
        error=cmd_result.error if cmd_result.error else "",
    )


def execute_skill_sequence(
    workspace: str,
    skills: List[str],
    stop_on_failure: bool = True,
) -> Dict[str, SkillResult]:
    results: Dict[str, SkillResult] = {}
    for skill_name in skills:
        result = execute_skill(skill_name, workspace)
        results[skill_name] = result
        if stop_on_failure and result.status in (
            SkillStatus.FAILED, SkillStatus.BLOCKED, SkillStatus.INCONCLUSIVE
        ):
            break
    return results


# =========================================================
# 4. 证据提取
# =========================================================

def _extract_evidence(
    skill_name: str,
    cmd_result: CommandResult,
    workspace: str,
) -> EvidenceSet:
    evidence = EvidenceSet()
    evidence.add("exit_code", cmd_result.exit_code, source="command_executor")

    if cmd_result.timed_out:
        evidence.add("timed_out", True, source="command_executor")
        return evidence

    if skill_name == "compile":
        _extract_compile_evidence(cmd_result, evidence, workspace)
    elif skill_name == "test":
        _extract_test_evidence(cmd_result, evidence)
    elif skill_name == "lint":
        _extract_lint_evidence(cmd_result, evidence)
    elif skill_name == "deps":
        _extract_deps_evidence(cmd_result, evidence)

    return evidence


def _extract_compile_evidence(
    cmd_result: CommandResult,
    evidence: EvidenceSet,
    workspace: str,
):
    stdout = cmd_result.stdout or ""
    stderr = cmd_result.stderr or ""

    # 编译成功
    evidence.add("compile_stdout", stdout[:3000], source="stdout_preview")

    # 警告计数
    warning_patterns = [
        (r'\bwarning[s]?\b', re.IGNORECASE),
        (r'WARNING', None),
        (r'\[WARNING\]', None),
    ]
    warning_count = 0
    for pattern, flags in warning_patterns:
        if flags:
            warning_count += len(re.findall(pattern, stdout))
        else:
            warning_count += stdout.count(pattern)
    if warning_count:
        evidence.add("warning_count", warning_count, source="stdout_parse", confidence=0.8)

    # 错误计数（含 stderr）
    error_count = stdout.count("error") + stderr.count("error")
    if error_count:
        evidence.add("error_count", error_count, source="stdout_parse", confidence=0.7)

    # 源文件计数（从工作区）
    try:
        import os
        src_files = [f for f in os.listdir(workspace)
                     if os.path.isfile(os.path.join(workspace, f))]
        evidence.add("source_files_count", len(src_files), source="filesystem", confidence=0.9)
    except OSError:
        pass


def _extract_test_evidence(
    cmd_result: CommandResult,
    evidence: EvidenceSet,
):
    stdout = cmd_result.stdout or ""

    # pytest 格式: N passed, M failed, K errors, ... in X.XXs
    pyt_match = re.search(
        r'(\d+)\s+passed[,\s]+(\d+)\s+failed',
        stdout, re.IGNORECASE
    )
    if pyt_match:
        evidence.add("test_passed", int(pyt_match.group(1)), source="stdout_parse", confidence=0.95)
        evidence.add("test_failed", int(pyt_match.group(2)), source="stdout_parse", confidence=0.95)
        evidence.add("test_total", int(pyt_match.group(1)) + int(pyt_match.group(2)),
                     source="computed", confidence=0.95)
        return

    # JUnit 格式: Tests run: N, Failures: M, Errors: K, Skipped: S
    jn_match = re.search(
        r'Tests run:\s*(\d+)[,\s]+Failures:\s*(\d+)[,\s]+Errors:\s*(\d+)[,\s]+Skipped:\s*(\d+)',
        stdout
    )
    if jn_match:
        total = int(jn_match.group(1))
        failures = int(jn_match.group(2))
        errors = int(jn_match.group(3))
        evidence.add("test_total", total, source="stdout_parse", confidence=0.95)
        evidence.add("test_passed", total - failures - errors, source="computed", confidence=0.85)
        evidence.add("test_failed", failures + errors, source="stdout_parse", confidence=0.95)
        return

    # Jest 格式: Tests: N passed, M failed, K total
    jest_match = re.search(
        r'Tests:\s*(\d+)\s+passed[,\s]+(\d+)\s+failed[,\s]+(\d+)\s+total',
        stdout, re.IGNORECASE
    )
    if jest_match:
        evidence.add("test_passed", int(jest_match.group(1)), source="stdout_parse", confidence=0.95)
        evidence.add("test_failed", int(jest_match.group(2)), source="stdout_parse", confidence=0.95)
        evidence.add("test_total", int(jest_match.group(3)), source="stdout_parse", confidence=0.95)
        return

    # Go test 格式: ok/FAIL + package + time
    go_matches = re.findall(r'^(ok|FAIL)\s+(\S+)', stdout, re.MULTILINE)
    if go_matches:
        passed = sum(1 for status, _ in go_matches if status == "ok")
        failed = sum(1 for status, _ in go_matches if status == "FAIL")
        evidence.add("test_total", passed + failed, source="stdout_parse", confidence=0.9)
        evidence.add("test_passed", passed, source="stdout_parse", confidence=0.9)
        evidence.add("test_failed", failed, source="stdout_parse", confidence=0.9)
        return

    # Rust cargo test 格式: test result: ok. N passed; M failed
    rust_match = re.search(
        r'test result:\s*(ok|FAILED)[.\s]+(\d+)\s+passed[;\s]+(\d+)\s+failed',
        stdout, re.IGNORECASE
    )
    if rust_match:
        evidence.add("test_passed", int(rust_match.group(2)), source="stdout_parse", confidence=0.95)
        evidence.add("test_failed", int(rust_match.group(3)), source="stdout_parse", confidence=0.95)
        evidence.add("test_total", int(rust_match.group(2)) + int(rust_match.group(3)),
                     source="computed", confidence=0.95)
        return

    # 降级：标记 inconclusive
    evidence.add("test_total", 0, source="fallback", confidence=0.0)
    evidence.add("test_passed", 0, source="fallback", confidence=0.0)
    evidence.add("test_failed", 0, source="fallback", confidence=0.0)
    evidence.summary = "no recognizable test output format detected"


def _extract_lint_evidence(
    cmd_result: CommandResult,
    evidence: EvidenceSet,
):
    evidence.add("lint_exit_code", cmd_result.exit_code, source="command_executor")
    stdout = cmd_result.stdout or ""
    stderr = cmd_result.stderr or ""

    # 尝试计数 lint issues
    combined = stdout + stderr
    issue_count = len(re.findall(r'^(error|warning|info)', combined, re.MULTILINE | re.IGNORECASE))
    if issue_count:
        evidence.add("lint_issue_count", issue_count, source="stdout_parse", confidence=0.8)
    else:
        # 以行数作为近似
        line_count = len([l for l in combined.split("\n") if l.strip()])
        if line_count > 0:
            evidence.add("lint_output_lines", line_count, source="stdout_count", confidence=0.5)


def _extract_deps_evidence(
    cmd_result: CommandResult,
    evidence: EvidenceSet,
):
    stdout = cmd_result.stdout or ""

    # npm/yarn: added N packages, removed M packages
    npm_match = re.search(
        r'(?:added|up to date|audited)\s+(\d+)\s+package',
        stdout, re.IGNORECASE
    )
    if npm_match:
        evidence.add("package_count", int(npm_match.group(1)), source="stdout_parse", confidence=0.8)

    # pip: Successfully installed ... (count packages)
    pip_match = re.search(r'Successfully installed\s+(.+)', stdout)
    if pip_match:
        pkgs = pip_match.group(1).split()
        evidence.add("package_count", len(pkgs), source="stdout_parse", confidence=0.8)

    # mvn/gradle: BUILD SUCCESS
    if "BUILD SUCCESS" in stdout:
        evidence.add("build_success", True, source="stdout_parse", confidence=0.9)


# =========================================================
# 5. 状态判定
# =========================================================

def _evaluate_status(
    cmd_result: CommandResult,
    contract: Optional[SkillContract],
    evidence: EvidenceSet,
) -> SkillStatus:
    """根据命令结果 + 契约 + 证据综合判定最终状态。"""

    # 被拦截
    if cmd_result.blocked:
        return SkillStatus.BLOCKED

    # 超时
    if cmd_result.timed_out:
        return SkillStatus.TIMED_OUT

    if not contract:
        return SkillStatus.SUCCEEDED if cmd_result.success else SkillStatus.FAILED

    criteria = contract.success_criteria

    # exit_code 检查
    if criteria.exit_code_zero and cmd_result.exit_code != 0:
        return SkillStatus.FAILED

    # 证据检查
    if criteria.evidence_required:
        passed, missing, _ = contract.evidence_policy.validate(evidence)
        if not passed:
            return SkillStatus.INCONCLUSIVE

    return SkillStatus.SUCCEEDED


# =========================================================
# 6. 公共接口
# =========================================================

def list_available_skills() -> List[str]:
    return ["compile", "test", "lint", "deps"]


def get_audit_trail() -> list:
    return get_executor().get_audit_trail()