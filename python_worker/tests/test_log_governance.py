# -*- coding: utf-8 -*-
"""日志治理回归契约：防止 Worker / Node 再次把完整结果倾泻到 stdout。

真实故障（2026-11-14）：单行 509,268 字符、Worker 单轮日志 6.2MB、
Node 日志 11MB。完整 prompt、记忆上下文、生成源码被无差别写进日志，
拖慢管道、淹没信号。本契约锁死「默认摘要 + 硬上界 + 完整数据不丢」。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import log_governance as lg  # noqa: E402


def _huge_result():
    """模拟一轮真实任务结果：多个步骤，每步带完整 prompt / 生成源码。"""
    return {
        "version": "2.0",
        "task_id": "task-1234",
        "status": "awaiting_authorization",
        "task_state": "WAITING_AUTHORIZATION",
        "result": "## 架构文档\n" + "# 段落\n" * 20000,
        "steps": [
            {
                "type": "write",
                "id": f"step-{i}",
                "input": {"prompt": "用户请求 + 记忆上下文 " * 5000},
                "text": "# FILE: backend/models/order.py\n" + "x = 1\n" * 30000,
                "code": "from sqlalchemy import Column\n" * 20000,
            }
            for i in range(8)
        ],
        "final_file_ops": [
            {"op": "create", "path": f"backend/models/m{i}.py",
             "content": "print('hi')\n" * 10000}
            for i in range(12)
        ],
    }


def test_summarize_has_hard_upper_bound_on_huge_payload():
    huge = _huge_result()
    raw_len = len(json.dumps(huge, ensure_ascii=False))
    out = lg.summarize(huge)
    assert raw_len > 500_000, "测试数据本身必须足够大才有意义"
    assert len(out) <= lg.MAX_TOTAL_CHARS, len(out)
    assert len(out) < raw_len / 50, "摘要必须显著小于原始 payload"


def test_summarize_never_leaks_full_prompt_or_source():
    out = lg.summarize(_huge_result())
    # 允许 120 字符首部预览，但绝不允许整段 prompt / 源码落盘
    assert "用户请求 + 记忆上下文 " * 30 not in out
    assert "x = 1\nx = 1\n" * 20 not in out
    assert "已截断" in out or '"len"' in out


def test_summarize_keeps_identity_and_status_fields():
    out = lg.summarize(_huge_result())
    for token in ("task-1234", "awaiting_authorization",
                  "WAITING_AUTHORIZATION", "2.0"):
        assert token in out, token


def test_summarize_is_safe_on_unserializable_input():
    out = lg.summarize({"x": object(), "nested": {"fn": lambda: 1}})
    assert isinstance(out, str)
    assert len(out) <= lg.MAX_TOTAL_CHARS


def test_log_task_default_is_summary_mode(capsys, monkeypatch):
    monkeypatch.delenv("ALPHAPILOT_VERBOSE_LOG", raising=False)
    lg.log_task("测试标签", _huge_result())
    out = capsys.readouterr().out
    assert len(out) <= lg.MAX_TOTAL_CHARS + 500, len(out)
    assert max(len(line) for line in out.splitlines()) <= lg.MAX_LINE_CHARS + 300
    assert "摘要模式" in out


def test_log_task_verbose_mode_is_also_bounded(capsys, monkeypatch):
    monkeypatch.setenv("ALPHAPILOT_VERBOSE_LOG", "1")
    lg.log_task("测试标签", _huge_result())
    out = capsys.readouterr().out
    assert "VERBOSE 模式" in out
    assert len(out) <= lg.MAX_TOTAL_CHARS + 500, len(out)


def test_log_line_enforces_single_line_cap():
    assert len(lg.log_line("A" * 10_000)) <= lg.MAX_LINE_CHARS + 40


def test_worker_no_longer_calls_pretty_print_for_task_results():
    """生产 Worker 不得再用 pretty_print 全量打印任务/结果。"""
    src = (_PROJECT_ROOT / "python_worker" / "agents" / "qwen" /
           "qwen_worker_v2.py").read_text(encoding="utf-8")
    assert "print(TaskModel.pretty_print(" not in src
    assert "log_task(" in src
    assert "log_governance" in src


def test_node_side_no_full_stringify_dump():
    node_dir = _PROJECT_ROOT / "node-api"
    for rel in ("index.js", "router/v4Router.js"):
        src = (node_dir / rel).read_text(encoding="utf-8")
        assert "console.log(JSON.stringify" not in src, rel
    assert "logGovernance" in (node_dir / "index.js").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_node_summarize_bounded_and_keeps_identity():
    """Node 侧摘要模块与 Python 侧对齐：硬上界 + 保留身份字段。"""
    script = r"""
const { summarize, MAX_TOTAL_CHARS } = require(process.argv[1]);
const huge = {
  task_id: 'task-1234', status: 'completed', task_state: 'COMPLETED',
  result: 'A'.repeat(300000),
  steps: Array.from({length: 8}, (_, i) => ({
    type: 'write', id: 'step-' + i,
    input: {prompt: '记忆上下文 '.repeat(5000)},
    text: 'source code\n'.repeat(30000)
  }))
};
const out = summarize(huge);
console.log(JSON.stringify({
  len: out.length,
  bound: MAX_TOTAL_CHARS,
  hasId: out.includes('task-1234'),
  hasStatus: out.includes('COMPLETED'),
  leaks: out.includes('A'.repeat(1000))
}));
"""
    module = _PROJECT_ROOT / "node-api" / "logGovernance.js"
    r = subprocess.run(["node", "-e", script, str(module)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout.strip())
    assert data["len"] <= data["bound"]
    assert data["hasId"] and data["hasStatus"]
    assert not data["leaks"], "整段大文本不得落盘（仅允许短预览）"
