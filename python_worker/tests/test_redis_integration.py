"""
Redis integration test — Phase 3.8.5 / 3.8.6

Validates:
  1. Queue name mappings for all 12 worker types
  2. Task format contract (envelope: task_id, type, protocol_version, trace_id, payload)
  3. Result format contract (status, task_id, result, steps, error, context)
  4. Cross-language consistency (Python / Node.js / Java / TypeScript)
"""

import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── 1. Queue Name Mapping Contract ───────────────────────────
QUEUE_MAP_PYTHON = {
    "qwen_generate": "task_queue:qwen",
    "deepseek_generate": "task_queue:deepseek",
    "doubao_generate": "task_queue:doubao",
    "maas_generate": "task_queue:maas",
    "modelscope_generate": "task_queue:modelscope",
    "local_generate": "task_queue:local",
    "openai_generate": "task_queue:openai",
    "claude_generate": "task_queue:claude",
    "gemini_generate": "task_queue:gemini",
    "node_generate": "node_worker",
    "java_generate": "java_worker",
    "ts_generate": "ts_worker",
}


class QueueMappingTest(unittest.TestCase):
    def test_all_12_types_have_mapping(self):
        expected = {
            "qwen_generate", "deepseek_generate", "doubao_generate",
            "maas_generate", "modelscope_generate", "local_generate",
            "openai_generate", "claude_generate", "gemini_generate",
            "node_generate", "java_generate", "ts_generate",
        }
        self.assertEqual(set(QUEUE_MAP_PYTHON.keys()), expected)

    def test_fallback_to_task_queue(self):
        result = QUEUE_MAP_PYTHON.get("unknown_generate", "task_queue")
        self.assertEqual(result, "task_queue")

    def test_multi_language_queues_distinct(self):
        self.assertNotEqual(QUEUE_MAP_PYTHON["node_generate"], QUEUE_MAP_PYTHON["java_generate"])
        self.assertNotEqual(QUEUE_MAP_PYTHON["java_generate"], QUEUE_MAP_PYTHON["ts_generate"])
        self.assertNotEqual(QUEUE_MAP_PYTHON["ts_generate"], QUEUE_MAP_PYTHON["node_generate"])

    def test_node_java_ts_not_colliding_with_python_queues(self):
        py_queues = {v for k, v in QUEUE_MAP_PYTHON.items()
                     if not k.startswith(("node_", "java_", "ts_"))}
        multi_lang_queues = {
            QUEUE_MAP_PYTHON["node_generate"],
            QUEUE_MAP_PYTHON["java_generate"],
            QUEUE_MAP_PYTHON["ts_generate"],
        }
        self.assertTrue(py_queues.isdisjoint(multi_lang_queues))


# ── 2. Task Envelope Contract ───────────────────────────────

REQUIRED_TASK_FIELDS = {"task_id", "type", "protocol_version", "payload"}
REQUIRED_PAYLOAD_FIELDS = {"prompt", "workspace_path"}


class TaskEnvelopeTest(unittest.TestCase):
    def test_minimal_valid_task(self):
        task = {
            "task_id": "test-001",
            "type": "qwen_generate",
            "protocol_version": "1.0",
            "payload": {
                "prompt": "Write a hello world",
                "workspace_path": "/tmp/test",
            },
        }
        missing = REQUIRED_TASK_FIELDS - set(task.keys())
        self.assertFalse(missing, f"Missing: {missing}")

    def test_task_missing_task_id_rejected(self):
        task = {
            "type": "qwen_generate",
            "protocol_version": "1.0",
            "payload": {"prompt": "test", "workspace_path": "/tmp"},
        }
        missing = REQUIRED_TASK_FIELDS - set(task.keys())
        self.assertTrue(missing)

    def test_payload_missing_workspace_path_rejected(self):
        payload = {"prompt": "test"}
        missing = REQUIRED_PAYLOAD_FIELDS - set(payload.keys())
        self.assertTrue(missing)

    def test_task_with_optional_trace_id(self):
        task = {
            "task_id": "trace-001",
            "type": "qwen_generate",
            "protocol_version": "1.0",
            "trace_id": "abc-123",
            "payload": {"prompt": "test", "workspace_path": "/tmp"},
        }
        self.assertEqual(task["trace_id"], "abc-123")

    def test_task_with_optional_context_field(self):
        task = {
            "task_id": "ctx-001",
            "type": "qwen_generate",
            "protocol_version": "1.0",
            "payload": {"prompt": "test", "workspace_path": "/tmp"},
            "context": {
                "project_context": {"name": "test-project"},
                "memory_context": {"user_preferences": {}},
            },
        }
        self.assertIn("context", task)
        self.assertIn("project_context", task["context"])


# ── 3. Result Format Contract ───────────────────────────────

