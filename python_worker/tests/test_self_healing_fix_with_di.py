"""
Unit tests for self-healing fix functionality with dependency injection.

Tests the enhanced fix_step that receives test code from test_step context
and uses dependency injection for better testability.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.step_executor import test_step, fix_step
from python_worker.agents.qwen.step_executor.prompts import fix_prompt
from python_worker.agents.qwen.step_executor.adapters import (
    MockLLMClient,
    MockCodeExecutor,
    MockFileOpsParser,
    MockPythonCompiler
)


# =============================================================================
# Test 1: test_step with dependency injection
# =============================================================================

def test_test_step_with_mock_llm_and_executor():
    """
    Verify that test_step works with injected mock dependencies.
    This tests the dependency injection mechanism itself.
    """
    # Create mock dependencies
    mock_llm = MockLLMClient(response="```python\ndef test_example():\n    assert True\n```")
    mock_executor = MockCodeExecutor(result={
        "stdout": "",
        "stderr": "",
        "error": None,
        "exception": None
    })
    
    context = {
        "intermediate_results": [
            {
                "type": "write",
                "text": "```python\nclass Example:\n    pass\n```"
            }
        ]
    }
    step = {}
    
    # Run with injected dependencies (no task_id, so uses non-streaming call)
    test_step.run_test_step(
        step,
        context,
        [],
        task_id=None,  # No task_id, use non-streaming call
        llm_client=mock_llm,
        code_executor=mock_executor
    )
    
    # Verify mocks were called
    assert mock_llm.call_count == 1  # Non-streaming call
    assert mock_executor.execute_count == 1
    
    # Verify test code was saved to context
    test_entries = [item for item in context["intermediate_results"] if item.get("type") == "test"]
    assert len(test_entries) > 0
    assert "test_code" in test_entries[-1]


def test_test_step_with_mock_executor_failure():
    """
    Verify that test_step handles executor failure correctly.
    """
    mock_llm = MockLLMClient(response="```python\ndef test_example():\n    assert False\n```")
    mock_executor = MockCodeExecutor(result={
        "stdout": "",
        "stderr": "AssertionError",
        "error": "AssertionError",
        "exception": "AssertionError"
    })
    
    context = {
        "intermediate_results": [
            {
                "type": "write",
                "text": "```python\nclass Example:\n    pass\n```"
            }
        ]
    }
    step = {}
    
    test_step.run_test_step(
        step,
        context,
        [],
        task_id=None,
        llm_client=mock_llm,
        code_executor=mock_executor
    )
    
    # Verify test was marked as failed
    test_entries = [item for item in context["intermediate_results"] if item.get("type") == "test"]
    assert test_entries[-1]["status"] == "failed"


# =============================================================================
# Test 2: fix_step with dependency injection
# =============================================================================

def test_fix_step_with_mock_dependencies():
    """
    Verify that fix_step works with injected mock dependencies.
    """
    # Create mock dependencies
    mock_llm = MockLLMClient(
        response="# FILE: voting.py\n```python\nclass VotingSystem:\n    def get_vote_count(self):\n        return 5\n```"
    )
    mock_parser = MockFileOpsParser(file_ops=[
        {
            "path": "voting.py",
            "content": "class VotingSystem:\n    def get_vote_count(self):\n        return 5"
        }
    ])
    mock_compiler = MockPythonCompiler()
    
    context = {
        "intermediate_results": [
            {
                "type": "test",
                "test_code": "def test_get_vote_count():\n    assert get_vote_count() == 5",
                "status": "failed",
                "error": "AttributeError"
            }
        ],
        "final_file_ops": [
            {
                "path": "voting.py",
                "content": "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
            }
        ],
        "meta": {
            "intent": "fix_code",
            "source_files": {  # ⭐ 直接提供 source_files，避免从 final_file_ops 提取
                "voting.py": "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
            }
        }
    }
    step = {}
    
    fix_step.run_fix_step(
        step,
        context,
        [],
        llm_client=mock_llm,
        file_parser=mock_parser,
        python_compiler=mock_compiler
    )
    
    # Verify mocks were called
    assert mock_llm.call_count == 1
    assert mock_parser.parse_count == 1
    assert mock_compiler.compile_count == 1
    
    # Verify prompt contains test code
    assert "【测试代码】" in mock_llm.prompts[0]
    assert "get_vote_count" in mock_llm.prompts[0]


def test_fix_step_with_mock_compiler_failure():
    """
    Verify that fix_step handles compiler failure correctly.
    When the compiler raises SyntaxError, the LLM is still called but
    no fix file_ops are generated; errors are captured in intermediate_results.
    """
    mock_llm = MockLLMClient(response="# FILE: voting.py\n```python\ndef broken(:\n```")
    mock_parser = MockFileOpsParser(file_ops=[])
    mock_compiler = MockPythonCompiler(should_fail=True)
    
    context = {
        "intermediate_results": [
            {
                "type": "test",
                "test_code": "def test_example():\n    pass",
                "status": "failed",
                "error": "SyntaxError"
            }
        ],
        "final_file_ops": [],
        "meta": {
            "intent": "fix_code",
            "source_files": {
                "voting.py": "class VotingSystem:\n    pass"
            }
        }
    }
    step = {}
    
    fix_step.run_fix_step(
        step,
        context,
        [],
        llm_client=mock_llm,
        file_parser=mock_parser,
        python_compiler=mock_compiler
    )
    
    # Verify LLM was still called
    assert mock_llm.call_count == 1
    
    # Verify no fix file_ops were produced (compilation failed)
    fix_entries = [item for item in context["intermediate_results"] if item.get("type") == "fix"]
    assert len(fix_entries) > 0
    assert fix_entries[-1]["file_ops"] == []
    assert len(fix_entries[-1]["errors"]) > 0


# =============================================================================
# Test 3: Integration test with dependency injection
# =============================================================================

def test_full_integration_with_dependency_injection():
    """
    Test the complete flow: test_step -> context -> fix_step
    using dependency injection for both steps.
    """
    # Step 1: test_step with mocks
    test_llm = MockLLMClient(response="```python\ndef test_get_vote_count():\n    assert get_vote_count() == 5\n```")
    test_executor = MockCodeExecutor(result={
        "stdout": "",
        "stderr": "AttributeError",
        "error": "AttributeError: 'VotingSystem' object has no attribute 'get_vote_count'",
        "exception": "AttributeError"
    })
    
    context = {
        "intermediate_results": [
            {
                "type": "write",
                "text": "```python\nclass VotingSystem:\n    def get_candidate_votes(self):\n        return 5\n```"
            }
        ]
    }
    step = {}
    
    test_step.run_test_step(
        step,
        context,
        [],
        task_id=None,
        llm_client=test_llm,
        code_executor=test_executor
    )
    
    # Verify test code was saved
    test_entries = [item for item in context["intermediate_results"] if item.get("type") == "test"]
    assert len(test_entries) > 0
    assert "get_vote_count" in test_entries[-1]["test_code"]
    
    # Step 2: fix_step with mocks
    fix_llm = MockLLMClient(
        response="# FILE: voting.py\n```python\nclass VotingSystem:\n    def get_vote_count(self):\n        return 5\n```"
    )
    fix_parser = MockFileOpsParser(file_ops=[
        {
            "path": "voting.py",
            "content": "class VotingSystem:\n    def get_vote_count(self):\n        return 5"
        }
    ])
    fix_compiler = MockPythonCompiler()
    
    context["final_file_ops"] = [
        {
            "path": "voting.py",
            "content": "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
        }
    ]
    context["meta"] = {
        "intent": "fix_code",
        "source_files": {
            "voting.py": "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
        }
    }
    step = {}
    
    fix_step.run_fix_step(
        step,
        context,
        [],
        llm_client=fix_llm,
        file_parser=fix_parser,
        python_compiler=fix_compiler
    )
    
    # Verify fix_step received test code in prompt
    assert "【测试代码】" in fix_llm.prompts[0]
    assert "get_vote_count" in fix_llm.prompts[0]
    
    # Verify file ops were generated
    assert len(context["final_file_ops"]) > 0
    assert context["final_file_ops"][0]["content"] == "class VotingSystem:\n    def get_vote_count(self):\n        return 5"


# =============================================================================
# Test 4: Backward compatibility (no injection)
# =============================================================================

def test_backward_compatibility_without_injection():
    """
    Verify that steps still work without dependency injection (backward compatibility).
    This test verifies that the default real implementations are used when no mocks are provided.
    """
    # This test would call real LLM and execute real code
    # For now, we just verify the function signature accepts None
    from python_worker.agents.qwen.step_executor import test_step, fix_step
    
    # Should not raise TypeError
    context = {"intermediate_results": [], "final_file_ops": [], "meta": {}}
    step = {}
    
    # Test that functions can be called with None (default)
    # Note: This will fail if LLM API is not configured, but that's expected
    # We're just testing the signature compatibility
    try:
        test_step.run_test_step(step, context, [], llm_client=None, code_executor=None)
    except Exception as e:
        # Expected if LLM not configured
        assert "call_qwen" in str(e).lower() or "api" in str(e).lower()
    
    try:
        fix_step.run_fix_step(
            step,
            context,
            [],
            llm_client=None,
            file_parser=None,
            python_compiler=None
        )
    except Exception as e:
        # Expected if source files not available
        assert "source" in str(e).lower() or "fix" in str(e).lower()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])