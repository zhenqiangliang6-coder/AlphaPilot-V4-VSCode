# smoke_tests/runner_expert.py
"""Phase 2.4: 编程专家角色测试运行器。

5大编程专家 × 10题 = 50题测试体系。
每个Worker在自己领域接收专家级任务，验证：
  - 语言检测 → 动态路由到对应Worker
  - Worker生成领域专业代码
  - 架构信条：Worker=真相 | Extension=映射 | Webview=投影 | 协议=宪法

Usage:
    python -m smoke_tests.runner_expert              # Offline (routing only, 50 tests)
    python -m smoke_tests.runner_expert --full        # Full E2E with real Qwen API
    python -m smoke_tests.runner_expert --role python # Single role
    python -m smoke_tests.runner_expert --role java   # Single role
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from datetime import datetime

from smoke_tests.config import SCRIPT_DIR, DASHSCOPE_API_KEY, runtime_report
from smoke_tests.definitions.P4_expert_roles import (
    ROLE_CONFIG,
    ALL_ROLES,
    TOTAL_QUESTIONS,
)
from smoke_tests.engine_expert import (
    run_expert_routing_tests,
    run_python_expert_e2e,
    run_node_expert_e2e,
    run_ts_expert_e2e,
    run_java_expert_verification,
)


def run(use_real_llm: bool = False, target_role: str | None = None) -> bool:
    now = datetime.now().isoformat()
    roles_to_run = [target_role] if target_role else ALL_ROLES

    print(f"\n{'='*70}")
    print(f"Phase 2.4 — 编程专家角色测试体系 (Expert Role E2E)")
    print(f"Time: {now}")
    print(f"Mode: {'Real LLM (Qwen API)' if use_real_llm else 'Offline (routing + structure)'}")
    print(f"API Key: {'Configured' if DASHSCOPE_API_KEY else 'MISSING'}")
    print(f"Roles: {', '.join(roles_to_run)}")

    rt = runtime_report()
    java_status = "✓" if rt['java'] else (f"JDK✓ Mvn✗" if rt['jdk'] else "✗")
    print(f"Runtime: Python ✓ | Node.js {'✓' if rt['nodejs'] else '✗'} | Java {java_status}")
    print(f"{'='*70}")

    all_results = []
    errors = []

    # ═════════════════════════════════════════════════════════════
    # Part 1: Language Routing Tests (always run, 50 questions)
    # ═════════════════════════════════════════════════════════════
    print(f"\n{'─'*60}")
    print("Part 1: Expert Role Language Routing (50 questions)")
    print(f"{'─'*60}")

    try:
        route_results = run_expert_routing_tests()

        # Filter by role if specified
        if target_role:
            role = ROLE_CONFIG[target_role]
            role_prefix = role["role_name"]
            filtered = [(n, s, d) for n, s, d in route_results
                       if role_prefix in n]
            route_results = filtered

        # Group by role for display
        role_groups = {}
        for name, status, detail in route_results:
            for role_key in roles_to_run:
                role_name = ROLE_CONFIG[role_key]["role_name"]
                if role_name in name:
                    role_groups.setdefault(role_name, []).append((name, status, detail))
                    break

        for role_name in role_groups:
            items = role_groups[role_name]
            pass_in_role = sum(1 for _, s, _ in items if s == "PASS")
            fail_in_role = sum(1 for _, s, _ in items if s == "FAIL")
            icon = "✅" if fail_in_role == 0 else "⚠️"
            print(f"\n  {icon} {role_name} ({pass_in_role}/{len(items)} routing)")
            for name, status, detail in items:
                if status != "PASS":
                    suffix = f" — {detail}" if detail else ""
                    print(f"     [{status}] {name}{suffix}")

        all_results.extend(route_results)
    except Exception as exc:
        errors.append(f"Routing tests: {exc}")
        print(f"  [ERROR] Routing tests failed: {exc}")

    # ═════════════════════════════════════════════════════════════
    # Part 2: Worker E2E with Real LLM (--full mode)
    # ═════════════════════════════════════════════════════════════
    if use_real_llm:
        print(f"\n{'─'*60}")
        print("Part 2: Expert Worker E2E (Real Qwen API)")
        print(f"{'─'*60}")

        with tempfile.TemporaryDirectory(prefix="AlphaPilot_ExpertE2E_") as temp:
            sandbox = Path(temp)
            (sandbox / "src").mkdir(parents=True, exist_ok=True)
            (sandbox / "tests").mkdir(parents=True, exist_ok=True)
            (sandbox / "logs").mkdir(parents=True, exist_ok=True)

            # ── Python Expert ──
            if not target_role or target_role in ("python_expert", "system_expert"):
                print(f"\n  🐍 Python 编程专家 + 系统工程专家")
                print(f"  {'─'*40}")

                try:
                    py_results = run_python_expert_e2e(sandbox)
                    for name, status, detail in py_results:
                        icon = _status_icon(status)
                        suffix = f" — {detail}" if detail else ""
                        print(f"    {icon} [{status}] {name}{suffix}")
                    all_results.extend(py_results)
                except Exception as exc:
                    errors.append(f"Python Expert: {exc}")
                    print(f"    [ERROR] {exc}")

            # ── JavaScript Expert ──
            if not target_role or target_role == "javascript_expert":
                print(f"\n  📦 JavaScript 编程专家")
                print(f"  {'─'*40}")

                try:
                    js_results = run_node_expert_e2e(sandbox)
                    for name, status, detail in js_results:
                        icon = _status_icon(status)
                        suffix = f" — {detail}" if detail else ""
                        print(f"    {icon} [{status}] {name}{suffix}")
                    all_results.extend(js_results)
                except Exception as exc:
                    errors.append(f"JavaScript Expert: {exc}")
                    print(f"    [ERROR] {exc}")

            # ── TypeScript Expert ──
            if not target_role or target_role == "typescript_expert":
                print(f"\n  🔷 TypeScript 编程专家")
                print(f"  {'─'*40}")

                try:
                    ts_results = run_ts_expert_e2e(sandbox)
                    for name, status, detail in ts_results:
                        icon = _status_icon(status)
                        suffix = f" — {detail}" if detail else ""
                        print(f"    {icon} [{status}] {name}{suffix}")
                    all_results.extend(ts_results)
                except Exception as exc:
                    errors.append(f"TypeScript Expert: {exc}")
                    print(f"    [ERROR] {exc}")

            # ── Java Expert ──
            if not target_role or target_role == "java_expert":
                print(f"\n  ☕ Java 编程专家")
                print(f"  {'─'*40}")

                try:
                    jv_results = run_java_expert_verification(sandbox)
                    for name, status, detail in jv_results:
                        icon = _status_icon(status)
                        suffix = f" — {detail}" if detail else ""
                        print(f"    {icon} [{status}] {name}{suffix}")
                    all_results.extend(jv_results)
                except Exception as exc:
                    errors.append(f"Java Expert: {exc}")
                    print(f"    [ERROR] {exc}")

    # ═════════════════════════════════════════════════════════════
    # Final Report
    # ═════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("Expert Role E2E Report")
    print(f"{'='*70}")

    pass_count = sum(1 for _, s, _ in all_results if s == "PASS")
    fail_count = sum(1 for _, s, _ in all_results if s == "FAIL")
    incomplete = sum(1 for _, s, _ in all_results
                    if s in ("INCOMPLETE", "PARTIAL", "BLOCKED"))

    print(f"\n  PASS:       {pass_count}")
    print(f"  FAIL:       {fail_count}")
    print(f"  INCOMPLETE: {incomplete}")
    print(f"  ERRORS:     {len(errors)}")
    print(f"  TOTAL:      {len(all_results)}")

    if errors:
        print(f"\n  Errors:")
        for e in errors:
            print(f"    - {e}")

    # Per-role summary
    print(f"\n  Per-Role Summary:")
    for role_key in roles_to_run:
        role = ROLE_CONFIG[role_key]
        role_name = role["role_name"]
        role_prefix = role_name
        role_pass = sum(1 for n, s, _ in all_results if s == "PASS" and role_prefix in n)
        role_total = sum(1 for n, _, _ in all_results if role_prefix in n)
        if role_total > 0:
            ratio = f"{role_pass}/{role_total}"
            bar = "█" * role_pass + "░" * (role_total - role_pass)
            print(f"    {_role_icon(role_key)} {role_name:20s} [{bar}] {ratio}")

    print()

    if fail_count == 0 and len(errors) == 0:
        print("✅ All expert role tests passed")
        if incomplete > 0:
            print(f"⚠️  {incomplete} test(s) incomplete (may need --full or env setup)")
        return True
    else:
        print("❌ Some tests failed — review output above")
        return False


def _status_icon(status: str) -> str:
    if status == "PASS":
        return "✅"
    elif status == "FAIL":
        return "❌"
    elif status in ("INCOMPLETE", "PARTIAL"):
        return "⚠️"
    elif status == "BLOCKED":
        return "🚫"
    return "❓"


def _role_icon(role_key: str) -> str:
    icons = {
        "python_expert": "🐍",
        "java_expert": "☕",
        "javascript_expert": "📦",
        "typescript_expert": "🔷",
        "system_expert": "⚙️",
    }
    return icons.get(role_key, "❓")


if __name__ == "__main__":
    use_full = "--full" in sys.argv
    target_role = None

    for i, arg in enumerate(sys.argv):
        if arg == "--role" and i + 1 < len(sys.argv):
            target_role = sys.argv[i + 1]
            if target_role not in ALL_ROLES:
                print(f"Unknown role: {target_role}")
                print(f"Available: {', '.join(ALL_ROLES)}")
                raise SystemExit(1)

    try:
        raise SystemExit(0 if run(use_real_llm=use_full, target_role=target_role) else 1)
    except Exception as error:
        print(f"\n[CRITICAL] {type(error).__name__}: {error}")
        raise SystemExit(1) from error