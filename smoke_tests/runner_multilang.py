# smoke_tests/runner_multilang.py
"""Phase 2.4: Multi-language Worker E2E runner.
Tests language routing, queue mapping, and Worker execution pipelines
for Python / Java / Node.js / TypeScript.

Usage:
    cd AlphaPilot
    python -m smoke_tests.runner_multilang          # Offline only (routing + structure)
    python -m smoke_tests.runner_multilang --full    # Full E2E with real Qwen API
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from datetime import datetime

from smoke_tests.config import SCRIPT_DIR, DASHSCOPE_API_KEY
from smoke_tests.engine_multilang import (
    run_lang_route_tests,
    run_python_worker_e2e,
    run_node_worker_e2e,
    run_ts_worker_e2e,
    run_java_worker_routing_test,
)


def run(use_real_llm: bool = False) -> bool:
    now = datetime.now().isoformat()
    print(f"\n{'='*60}")
    print(f"Phase 2.4 Multi-language Worker E2E Tests")
    print(f"Time: {now}")
    print(f"Mode: {'Real LLM (Qwen API)' if use_real_llm else 'Offline (routing only)'}")
    print(f"API Key: {'Configured' if DASHSCOPE_API_KEY else 'MISSING'}")
    print(f"{'='*60}")

    all_results = []
    errors = []

    # ─────────────────────────────────────────────
    # Phase 1: Language Routing Tests (always run)
    # ─────────────────────────────────────────────
    print(f"\n{'='*40}")
    print("Part 1: Language Routing Detection")
    print(f"{'='*40}")

    try:
        route_results = run_lang_route_tests()
        for name, status, detail in route_results:
            suffix = f" — {detail}" if detail else ""
            print(f"  [{status}] {name}{suffix}")
        all_results.extend(route_results)
    except Exception as exc:
        errors.append(f"Routing tests: {exc}")
        print(f"  [ERROR] Routing tests failed: {exc}")

    # ─────────────────────────────────────────────
    # Phase 2: Java Worker Structure Verification
    # ─────────────────────────────────────────────
    print(f"\n{'='*40}")
    print("Part 2: Java Worker Structure")
    print(f"{'='*40}")

    try:
        java_results = run_java_worker_routing_test()
        for name, status, detail in java_results:
            suffix = f" — {detail}" if detail else ""
            print(f"  [{status}] {name}{suffix}")
        all_results.extend(java_results)
    except Exception as exc:
        errors.append(f"Java Worker: {exc}")
        print(f"  [ERROR] Java Worker verification failed: {exc}")

    # ─────────────────────────────────────────────
    # Phase 3: Worker E2E with Real LLM (--full)
    # ─────────────────────────────────────────────
    if use_real_llm:
        with tempfile.TemporaryDirectory(prefix="AlphaPilot_MultiLangE2E_") as temp:
            sandbox = Path(temp)
            (sandbox / "src").mkdir()
            (sandbox / "tests").mkdir()

            print(f"\n{'='*40}")
            print("Part 3: Worker E2E Smoke Tests (Real LLM)")
            print(f"{'='*40}")

            for worker_name, runner_fn in [
                ("Python Worker (baseline)", run_python_worker_e2e),
                ("Node.js Worker", run_node_worker_e2e),
                ("TypeScript Worker", run_ts_worker_e2e),
            ]:
                try:
                    name, status, detail = runner_fn(sandbox)
                    suffix = f" — {detail}" if detail else ""
                    print(f"  [{status}] {name}{suffix}")
                    all_results.append((name, status, detail))
                except Exception as exc:
                    error_msg = f"{worker_name}: {exc}"
                    errors.append(error_msg)
                    print(f"  [ERROR] {error_msg}")

    # ─────────────────────────────────────────────
    # Final Report
    # ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Multi-language E2E Report")
    print(f"{'='*60}")

    pass_count = sum(1 for _, s, _ in all_results if s == "PASS")
    fail_count = sum(1 for _, s, _ in all_results if s == "FAIL")
    incomplete = sum(1 for _, s, _ in all_results if s in ("INCOMPLETE", "PARTIAL", "BLOCKED"))

    print(f"\n  PASS:  {pass_count}")
    print(f"  FAIL:  {fail_count}")
    print(f"  INCOMPLETE: {incomplete}")
    print(f"  ERRORS: {len(errors)}")
    print(f"  TOTAL: {len(all_results)}")

    if errors:
        print(f"\n  Errors:")
        for e in errors:
            print(f"    - {e}")

    print()

    if fail_count == 0 and len(errors) == 0:
        print("✅ All multi-language routing + structure tests passed")
        if incomplete > 0:
            print(f"⚠️  {incomplete} test(s) incomplete (may need --full or environment setup)")
        return True
    else:
        print("❌ Some tests failed — review output above")
        return False


if __name__ == "__main__":
    use_full = "--full" in sys.argv
    try:
        raise SystemExit(0 if run(use_real_llm=use_full) else 1)
    except Exception as error:
        print(f"\n[CRITICAL] {type(error).__name__}: {error}")
        raise SystemExit(1) from error