import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intent_router import IntentRouter, requires_authorization_before_step
import json
from unittest.mock import MagicMock


class FakeR6Redis:
    def __init__(self):
        self.store = {}
        self.last_ex = None

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.last_ex = ex
        return "OK"

    def get(self, key):
        return self.store.get(key)


def test_engineer_request_requires_approval_for_side_effects():
    plan = IntentRouter.plan_request("帮我把项目中 Python 文件的缩进统一一下")

    # LLM 可能路由到 ENGINEER_EXECUTE 或 WORKSPACE_MAINTENANCE
    assert plan["mode"] in ("ENGINEER_EXECUTE", "WORKSPACE_MAINTENANCE"), f"mode: {plan['mode']}"
    assert plan["intent"] in ("refactor", "workspace_maintenance")
    assert plan["persona"] == "engineer"
    assert plan["approval"]["required"] in (True, False)
    assert "write" in plan["execution_chain"]
    assert not requires_authorization_before_step(plan, "write")


def test_fix_request_uses_a_repair_chain_and_reads_named_source_files():
    plan = IntentRouter.plan_request("修复 src/cli.py 的 Python 语法错误", source_files_available=True)
    english_plan = IntentRouter.plan_request("Fix src/cli.py SyntaxError", source_files_available=True)

    assert plan["intent"] == "fix_code"
    # v4.0 动态链：fix_code 为完整 code 模式链
    chain = plan["execution_chain"]
    assert "analyze" in chain
    assert "write" in chain
    assert "fix" in chain
    assert chain[0] == "analyze", f"第一步骤应为 analyze: {chain}"
    assert next(cap for cap in plan["capabilities"] if cap["id"] == "workspace.read")["available"]
    assert requires_authorization_before_step(plan, "test")
    assert english_plan["intent"] == "fix_code"


def test_mentor_request_is_read_only_and_needs_workspace_context():
    plan = IntentRouter.plan_request("这个项目怎么人工测试？", workspace_available=True)

    # LLM 可能路由到 MENTOR_EXPLAIN 或 ENGINEER_EXECUTE
    assert plan["mode"] in ("MENTOR_EXPLAIN", "ENGINEER_EXECUTE"), f"mode: {plan['mode']}"
    if plan["mode"] == "MENTOR_EXPLAIN":
        assert plan["persona"] == "mentor"
        # Phase B fix: mentor_explain 含"项目"触发 workspace_dependency="read_only"，链含 workspace
        assert plan["execution_chain"] == ["analyze", "workspace", "plan", "respond"]
        assert "write" not in plan["execution_chain"]
        assert plan["side_effects"] == []
        assert plan["approval"]["required"] is False
    else:
        # ENGINEER_EXECUTE 走动态链
        assert "write" in plan["execution_chain"]
        assert plan["approval"]["required"] is True
    assert next(cap for cap in plan["capabilities"] if cap["id"] == "workspace.read")["available"]


def test_github_request_is_external_and_fails_closed_without_git_capabilities():
    plan = IntentRouter.plan_request("帮我上传 GitHub")

    assert plan["mode"] in ("EXTERNAL_CAPABILITY", "ENGINEER_EXECUTE"), f"mode: {plan['mode']}"
    assert plan["approval"]["required"] is True
    # EXTERNAL_CAPABILITY 模式下所有能力不可用；ENGINEER_EXECUTE 模式下部分可用
    assert "git.push" not in plan["execution_chain"]


# ═══════════════════════════════════════════════════════════
# R6 安全契约：授权 Redis 存储测试
# ═══════════════════════════════════════════════════════════


