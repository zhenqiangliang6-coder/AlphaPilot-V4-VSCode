"""Smoke test runner: orchestrates all scenarios and prints the final report."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from smoke_tests.config import (
    SCRIPT_DIR,
    apply_file_ops,
    run_pytest,
)
from smoke_tests.turns import (
    TURNS,
    GENERATED_PROTOCOL,
    run_worker_turn,
    exercise_memory_integration,
    exercise_real_memory_integration,
)
from smoke_tests.engine import (
    run_single_self_healing_scenario,
    run_multi_file_self_healing_scenario,
    UNFIXABLE,
)
from smoke_tests.definitions import P0_baseline as p0
from smoke_tests.definitions import P1_intermediate as p1
from smoke_tests.definitions import P2_advanced as p2

from python_worker.dependency_merger import merge_dependencies, dependency_summary
from python_worker.context_builder import inspect_python_project
from python_worker.file_ops import parse_fileops_v3
from python_worker.intent_router import IntentRouter


def _run_self_healing_smoke(sandbox: Path) -> list[tuple[str, str, str]]:
    """Run all 42 self-healing scenarios and return per-question results."""
    results = []

    # ── S0：单文件除零 ──
    status, detail = run_single_self_healing_scenario(
        sandbox=sandbox,
        label="S0-div-zero",
        scenario_prompt="write a divide function and test it",
        write_code=p0.BUGGY_DIV,
        write_content="calc.py",
        test_content=p0.TEST_PASSING,
        fix_rounds=1,
        fix_effect="real_llm",
    )
    results.append(("self-heal[S0] div-zero guard", status, detail))

    # ── S1：源文件缺 import ──
    status, detail = run_single_self_healing_scenario(
        sandbox=sandbox,
        label="S1-missing-import",
        scenario_prompt="write a JSON serialize function and test it",
        write_code=p0.BUGGY_MISSING_IMPORT,
        write_content="serializer.py",
        test_content=p0.TEST_MISSING_IMPORT,
        fix_rounds=1,
        fix_effect="real_llm",
    )
    results.append(("self-heal[S1] source file missing import", status, detail))

    # ── S2：跨文件类型错误 ──
    status, detail = run_multi_file_self_healing_scenario(
        sandbox=sandbox,
        label="S2-cross-file-type",
        scenario_prompt="write a discount calculator and test it",
        write_files={"src/constants.py": p0.BUGGY_CONSTANTS,
                      "src/calc.py": p0.BUGGY_CALC_CROSS},
        test_content=p0.TEST_CROSS_FILE_TYPE,
        fix_effect="real_llm",
    )
    results.append(("self-heal[S2] cross-file type error", status, detail))

    # ── S3：边界条件误判 ──
    status, detail = run_single_self_healing_scenario(
        sandbox=sandbox,
        label="S3-boundary",
        scenario_prompt="write a string truncate function and test it",
        write_code=p0.BUGGY_TRUNCATE,
        write_content="text_tools.py",
        test_content=p0.TEST_TRUNCATE,
        fix_rounds=1,
        fix_effect="real_llm",
    )
    results.append(("self-heal[S3] boundary condition", status, detail))

    # ── S4：mock 失败路径（回环上限）──
    status, detail = run_single_self_healing_scenario(
        sandbox=sandbox,
        label="S4-mock-fail",
        scenario_prompt="write a broken function and test it",
        write_code=UNFIXABLE,
        write_content="broken_mod.py",
        test_content=p0.TEST_UNFIXABLE,
        fix_rounds=3,
        fix_effect="never_fix",
    )
    results.append(("self-heal[S4] failure loop cap", status, detail))

    # ── S5：跨文件 import 链 ──
    status, detail = run_multi_file_self_healing_scenario(
        sandbox=sandbox,
        label="S5-import-chain",
        scenario_prompt="write JSON encode/decode and test it",
        write_files={"src/encoder.py": p0.BUGGY_ENCODER,
                      "src/api.py": p0.BUGGY_API_CHAIN},
        test_content=p0.TEST_IMPORT_CHAIN,
        fix_effect="real_llm",
    )
    results.append(("self-heal[S5] cross-file import chain", status, detail))

    # ===== P0: 6 道 42 题矩阵试题 =====

    stats = {}

    # T1: Q-028 LRU 缓存
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T1-LRU",
        scenario_prompt="write an LRU cache class and test it",
        write_code=p0.BUGGY_LRU, write_content="lru.py",
        test_content=p0.TEST_LRU, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T1] Q-028 LRU cache eviction", stats[0], stats[1]))

    # T2: Q-001 验证漏上界
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T2-validator",
        scenario_prompt="write a range validator and test it",
        write_code=p0.BUGGY_VALIDATOR, write_content="validator.py",
        test_content=p0.TEST_VALIDATOR, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T2] Q-001 missing upper bound", stats[0], stats[1]))

    # T3: Q-031 输入验证
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T3-parser",
        scenario_prompt="write a range parser and test it",
        write_code=p0.BUGGY_PARSER, write_content="parser.py",
        test_content=p0.TEST_PARSER, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T3] Q-031 input validation", stats[0], stats[1]))

    # T4: Q-006 闭包陷阱
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T4-closure",
        scenario_prompt="write a multiplier factory and test it",
        write_code=p0.BUGGY_CLOSURE, write_content="closure.py",
        test_content=p0.TEST_CLOSURE, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T4] Q-006 closure late-binding", stats[0], stats[1]))

    # T5: Q-019 配置无默认值
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T5-config",
        scenario_prompt="write a database config module and test it",
        write_code=p0.BUGGY_CONFIG, write_content="config.py",
        test_content=p0.TEST_CONFIG, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T5] Q-019 no default config", stats[0], stats[1]))

    # T6: Q-035 CLI 文件操作
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T6-cli",
        scenario_prompt="write a file uppercase transformer and test it",
        write_code=p0.BUGGY_CLI, write_content="cli.py",
        test_content=p0.TEST_CLI, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T6] Q-035 CLI missing file check", stats[0], stats[1]))

    # ===== P1: 15 道 42 题矩阵试题 =====

    # T7: Q-002 可变默认参数
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T7-mutable-default",
        scenario_prompt="write a list append function and test default arg behavior",
        write_code=p1.BUGGY_MUTABLE_DEFAULT, write_content="collector.py",
        test_content=p1.TEST_MUTABLE_DEFAULT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T7] Q-002 mutable default arg", stats[0], stats[1]))

    # T8: Q-003 过度宽泛异常
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T8-bare-except",
        scenario_prompt="write a safe string-to-int parser and test it",
        write_code=p1.BUGGY_BARE_EXCEPT, write_content="safe_parser.py",
        test_content=p1.TEST_BARE_EXCEPT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T8] Q-003 bare except", stats[0], stats[1]))

    # T9: Q-004 遍历时修改列表
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T9-iter-mod",
        scenario_prompt="write a function to remove odds from a list and test it",
        write_code=p1.BUGGY_FILE_LEAK, write_content="filter.py",
        test_content=p1.TEST_FILE_LEAK, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T9] Q-004 modify-during-iteration", stats[0], stats[1]))

    # T10: Q-005 None 传播链
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T10-none-chain",
        scenario_prompt="write a user query service and test it",
        write_code=p1.BUGGY_NONE_CHAIN, write_content="user_svc.py",
        test_content=p1.TEST_NONE_CHAIN, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T10] Q-005 None propagation", stats[0], stats[1]))

    # T11: Q-007 除零无保护
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T11-avg-zero",
        scenario_prompt="write an average function and test empty list",
        write_code=p1.BUGGY_AVG_ZERO, write_content="stats.py",
        test_content=p1.TEST_AVG_ZERO, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T11] Q-007 zero division", stats[0], stats[1]))

    # T12: Q-008 空列表索引
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T12-last-elem",
        scenario_prompt="write a last-element function and test empty list",
        write_code=p1.BUGGY_LAST_ELEM, write_content="tools.py",
        test_content=p1.TEST_LAST_ELEM, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T12] Q-008 empty list index", stats[0], stats[1]))

    # T13: Q-009 字典键缺失
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T13-dict-key",
        scenario_prompt="write a dict value extractor and test missing keys",
        write_code=p1.BUGGY_DICT_KEY, write_content="extractor.py",
        test_content=p1.TEST_DICT_KEY, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T13] Q-009 dict key missing", stats[0], stats[1]))

    # T14: Q-010 None 类型运算
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T14-none-arith",
        scenario_prompt="write a score aggregator and test missing data",
        write_code=p1.BUGGY_NONE_ARITH, write_content="scorer.py",
        test_content=p1.TEST_NONE_ARITH, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T14] Q-010 None arithmetic", stats[0], stats[1]))

    # T15: Q-011 递归无终止
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T15-factorial",
        scenario_prompt="write a factorial function and test base case",
        write_code=p1.BUGGY_FACTORIAL, write_content="math_utils.py",
        test_content=p1.TEST_FACTORIAL, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T15] Q-011 missing base case", stats[0], stats[1]))

    # T16: Q-012 编码缺失
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T16-encoding",
        scenario_prompt="write a file reader and test multilang text",
        write_code=p1.BUGGY_ENCODING, write_content="reader.py",
        test_content=p1.TEST_ENCODING, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T16] Q-012 missing encoding", stats[0], stats[1]))

    # T17: Q-013 浮点数精度
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T17-float-eq",
        scenario_prompt="write a float sum checker and test 0.1+0.2",
        write_code=p1.BUGGY_FLOAT_EQ, write_content="checker.py",
        test_content=p1.TEST_FLOAT_EQ, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T17] Q-013 float precision", stats[0], stats[1]))

    # T18: Q-014 正则转义
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T18-regex-inject",
        scenario_prompt="write a regex matcher and test special chars",
        write_code=p1.BUGGY_REGEX, write_content="matcher.py",
        test_content=p1.TEST_REGEX, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T18] Q-014 regex injection", stats[0], stats[1]))

    # T19: Q-015 跨文件 None 传播
    stats = run_multi_file_self_healing_scenario(
        sandbox=sandbox, label="T19-cross-none",
        scenario_prompt="write a user greeter service and test missing users",
        write_files={"src/users_db.py": p1.BUGGY_SERVICE_NONE,
                      "src/greeter.py": p1.BUGGY_HANDLER_NONE},
        test_content=p1.TEST_CROSS_NONE,
        fix_effect="real_llm",
    )
    results.append(("self-heal[T19] Q-015 cross-file None", stats[0], stats[1]))

    # T20: Q-016 跨文件类型语义
    stats = run_multi_file_self_healing_scenario(
        sandbox=sandbox, label="T20-cross-strtype",
        scenario_prompt="write an e-commerce pricing module and test it",
        write_files={"src/pricing.py": p1.BUGGY_STR_RETURN,
                      "src/checkout.py": p1.BUGGY_STR_CONSUMER},
        test_content=p1.TEST_CROSS_STR_TYPE,
        fix_effect="real_llm",
    )
    results.append(("self-heal[T20] Q-016 cross-file type", stats[0], stats[1]))

    # T21: Q-017 全局可变状态
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T21-global-state",
        scenario_prompt="write a counter module (inc/dec/reset) and test it",
        write_code=p1.BUGGY_GLOBAL_CTR, write_content="tally.py",
        test_content=p1.TEST_GLOBAL_CTR, fix_rounds=2, fix_effect="real_llm",
    )
    results.append(("self-heal[T21] Q-017 global mutable state", stats[0], stats[1]))

    # ===== P2: 21 道 42 题矩阵试题 =====

    # T22: Q-018 SQL 注入
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T22-sql-inject",
        scenario_prompt="write a DB user query function and test injection",
        write_code=p2.BUGGY_SQL_INJECT, write_content="user_search.py",
        test_content=p2.TEST_SQL_INJECT, fix_rounds=2, fix_effect="real_llm",
    )
    results.append(("self-heal[T22] Q-018 SQL injection", stats[0], stats[1]))

    # T23: Q-020 路径遍历
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T23-path-traverse",
        scenario_prompt="write a safe file reader with base dir and test it",
        write_code=p2.BUGGY_PATH_TRAVERSAL, write_content="file_access.py",
        test_content=p2.TEST_PATH_TRAVERSAL, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T23] Q-020 path traversal", stats[0], stats[1]))

    # T24: Q-021 import 未用前缀
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T24-no-prefix",
        scenario_prompt="write a circle circumference function and test it",
        write_code=p2.BUGGY_MOD_A, write_content="mod_a.py",
        test_content=p2.TEST_CIRCULAR_IMPORT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T24] Q-021 missing import prefix", stats[0], stats[1]))

    # T25: Q-022 str+int 拼接
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T25-str-int",
        scenario_prompt="write a page label generator and test it",
        write_code=p2.BUGGY_FULL_READ, write_content="pager.py",
        test_content=p2.TEST_FULL_READ, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T25] Q-022 str+int concat", stats[0], stats[1]))

    # T26: Q-023 字典遍历删除
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T26-dict-del",
        scenario_prompt="write a dict cleaner that removes by value and test it",
        write_code=p2.BUGGY_DICT_DEL, write_content="cleaner.py",
        test_content=p2.TEST_DICT_DEL, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T26] Q-023 dict iter delete", stats[0], stats[1]))

    # T27: Q-024 list.insert(-1)
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T27-insert-neg",
        scenario_prompt="write a list right-padder and test it",
        write_code=p2.BUGGY_UNSAFE_CTR, write_content="padder.py",
        test_content=p2.TEST_UNSAFE_CTR, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T27] Q-024 list.insert(-1)", stats[0], stats[1]))

    # T28: Q-025 set 无序去重
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T28-set-order",
        scenario_prompt="write a dedup function preserving order and test it",
        write_code=p2.BUGGY_TZ_NAIVE, write_content="uniquer.py",
        test_content=p2.TEST_TZ_NAIVE, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T28] Q-025 set order loss", stats[0], stats[1]))

    # T29: Q-026 浅拷贝陷阱
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T29-shallow-copy",
        scenario_prompt="write a copy-2d-list function and test independence",
        write_code=p2.BUGGY_SHALLOW_COPY, write_content="grid_util.py",
        test_content=p2.TEST_SHALLOW_COPY, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T29] Q-026 shallow copy trap", stats[0], stats[1]))

    # T30: Q-027 敏感信息泄漏
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T30-log-leak",
        scenario_prompt="write an API client and test no token in logs",
        write_code=p2.BUGGY_LOG_LEAK, write_content="api_client.py",
        test_content=p2.TEST_LOG_LEAK, fix_rounds=2, fix_effect="real_llm",
    )
    results.append(("self-heal[T30] Q-027 sensitive info leak", stats[0], stats[1]))

    # T31: Q-029 生成器复用
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T31-gen-reuse",
        scenario_prompt="write a rank-and-split function and test it",
        write_code=p2.BUGGY_GEN_REUSE, write_content="ranker.py",
        test_content=p2.TEST_GEN_REUSE, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T31] Q-029 generator reuse", stats[0], stats[1]))

    # T32: Q-030 类属性共享
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T32-class-attr",
        scenario_prompt="write a ShoppingCart class and test instance independence",
        write_code=p2.BUGGY_CLASS_ATTR, write_content="cart.py",
        test_content=p2.TEST_CLASS_ATTR, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T32] Q-030 class attr sharing", stats[0], stats[1]))

    # T33: Q-032 NaN 比较
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T33-nan-cmp",
        scenario_prompt="write a NaN detector and test it",
        write_code=p2.BUGGY_NAN_CMP, write_content="validator.py",
        test_content=p2.TEST_NAN_CMP, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T33] Q-032 NaN comparison", stats[0], stats[1]))

    # T34: Q-033 HTTP 无超时
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T34-no-timeout",
        scenario_prompt="write an HTTP fetch function and test timeout",
        write_code=p2.BUGGY_NO_TIMEOUT, write_content="fetcher.py",
        test_content=p2.TEST_NO_TIMEOUT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T34] Q-033 HTTP no timeout", stats[0], stats[1]))

    # T35: Q-034 JSON 序列化
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T35-json-serial",
        scenario_prompt="write a JSON serialize function for records and test it",
        write_code=p2.BUGGY_JSON_SERIALIZE, write_content="serializer.py",
        test_content=p2.TEST_JSON_SERIALIZE, fix_rounds=2, fix_effect="real_llm",
    )
    results.append(("self-heal[T35] Q-034 JSON serialization", stats[0], stats[1]))

    # T36: Q-036 正则贪婪
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T36-greedy-regex",
        scenario_prompt="write a curly-brace tag extractor and test it",
        write_code=p2.BUGGY_CMD_INJECT, write_content="tagger.py",
        test_content=p2.TEST_CMD_INJECT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T36] Q-036 greedy regex", stats[0], stats[1]))

    # T37: Q-037 浮点累积误差
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T37-float-accum",
        scenario_prompt="write a total price calculator and test it",
        write_code=p2.BUGGY_FLOAT_ACCUM, write_content="pricing.py",
        test_content=p2.TEST_FLOAT_ACCUM, fix_rounds=2, fix_effect="real_llm",
    )
    results.append(("self-heal[T37] Q-037 float accumulation", stats[0], stats[1]))

    # T38: Q-038 assert 校验
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T38-assert-check",
        scenario_prompt="write an age setter and test input validation",
        write_code=p2.BUGGY_ASSERT_CHECK, write_content="age_setter.py",
        test_content=p2.TEST_ASSERT_CHECK, fix_rounds=2, fix_effect="real_llm",
    )
    results.append(("self-heal[T38] Q-038 assert validation", stats[0], stats[1]))

    # T39: Q-039 字符串版本比较
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T39-ver-cmp",
        scenario_prompt="write a version comparison function and test '9' vs '10'",
        write_code=p2.BUGGY_HANDLE_LEAK, write_content="vercmp.py",
        test_content=p2.TEST_HANDLE_LEAK, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T39] Q-039 string version cmp", stats[0], stats[1]))

    # T40: Q-040 __init__ 默认参数
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T40-init-default",
        scenario_prompt="write a Collector class and test instance independence",
        write_code=p2.BUGGY_INIT_DEFAULT, write_content="collector_cls.py",
        test_content=p2.TEST_INIT_DEFAULT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T40] Q-040 __init__ default arg", stats[0], stats[1]))

    # T41: Q-041 is 比较字符串
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T41-is-str",
        scenario_prompt="write a 'is hello' checker and test it",
        write_code=p2.BUGGY_STAR_IMPORT, write_content="strcmp.py",
        test_content=p2.TEST_STAR_IMPORT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T41] Q-041 'is' string cmp", stats[0], stats[1]))

    # T42: Q-042 协程未 await
    stats = run_single_self_healing_scenario(
        sandbox=sandbox, label="T42-missing-await",
        scenario_prompt="write an async user query + sync wrapper and test it",
        write_code=p2.BUGGY_MISSING_AWAIT, write_content="user_async.py",
        test_content=p2.TEST_MISSING_AWAIT, fix_rounds=1, fix_effect="real_llm",
    )
    results.append(("self-heal[T42] Q-042 missing await", stats[0], stats[1]))

    return results


def run() -> bool:
    use_real_db = "--full" in sys.argv or os.getenv(
        "ALPHAPILOT_SMOKE_REAL_DB", ""
    ).lower() in ("1", "true", "yes")

    print("AlphaPilot offline E2E smoke test")
    print(f"Project: {SCRIPT_DIR}")
    if use_real_db:
        print("[link] Real PostgreSQL memory mode (--full)")
    else:
        print("[fast] Quick mode (mock memory), use --full for real PostgreSQL")
    results = []

    with tempfile.TemporaryDirectory(prefix="AlphaPilot_SmokeTest_") as temp:
        sandbox = Path(temp)
        (sandbox / "src").mkdir()
        (sandbox / "tests").mkdir()
        (sandbox / "src" / "app.py").write_text(
            "def run():\n    return True\n", encoding="utf-8"
        )

        turn_results = []
        for label, prompt, expected_intent, expected_persona, expected_mode in TURNS:
            routed_intent, routed_persona, routed_chain = IntentRouter.detect_intent(prompt)
            assert routed_intent == expected_intent, (label, routed_intent)
            assert routed_persona == expected_persona, (label, routed_persona)

            result = run_worker_turn(sandbox, prompt)
            assert result["intent"] == expected_intent, (label, result["intent"])
            assert result["persona"] == expected_persona, (label, result["persona"])
            assert result["mode"] == expected_mode, (label, result["mode"])
            assert result["chain"] == routed_chain, (label, result["chain"])
            turn_results.append(result)

        actual_personas = {result["persona"] for result in turn_results}
        if {"architect", "reviewer"}.issubset(actual_personas):
            results.append(("Independent architect/reviewer personas", "PASS", ""))
        else:
            results.append((
                "Dedicated architect/reviewer roles and architecture write",
                "GAP",
                "Architecture routes to engineer persona + teacher mode",
            ))

        dep_project = sandbox / "dependency-check"
        dep_project.mkdir()
        (dep_project / "requirements.txt").write_text(
            "pandas\nnumpy\n", encoding="utf-8"
        )
        (dep_project / "main.py").write_text(
            "import pandas\nimport numpy\nimport openpyxl\n", encoding="utf-8"
        )
        scan = inspect_python_project(str(dep_project))

        unified = {d["name"]: d for d in scan.get("unified_dependencies", [])}
        assert "pandas" in unified, "pandas missing from unified_dependencies"
        assert "numpy" in unified, "numpy missing from unified_dependencies"

        pandas_entry = unified["pandas"]
        numpy_entry = unified["numpy"]

        assert set(pandas_entry["sources"]) == {"manifest", "ast_import"}, \
            f"pandas sources: {pandas_entry['sources']}"
        assert pandas_entry["signal_count"] == 2
        assert set(numpy_entry["sources"]) == {"manifest", "ast_import"}, \
            f"numpy sources: {numpy_entry['sources']}"
        assert numpy_entry["signal_count"] == 2

        assert "openpyxl" in scan["unresolved_imports"]

        summary = scan["dependency_summary"]
        assert summary["total"] == 2
        assert summary["by_source"]["manifest"] == 2
        assert summary["by_source"]["ast_import"] == 2
        assert summary["multi_signal"] == 2

        results.append((
            "Unified dependency merge & dedup",
            "PASS",
            "Manifest + AST merged: pandas/numpy=2-signal; openpyxl=unresolved",
        ))

        if use_real_db:
            memory_ok, memory_detail = exercise_real_memory_integration(sandbox)
            if memory_ok:
                results.append((
                    "Cross-turn memory integration (PostgreSQL)",
                    "PASS",
                    "Real PostgreSQL write->cross-turn retrieval passed",
                ))
            else:
                results.append((
                    "Cross-turn memory integration (PostgreSQL)",
                    "GAP",
                    f"Real PostgreSQL unavailable: {memory_detail}",
                ))
        else:
            memory_ok = exercise_memory_integration()
            assert memory_ok, "Memory integration did not retrieve stored test memory"
            results.append((
                "Cross-turn memory integration",
                "PARTIAL",
                "Integration wrapper passed with in-memory provider; PostgreSQL not exercised",
            ))
            print("  [PARTIAL] Cross-turn memory integration - mock provider only")

        generated_ops = [
            operation
            for operation in parse_fileops_v3(GENERATED_PROTOCOL)
            if operation.get("path")
        ]
        apply_file_ops(sandbox, generated_ops)
        pytest_result = run_pytest(sandbox)
        if pytest_result is None:
            results.append(("Multi-file generation + real pytest", "BLOCKED", "pytest not installed"))
        else:
            if pytest_result.returncode != 0:
                raise AssertionError(
                    "Sandbox pytest failed:\n"
                    + pytest_result.stdout
                    + pytest_result.stderr
                )
            results.append(("Multi-file FileOps + real pytest fixture", "PASS", ""))
        results.extend(_run_self_healing_smoke(sandbox))

        for label, result in zip((turn[0] for turn in TURNS), turn_results):
            print(
                f"  {label}: intent={result['intent']} persona={result['persona']} "
                f"mode={result['mode']} chain={' -> '.join(result['chain'])}"
            )
        for name, status, detail in results:
            suffix = f" - {detail}" if detail else ""
            print(f"  [{status}] {name}{suffix}")

        review, mentor = turn_results[2], turn_results[3]
        assert review["mode"] == "reviewer" and not review["file_ops"]
        assert mentor["mode"] == "teacher" and not mentor["file_ops"]
        assert "test" in turn_results[1]["deferred"], (
            "Engineer test execution should remain approval-gated."
        )
        results.append(("Read-only review/teaching + test approval gate", "PASS", ""))
        print("  [PASS] Read-only review/teaching + test approval gate")

    gaps = [item for item in results if item[1] in {"GAP", "PARTIAL", "BLOCKED"}]
    print(f"\nResult: {len(results) - len(gaps)} PASS, {len(gaps)} incomplete")
    print("The sandbox was automatically removed; no project files were written.")
    return not gaps


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(0 if run() else 1)
    except Exception as error:
        print(f"[FAIL] {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error