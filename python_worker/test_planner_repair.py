# -*- coding: utf-8 -*-
import re
import json
import python_worker.planner as planner


class _FakeResp:
    def __init__(self, raw_text):
        self._raw = raw_text

    def raise_for_status(self):
        return None

    def json(self):
        return {"output": {"text": self._raw}}


def _make_post(raw_text):
    def _post(url, headers=None, json=None, timeout=None):
        return _FakeResp(raw_text)

    return _post


def _run_and_assert(monkeypatch, raw_text):
    # patch requests.post used in planner
    monkeypatch.setattr(planner.requests, 'post', _make_post(raw_text))

    steps = planner.llm_decompose_task("写一个函数，计算两个数的和")

    assert isinstance(steps, list)
    assert len(steps) >= 1
    for s in steps:
        assert isinstance(s, dict)
        assert 'id' in s and 'type' in s and 'input' in s


def test_repair_extra_brace(monkeypatch):
    # 原始日志中的典型错误：多出的右大括号导致 JSON 解析失败
    raw = '[{"id":"step-1","type":"analyze","input":{"prompt":"写一个函数，计算两个数的和"}},{"id":"step-2","type":"plan","input":{"prompt":"确定函数的参数和返回值类型，以及如何处理输入数据"}}},{"id":"step-3","type":"write","input":{"prompt":"编写函数代码，实现两个数的相加功能"}}]'
    _run_and_assert(monkeypatch, raw)


def test_repair_missing_comma_between_objects(monkeypatch):
    # 缺少对象之间的逗号：}{ -> }, {
    raw = '[{"id":"step-1","type":"analyze","input":{"prompt":"p1"}}{"id":"step-2","type":"plan","input":{"prompt":"p2"}},{"id":"step-3","type":"write","input":{"prompt":"p3"}}]'
    _run_and_assert(monkeypatch, raw)


def test_repair_single_quotes_and_trailing_commas(monkeypatch):
    # 使用单引号并带有尾随逗号
    raw = "[{'id':'step-1','type':'analyze','input':{'prompt':'p1'},},{'id':'step-2','type':'plan','input':{'prompt':'p2'}}]"
    _run_and_assert(monkeypatch, raw)
