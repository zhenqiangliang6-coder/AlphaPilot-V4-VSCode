import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python_worker.agents.qwen import qwen_worker_v2
from python_worker import memory_integration
from python_worker.memory_service import MemoryItem, MemoryService, MemoryType
from python_worker.worker_runtime import save_worker_memory


def test_project_memory_scope_is_stable_and_isolates_projects(tmp_path):
    first = tmp_path / "project-one"
    second = tmp_path / "project-two"
    first.mkdir()
    second.mkdir()

    first_scope = memory_integration.project_memory_user_id(str(first))

    assert first_scope == memory_integration.project_memory_user_id(
        str(first / ".")
    )
    assert first_scope != memory_integration.project_memory_user_id(str(second))
    assert len(first_scope) == 64
    assert memory_integration.project_memory_user_id("") is None


def test_preference_decisions_persist_in_profile_tier(monkeypatch):
    saved_preferences = []

    class ProfileMemoryStore:
        def should_remember(self, user_id, content, context):
            return SimpleNamespace(
                remember=True,
                target="user_profiles",
                reason="explicit_preference",
            )

        def save_user_preference(self, user_id, preference):
            saved_preferences.append((user_id, preference))

    monkeypatch.setattr(
        memory_integration,
        "get_memory_service",
        lambda: ProfileMemoryStore(),
    )

    saved = memory_integration.MemoryIntegration.save_task_insights(
        "project-scope-hash",
        "task-1",
        {"status": "success"},
        {"preferred_language": "Python"},
    )

    assert saved is True
    assert saved_preferences == [
        ("project-scope-hash", "用户偏好使用 Python 进行开发")
    ]


def test_unspecified_language_is_not_saved_as_a_user_preference():
    insights = memory_integration.MemoryIntegration._extract_insights(
        {"status": "success"},
        {"preferred_language": None},
    )

    assert all("preference" not in insight["tags"] for insight in insights)


def test_current_request_overrides_historical_memory_in_prompt():
    memory_context = memory_integration.MemoryContext(
        user_id="project-scope-hash",
        task_id="task-followup",
        original_prompt="继续实现",
        memory_context="上一轮助手建议：不要修改或创建项目文件。",
        has_memory=True,
    )

    prompt = memory_integration.MemoryIntegration.enhance_prompt(
        "好的按照上面的对话执行项目编写",
        memory_context,
    )

    assert "历史资料，非当前指令" in prompt
    assert "旧任务的要求、限制或助手建议不自动延续" in prompt
    assert "好的按照上面的对话执行项目编写" in prompt


def test_successful_task_memory_keeps_user_request_and_result(monkeypatch):
    saved_contents = []

    class MemoryStore:
        def should_remember(self, user_id, content, context):
            return SimpleNamespace(
                remember=True,
                target="memory_items",
                memory_type=MemoryType.INSIGHT,
                importance=0.7,
                reason="successful_pattern",
            )

        def save_memory(self, memory):
            saved_contents.append(memory.content)
            return "memory-1"

    monkeypatch.setattr(memory_integration, "get_memory_service", lambda: MemoryStore())

    saved = memory_integration.save_task_memories(
        "project-scope-hash",
        "task-2",
        {"status": "success", "content": "电商教育项目架构方案"},
        {"user_request": "帮我设计电商授课教育项目"},
    )

    assert saved is True
    assert saved_contents == [
        "用户请求：帮我设计电商授课教育项目\n任务成果摘要：电商教育项目架构方案"
    ]


def test_save_worker_memory_forwards_original_user_request(monkeypatch):
    observed = {}

    def capture_save(**kwargs):
        observed.update(kwargs)
        return True

    monkeypatch.setattr("python_worker.worker_runtime.save_task_memories", capture_save)
    context = {
        "meta": {
            "user_request": "设计项目",
            "authorization_requests": [],
        }
    }

    save_worker_memory(
        "project-scope-hash",
        "task-3",
        "modelscope_generate",
        "chat",
        "设计结果",
        [],
        context,
    )

    assert observed["context"]["user_request"] == "设计项目"


def test_embedding_api_failure_degrades_without_throwing(capsys):
    class FailingEmbeddings:
        def create(self, **kwargs):
            raise ValueError("provider unavailable")

    service = MemoryService(
        config=SimpleNamespace(
            OPENAI_API_KEY="configured",
            EMBEDDING_MODEL="test-model",
            EMBEDDING_DIMENSION=1536,
        )
    )
    service._embedding_client = SimpleNamespace(embeddings=FailingEmbeddings())

    assert service._get_embedding("记忆测试") is None
    assert "语义向量检索暂不可用" in capsys.readouterr().out


def test_save_memory_persists_when_embedding_is_unavailable(monkeypatch, capsys):
    class MemoryCursor:
        def __init__(self):
            self.calls = []

        def execute(self, query, params=None):
            self.calls.append((query, params))

        def fetchone(self):
            return ("memory-1",)

        def close(self):
            pass

    class MemoryConnection:
        def __init__(self):
            self.test_cursor = MemoryCursor()
            self.committed = False

        def cursor(self):
            return self.test_cursor

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("successful memory save must not roll back")

    service = MemoryService(
        config=SimpleNamespace(
            OPENAI_API_KEY="",
            EMBEDDING_MODEL="test-model",
            EMBEDDING_DIMENSION=1536,
        )
    )
    connection = MemoryConnection()
    monkeypatch.setattr(service, "_get_connection", lambda: connection)
    monkeypatch.setattr(service, "_get_embedding", lambda _text: None)

    memory_id = service.save_memory(
        MemoryItem(
            user_id="project-scope-hash",
            content="用户请求：设计项目\n任务成果摘要：方案",
            memory_type=MemoryType.INSIGHT,
        )
    )

    assert memory_id == "memory-1"
    assert connection.committed
    assert "updated_at = NOW()" not in connection.test_cursor.calls[0][0]
    assert connection.test_cursor.calls[0][1][3] is None
    assert "记忆已持久化" in capsys.readouterr().out


