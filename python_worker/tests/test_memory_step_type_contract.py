# -*- coding: utf-8 -*-
"""回归契约：Worker 动态执行链 → Prisma StepType 归一化（FAIL-SAFE）。

真实故障（2026-11-14 端到端跟测发现）：
  IntentRouter 的 architecture 执行链固定为
    analyze → workspace → plan → setup → write → refine → doc
  其中 workspace / setup 不在 Prisma StepType 枚举内。旧版
  memoryService.createTaskStep() 直接把 Worker 步骤名透传给 Prisma，
  于是「每一个架构任务」都会抛 PrismaClientValidationError：
    Invalid value for argument `step_type`. Expected StepType.
  上层 catch 只打一行告警，记忆库静默丢失步骤记录，异常堆栈还把
  Node 日志刷到数 MB。这不是偶发，是 100% 必现的本体缺陷。

修复位置：node-api/services/memoryService.js
  - 写入层白名单归一化，DB 枚举不跟随 Worker 步骤名演化
  - 未知值按 analyze 兜底，原始步骤名写入 input._original_step_type 可追溯
  - 步骤状态 / FileOp.op / FileOp.role 同样做 FAIL-SAFE 归一化

本契约同时锁死「schema.prisma 枚举 ↔ 代码白名单」不漂移。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MEMORY_SERVICE = _ROOT / "node-api" / "services" / "memoryService.js"
_SCHEMA = _ROOT / "node-api" / "prisma" / "schema.prisma"

# 架构意图真实执行链（来自 IntentRouter，取证自 2026-11-14 分类探针）
ARCHITECTURE_CHAIN = [
    "analyze", "workspace", "plan", "setup", "write", "refine", "doc",
]


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    if not shutil.which("node"):
        pytest.skip("未安装 node，跳过 Node 记忆层归一化契约")
    if not _MEMORY_SERVICE.exists() or not _SCHEMA.exists():
        pytest.skip("Node 记忆层源码不存在，跳过契约")


def _node_eval(body: str):
    """在真实 node 进程里跑归一化函数，返回它写到 stdout 的 JSON。

    屏蔽 console.log / console.warn，避免归一化告警污染 JSON 输出。
    """
    prelude = (
        "const _log = console.log, _warn = console.warn;\n"
        "console.log = () => {}; console.warn = () => {};\n"
        f"const m = require({json.dumps(_MEMORY_SERVICE.as_posix())});\n"
    )
    proc = subprocess.run(
        ["node", "-e", prelude + body],
        cwd=str(_ROOT / "node-api"),
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"node 执行失败: {proc.stderr}"
    return json.loads(proc.stdout.strip())


def _prisma_step_types() -> set:
    text = _SCHEMA.read_text(encoding="utf-8")
    block = re.search(r"enum\s+StepType\s*\{([^}]*)\}", text, re.S)
    assert block, "schema.prisma 中找不到 StepType 枚举"
    return {x.strip() for x in block.group(1).split() if x.strip()}


def test_normalizer_whitelist_matches_prisma_enum():
    """代码白名单必须与数据库枚举完全一致，防止单边改动造成漂移。"""
    whitelist = set(_node_eval(
        "process.stdout.write(JSON.stringify([...m.PRISMA_STEP_TYPES]));"
    ))
    assert whitelist == _prisma_step_types()


def test_architecture_chain_never_produces_invalid_step_type():
    """整条架构链的每个步骤都必须能落到合法枚举，且保留原始名。"""
    mapped = _node_eval(
        f"const raw = {json.dumps(ARCHITECTURE_CHAIN)};\n"
        "const out = raw.map(v => m._normalizeStepType(v, {prompt:'x'}));\n"
        "process.stdout.write(JSON.stringify(out));"
    )
    legal = _prisma_step_types()
    assert len(mapped) == len(ARCHITECTURE_CHAIN)
    for item in mapped:
        assert item["stepType"] in legal

    # 触发历史故障的两个步骤：语义等价映射 + 原始值可追溯
    assert mapped[1]["stepType"] == "analyze"
    assert mapped[1]["input"]["_original_step_type"] == "workspace"
    assert mapped[3]["stepType"] == "plan"
    assert mapped[3]["input"]["_original_step_type"] == "setup"

    # 本来就合法的步骤不得被改写、不得被塞入追溯字段
    assert mapped[0]["stepType"] == "analyze"
    assert "_original_step_type" not in mapped[0]["input"]
    assert mapped[4]["stepType"] == "write"


def test_unknown_step_type_is_fail_safe_and_traceable():
    """Worker 将来新增步骤名时，记忆库要能落库而不是抛异常。"""
    out = _node_eval(
        "const r = m._normalizeStepType('future_new_step', {prompt:'x'});\n"
        "process.stdout.write(JSON.stringify(r));"
    )
    assert out["stepType"] in _prisma_step_types()
    assert out["input"]["_original_step_type"] == "future_new_step"
    assert out["input"]["prompt"] == "x"  # 原始 input 不得丢失


def test_unknown_status_does_not_throw():
    """Worker 侧未知状态按 pending 落库，不再让整条记录链路崩掉。"""
    out = _node_eval(
        "process.stdout.write(JSON.stringify(["
        "m._normalizeStepStatus('completed'),"
        "m._normalizeStepStatus('failed'),"
        "m._normalizeStepStatus('unknown'),"
        "m._normalizeStepStatus(null)]));"
    )
    assert out == ["done", "failed", "pending", "pending"]


def test_file_op_and_role_are_normalized():
    out = _node_eval(
        "process.stdout.write(JSON.stringify(["
        "m._normalizeFileOp('remove'), m._normalizeFileOp('create'),"
        "m._normalizeFileOp('weird'),"
        "m._normalizeFileRole('config'), m._normalizeFileRole(null),"
        "m._normalizeFileRole('nope')]));"
    )
    assert out == ["delete", "create", "create", "config", None, "main"]


def test_create_task_step_uses_normalized_value():
    """静态锁死写入层不再透传原始步骤名。"""
    src = _MEMORY_SERVICE.read_text(encoding="utf-8")
    fn = src.split("async function createTaskStep", 1)[1].split(
        "async function", 1
    )[0]
    assert "_normalizeStepType(stepType, input)" in fn
    assert "step_type: prismaStepType" in fn
    assert "step_type: stepType" not in fn