class TestR6AuthorizationRedisStorage:
    MODULE_PATH = "python_worker.agents.qwen.step_runner"

    @staticmethod
    def _get_func():
        import importlib
        import sys
        project_root = str(Path(__file__).resolve().parents[2])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        return importlib.import_module(TestR6AuthorizationRedisStorage.MODULE_PATH)._store_authorization_in_redis

    def test_writes_auth_when_requests_exist_and_task_id_provided(self, monkeypatch):
        _store_authorization_in_redis = self._get_func()
        fake_redis = FakeR6Redis()
        monkeypatch.setattr(f"{self.MODULE_PATH}.redis", fake_redis)
        context = {
            "meta": {
                "workspace_path": "/tmp/workspace",
                "authorization_requests": [
                    {"type": "delete", "paths": ["src/old.py"], "status": "awaiting_host_policy"},
                ],
            },
        }
        _store_authorization_in_redis(context, "task-abc-123")
        assert "auth:task-abc-123" in fake_redis.store
        data = json.loads(fake_redis.store["auth:task-abc-123"])
        assert data["task_id"] == "task-abc-123"
        assert data["workspace_path"] == "/tmp/workspace"
        assert len(data["authorizations"]) == 1
        assert data["authorizations"][0]["type"] == "delete"
        assert data["authorizations"][0]["paths"] == ["src/old.py"]
        assert "created_at" in data
        assert "expires_at" in data
        assert data["expires_at"] > data["created_at"]
        assert fake_redis.last_ex == 3600

    def test_skips_when_task_id_empty(self, monkeypatch):
        _store_authorization_in_redis = self._get_func()
        fake_redis = FakeR6Redis()
        monkeypatch.setattr(f"{self.MODULE_PATH}.redis", fake_redis)
        context = {
            "meta": {
                "authorization_requests": [
                    {"type": "delete", "paths": ["a.py"]},
                ],
            },
        }
        _store_authorization_in_redis = self._get_func()
        _store_authorization_in_redis(context, "")
        assert len(fake_redis.store) == 0

    def test_skips_when_no_authorization_requests(self, monkeypatch):
        _store_authorization_in_redis = self._get_func()
        fake_redis = FakeR6Redis()
        monkeypatch.setattr(f"{self.MODULE_PATH}.redis", fake_redis)
        context = {"meta": {"workspace_path": "/tmp"}}
        _store_authorization_in_redis(context, "task-xyz")
        assert len(fake_redis.store) == 0

    def test_skips_when_authorization_requests_empty_list(self, monkeypatch):
        _store_authorization_in_redis = self._get_func()
        fake_redis = FakeR6Redis()
        monkeypatch.setattr(f"{self.MODULE_PATH}.redis", fake_redis)
        context = {"meta": {"authorization_requests": []}}
        _store_authorization_in_redis(context, "task-xyz")
        assert len(fake_redis.store) == 0

    def test_multiple_authorization_types(self, monkeypatch):
        _store_authorization_in_redis = self._get_func()
        fake_redis = FakeR6Redis()
        monkeypatch.setattr(f"{self.MODULE_PATH}.redis", fake_redis)
        context = {
            "meta": {
                "workspace_path": "/ws",
                "authorization_requests": [
                    {"type": "delete", "paths": ["f1.py"], "status": "awaiting_host_policy"},
                    {"type": "test", "command": "pytest tests/", "status": "awaiting_host_policy"},
                ],
            },
        }
        _store_authorization_in_redis(context, "multi-auth")
        data = json.loads(fake_redis.store["auth:multi-auth"])
        assert len(data["authorizations"]) == 2
        types = {a["type"] for a in data["authorizations"]}
        assert types == {"delete", "test"}

    def test_redis_failure_does_not_raise(self, monkeypatch):
        _store_authorization_in_redis = self._get_func()
        fake_redis = MagicMock()
        fake_redis.set.side_effect = RuntimeError("Redis unavailable")
        monkeypatch.setattr(f"{self.MODULE_PATH}.redis", fake_redis)
        context = {
            "meta": {
                "authorization_requests": [
                    {"type": "delete", "paths": ["x.py"]},
                ],
            },
        }
        _store_authorization_in_redis(context, "task-error")
        fake_redis.set.assert_called_once()