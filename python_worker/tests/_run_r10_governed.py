# -*- coding: utf-8 -*-
"""R10 治理重试：通过统一任务状态机执行 Round 10 服务层重构。

PREPARE → SNAPSHOT → VERIFY_BASELINE → WORKER_EXECUTE → QUALITY_GATE
    QUALITY_GATE PASS → ACCEPT
    QUALITY_GATE FAIL → QUARANTINE → PRESERVE_DIFF → BASELINE_SAFE

前置：Node API、Redis、Worker 已启动。
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_observe_task_system import (
    _run_governed_task,
    _check_service_layer_contract,
    _check_semantic_contract,
    build_prompt_round_10,
    DEFAULT_WORKSPACE,
)


def main() -> int:
    ws = str(Path(DEFAULT_WORKSPACE))
    print("=" * 70)
    print("  R10 治理重试 —— 统一任务状态机闭环")
    print(f"  工作区: {ws}")
    print("=" * 70)

    # FAIL-CLOSED：从真实源码（基线）冻结语义契约后派生完整 PROMPT，
    # 若契约提取不完整则抛错中止，绝不以不含模型契约的模板放行。
    prompt = build_prompt_round_10(ws)
    print("  ✅ 已从基线冻结语义契约并派生完整 PROMPT_ROUND_10")

    result = _run_governed_task(
        prompt=prompt,
        workspace_path=ws,
        contract_checker=_check_service_layer_contract,
        semantic_contract_checker=_check_semantic_contract,
    )

    print("\n" + "=" * 70)
    print("  R10 治理重试结果")
    print("=" * 70)
    print(f"  最终状态: {result['state']}")
    print(f"  状态流转: {' → '.join(result['history'])}")
    print(f"  任务 ID: {result.get('task_id')}")

    baseline = result.get("baseline_test") or {}
    print(f"  基线测试: {'PASS' if baseline.get('passed') else 'FAIL'}")

    gate = result.get("gate_result")
    if gate:
        print(f"  门禁: {'PASS' if gate['passed'] else 'FAIL'}")
        checks = gate.get("checks", {})
        if "regression_test" in checks:
            rt = checks["regression_test"]
            print(f"    回归测试: {'PASS' if rt.get('passed') else 'FAIL'} "
                  f"(exit={rt.get('exit_code')}, timed_out={rt.get('timed_out')})")
        if "ast_contract" in checks:
            ac = checks["ast_contract"]
            print(f"    AST 契约: {'PASS' if ac.get('passed') else 'FAIL'}")
        if "semantic_contract" in checks:
            sc = checks["semantic_contract"]
            if "skipped" in sc:
                print(f"    语义契约: SKIPPED")
            else:
                print(f"    语义契约(四层): {'PASS' if sc.get('passed') else 'FAIL'}")
                if sc.get("failure_reason"):
                    print(f"      失败原因: {sc['failure_reason']}")
        if "baseline_compare" in checks:
            bc = checks["baseline_compare"]
            if "regressed" in bc:
                print(f"    基线对比: regressed={bc['regressed']}")
        if "file_scope" in checks:
            fs = checks["file_scope"]
            print(f"    文件范围: added={fs.get('added')} modified={fs.get('modified')} "
                  f"deleted={fs.get('deleted')}")

    quarantine = result.get("quarantine")
    if quarantine:
        print(f"  隔离目录: {quarantine.get('quarantine_dir')}")
        rollback = quarantine.get("rollback", {})
        print(f"  回滚: 恢复 {rollback.get('restored', 0)} 文件, "
              f"删除 {len(rollback.get('deleted_new', []))} 文件")

    if result.get("error"):
        print(f"  错误: {result['error']}")

    print("=" * 70)

    if result["state"] == "ACCEPT":
        print("  ✅ R10 治理重试通过（QUALITY_GATE 全部通过，已接受）")
        return 0
    else:
        print("  ⚠️ R10 未 ACCEPT（见上方门禁/隔离详情）")
        return 1


if __name__ == "__main__":
    sys.exit(main())