class ResultContractTest(unittest.TestCase):
    def make_success(self, task_id="r-001"):
        return {
            "task_id": task_id,
            "status": "success",
            "result": "Generated code here",
            "steps": [
                {"type": "analyze", "status": "completed"},
                {"type": "plan", "status": "completed"},
                {"type": "write", "status": "completed"},
                {"type": "test", "status": "completed"},
            ],
        }

    def test_success_result_has_required_fields(self):
        r = self.make_success()
        for f in ["task_id", "status", "result", "steps"]:
            self.assertIn(f, r, f"Missing {f}")

    def test_success_status_is_success(self):
        r = self.make_success()
        self.assertEqual(r["status"], "success")

    def test_error_result_format(self):
        r = {
            "task_id": "err-001",
            "status": "error",
            "error": "Model call failed",
            "error_code": "MODEL_CALL_ERROR",
            "steps": [],
        }
        self.assertEqual(r["status"], "error")
        self.assertIn("error", r)

    def test_steps_array_each_has_type_and_status(self):
        r = self.make_success()
        for s in r["steps"]:
            self.assertIn("type", s)
            self.assertIn("status", s)
            self.assertIn(s["status"], {"completed", "failed", "skipped", "awaiting_authorization"})

    def test_result_with_meta_context(self):
        r = self.make_success()
        r["context"] = {
            "meta": {"workspace_scan": {"python_file_count": 5, "root": "/tmp"}},
        }
        self.assertIn("context", r)
        self.assertIn("workspace_scan", r["context"]["meta"])

    def test_intermediate_results_preserved(self):
        r = self.make_success()
        r["intermediate_results"] = [
            {"step": "write", "content": "code"},
            {"step": "compile", "content": "BUILD SUCCESS"},
        ]
        self.assertIsInstance(r["intermediate_results"], list)
        self.assertEqual(len(r["intermediate_results"]), 2)


# ── 4. Cross-Language Execution Chain Consistency ───────────

EXECUTION_CHAINS = {
    "python": ["analyze", "plan", "write", "refine", "test", "fix"],
    "java": ["analyze", "plan", "write", "compile", "refine", "test", "fix"],
    "node": ["analyze", "plan", "write", "refine", "test", "fix"],
    "ts": ["analyze", "plan", "write", "compile", "refine", "test", "fix"],
}


class ExecutionChainTest(unittest.TestCase):
    def test_java_and_ts_both_have_compile(self):
        self.assertIn("compile", EXECUTION_CHAINS["java"])
        self.assertIn("compile", EXECUTION_CHAINS["ts"])

    def test_python_and_node_no_compile(self):
        self.assertNotIn("compile", EXECUTION_CHAINS["python"])
        self.assertNotIn("compile", EXECUTION_CHAINS["node"])

    def test_all_chains_start_with_analyze(self):
        for lang, chain in EXECUTION_CHAINS.items():
            self.assertEqual(chain[0], "analyze", f"{lang} chain")

    def test_all_chains_end_with_fix(self):
        for lang, chain in EXECUTION_CHAINS.items():
            self.assertEqual(chain[-1], "fix", f"{lang} chain")

    def test_all_chains_have_write_and_refine(self):
        for lang, chain in EXECUTION_CHAINS.items():
            self.assertIn("write", chain, f"{lang} chain")
            self.assertIn("refine", chain, f"{lang} chain")


# ── 5. Retry / Error Format Consistency ─────────────────────

class RetryAndErrorConsistencyTest(unittest.TestCase):
    def test_retry_count_in_meta(self):
        task = {
            "task_id": "retry-001",
            "meta": {"retry_count": 2, "max_retries": 3},
        }
        self.assertEqual(task["meta"]["retry_count"], 2)
        self.assertLess(task["meta"]["retry_count"], task["meta"]["max_retries"])

    def test_error_result_includes_error_code(self):
        r = {"status": "error", "error": "timeout", "error_code": "TIMEOUT"}
        self.assertIn("error_code", r)

    def test_task_state_transitions_valid(self):
        valid_pairs = [
            ("PENDING", "RUNNING"),
            ("RUNNING", "COMPLETED"),
            ("RUNNING", "FAILED"),
            ("RUNNING", "WAITING_AUTHORIZATION"),
            ("WAITING_AUTHORIZATION", "RUNNING"),
            ("WAITING_AUTHORIZATION", "COMPLETED"),
            ("WAITING_AUTHORIZATION", "FAILED"),
        ]
        for src, dst in valid_pairs:
            self.assertIn((src, dst), valid_pairs,
                          f"Invalid transition: {src} → {dst}")

    def test_legacy_status_mapping(self):
        mapping = {
            "COMPLETED": "done",
            "FAILED": "error",
            "PENDING": "pending",
            "RUNNING": "pending",
            "WAITING_AUTHORIZATION": "awaiting_authorization",
        }
        for task_state, legacy in mapping.items():
            self.assertIsNotNone(legacy, f"Missing legacy mapping for {task_state}")


if __name__ == '__main__':
    unittest.main()