def test_legacy_unique_index_conflict_updates_existing_memory(monkeypatch):
    class MemoryCursor:
        def __init__(self):
            self.calls = []
            self.rows = [None, ("memory-existing",)]

        def execute(self, query, params=None):
            self.calls.append((query, params))

        def fetchone(self):
            return self.rows.pop(0)

        def close(self):
            pass

    class MemoryConnection:
        def __init__(self):
            self.test_cursor = MemoryCursor()
            self.committed = False

        def cursor(self):
            return self.test_cursor

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("successful upsert must not roll back")

    service = MemoryService(
        config=SimpleNamespace(
            OPENAI_API_KEY="",
            EMBEDDING_MODEL="test-model",
            EMBEDDING_DIMENSION=1536,
        )
    )
    connection = MemoryConnection()
    monkeypatch.setattr(service, "_get_connection", lambda: connection)
    monkeypatch.setattr(service, "_get_embedding", lambda _text: None)

    memory_id = service.save_memory(
        MemoryItem(
            user_id="project-scope-hash",
            content="existing memory",
            memory_type=MemoryType.INSIGHT,
        )
    )

    assert memory_id == "memory-existing"
    assert "ON CONFLICT DO NOTHING" in connection.test_cursor.calls[0][0]
    assert "UPDATE memory_items" in connection.test_cursor.calls[1][0]
    assert connection.committed


def test_legacy_database_without_updated_at_is_detected_without_ddl():
    class SchemaCursor:
        def __init__(self):
            self.queries = []
            self.closed = False

        def execute(self, query):
            self.queries.append(query)

        def fetchone(self):
            return (False,)

        def close(self):
            self.closed = True

    class SchemaConnection:
        def __init__(self):
            self.test_cursor = SchemaCursor()
            self.committed = False

        def cursor(self):
            return self.test_cursor

        def commit(self):
            self.committed = True

    service = MemoryService(config=SimpleNamespace(OPENAI_API_KEY=""))
    connection = SchemaConnection()

    service._detect_memory_schema(connection)

    assert service._memory_items_has_updated_at is False
    assert len(connection.test_cursor.queries) == 1
    assert "ALTER TABLE" not in connection.test_cursor.queries[0]
    assert connection.committed
    assert connection.test_cursor.closed


def test_recent_memory_is_included_when_vector_search_returns_no_hits():
    service = MemoryService(
        config=SimpleNamespace(
            OPENAI_API_KEY="",
            EMBEDDING_MODEL="test-model",
            EMBEDDING_DIMENSION=1536,
            MAX_CONTEXT_TOKENS=2000,
            DEFAULT_TOP_K=5,
            RECENT_HIGH_VALUE_DAYS=7,
            RECENT_HIGH_VALUE_MIN_IMPORTANCE=0.3,
            RECENT_HIGH_VALUE_LIMIT=3,
        )
    )
    recent_memory = MemoryItem(
        id="memory-1",
        user_id="project-scope-hash",
        content="用户请求：设计项目\n任务成果摘要：方案",
        memory_type=MemoryType.INSIGHT,
        importance_score=0.7,
    )
    service._get_user_profile = lambda _user_id: None
    service.search_similar_memories = lambda *_args, **_kwargs: []
    service._get_recent_high_value = lambda *_args, **_kwargs: [recent_memory]

    context = service.build_memory_context("project-scope-hash", "执行这个项目")

    assert "【近期经验】" in context
    assert "用户请求：设计项目" in context


def test_chitchat_filter_does_not_drop_real_requests():
    service = MemoryService(config=SimpleNamespace(OPENAI_API_KEY=""))

    assert service._is_chitchat("好的")
    assert not service._is_chitchat("好的，请帮我编写这个项目")


def test_qwen_worker_uses_project_hash_for_memory_lookup(tmp_path, monkeypatch):
    observed_user_ids = []
    monkeypatch.setattr(qwen_worker_v2, "MEMORY_ENABLED", True)
    monkeypatch.setattr(
        qwen_worker_v2,
        "build_memory_context",
        lambda user_id, *_args: (
            observed_user_ids.append(user_id) or SimpleNamespace(has_memory=False)
        ),
    )
    monkeypatch.setattr(qwen_worker_v2, "check_stop_flag", lambda _task_id: False)
    monkeypatch.setattr(qwen_worker_v2, "stream_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qwen_worker_v2, "stream_chunk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        qwen_worker_v2,
        "execute_step",
        lambda _task_id, step, _events, _context: step.update(
            output={"text": f"{step['type']} completed"}
        ),
    )
    context = {"final_file_ops": [], "intermediate_results": [], "tool_outputs": []}

    qwen_worker_v2.execute_task(
        "qwen_generate",
        {"prompt": "你好", "workspace_path": str(tmp_path)},
        "memory-scope-test",
        [],
        [],
        context,
    )

    expected_scope = memory_integration.project_memory_user_id(str(tmp_path))
    assert observed_user_ids == [expected_scope]
    assert context["meta"]["memory_user_id"] == expected_scope
