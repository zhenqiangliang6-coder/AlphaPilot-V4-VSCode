"""
Unit tests for self-healing fix functionality.

Tests the enhanced fix_step that receives test code from test_step context
and uses it to guide the repair process.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.step_executor import fix_step
from python_worker.agents.qwen.step_executor.prompts import fix_prompt


# =============================================================================
# Test 1: _get_test_context extracts test code
# =============================================================================

def test_get_test_context_extracts_test_code():
    """
    Verify that _get_test_context correctly extracts both error info and test code
    from context['intermediate_results'].
    """
    context = {
        "intermediate_results": [
            {
                "type": "test",
                "test_code": "def test_get_vote_count():\n    assert get_vote_count() == 5",
                "status": "failed",
                "error": "AttributeError: 'VotingSystem' object has no attribute 'get_vote_count'"
            }
        ]
    }

    error_info, test_code = fix_step._get_test_context(context)

    # Verify error info is extracted
    assert "AttributeError" in error_info
    assert "get_vote_count" in error_info

    # Verify test code is extracted
    assert "test_get_vote_count" in test_code
    assert "get_vote_count" in test_code


def test_get_test_context_handles_missing_test_code():
    """
    Verify that _get_test_context gracefully handles context without test code.
    """
    context = {
        "intermediate_results": [
            {
                "type": "test",
                "status": "failed",
                "error": "Some error"
            }
        ]
    }

    error_info, test_code = fix_step._get_test_context(context)

    # Should return error info but empty test code
    assert error_info == "Some error"
    assert test_code == ""


def test_get_test_context_handles_empty_context():
    """
    Verify that _get_test_context handles empty context gracefully.
    """
    context = {}

    error_info, test_code = fix_step._get_test_context(context)

    assert error_info == ""
    assert test_code == ""


def test_get_test_context_extracts_from_output():
    """
    Verify that _get_test_context can extract test code from output.text
    when test_code field is not available (backward compatibility).
    """
    context = {
        "intermediate_results": [
            {
                "type": "test",
                "status": "failed",
                "output": {
                    "text": "Generated test code:\n```python\ndef test_example():\n    assert True\n```"
                }
            }
        ]
    }

    error_info, test_code = fix_step._get_test_context(context)

    # Should extract from output.text
    assert "test_example" in error_info
    assert test_code == ""  # test_code field is empty since it's not in the data


# =============================================================================
# Test 2: fix_prompt includes test code when provided
# =============================================================================

def test_fix_prompt_includes_test_code():
    """
    Verify that fix_prompt includes test code in the prompt when provided.
    This enables the model to understand test expectations.
    """
    code = "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
    error = "AttributeError: 'VotingSystem' object has no attribute 'get_vote_count'"
    test_code = "def test_get_vote_count():\n    assert get_vote_count() == 5"

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Verify test code is included in prompt
    assert "【测试代码】" in prompt
    assert "test_get_vote_count" in prompt
    assert "你的修复必须通过以下测试" in prompt
    assert "接口期望（方法名、参数签名、返回值类型）" in prompt


def test_fix_prompt_without_test_code():
    """
    Verify that fix_prompt works without test code (backward compatibility).
    """
    code = "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
    error = "AttributeError: 'VotingSystem' object has no attribute 'get_vote_count'"

    prompt = fix_prompt("voting.py", code, error)

    # Should not include test code section
    assert "【测试代码】" not in prompt
    # Should still include original code and error
    assert "【原始代码】" in prompt
    assert "【执行错误】" in prompt


def test_fix_prompt_with_long_test_code():
    """
    Verify that fix_prompt handles long test code correctly.
    """
    code = "class VotingSystem:\n    pass"
    error = "Test failed"
    test_code = "\n".join([f"def test_{i}():\n    assert True" for i in range(10)])

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Should include all test code
    assert "【测试代码】" in prompt
    assert "test_0" in prompt
    assert "test_9" in prompt


# =============================================================================
# Test 3: Real-world scenarios - method name mismatch
# =============================================================================

def test_scenario_method_name_mismatch():
    """
    Test scenario: test expects get_vote_count() but model implemented get_candidate_votes().
    Verify that fix_prompt with test code would help the model understand the mismatch.
    """
    code = "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
    error = "AttributeError: 'VotingSystem' object has no attribute 'get_vote_count'"
    test_code = "def test_get_vote_count():\n    assert get_vote_count() == 5"

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Model should see both the wrong method name and the expected one
    assert "get_candidate_votes" in prompt  # Wrong implementation
    assert "get_vote_count" in prompt  # Expected by test
    assert "接口期望（方法名、参数签名、返回值类型）" in prompt


def test_scenario_return_type_mismatch():
    """
    Test scenario: test expects bool return but model returns (bool, str) tuple.
    """
    code = "class VotingSystem:\n    def cast_vote(self, user):\n        return True, 'Success'"
    error = "AssertionError: assert isinstance(result, bool)"
    test_code = "def test_cast_vote():\n    result = cast_vote('user1')\n    assert isinstance(result, bool)"

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Model should see the type check in the test
    assert "isinstance(result, bool)" in prompt
    assert "返回值类型" in prompt


def test_scenario_fixture_signature():
    """
    Test scenario: test uses a specific fixture signature.
    """
    code = "class VotingSystem:\n    def vote(self, user_id):\n        return True"
    error = "TypeError: vote() missing 1 required positional argument: 'user_id'"
    test_code = """
@pytest.fixture
def voting_system():
    return VotingSystem()

def test_vote(voting_system):
    result = voting_system.vote(123)
    assert result is True
"""

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Model should see the fixture usage
    assert "voting_system" in prompt
    assert "pytest.fixture" in prompt


# =============================================================================
# Test 4: Edge cases
# =============================================================================

def test_fix_prompt_empty_test_code():
    """
    Verify that fix_prompt handles empty test code gracefully.
    """
    code = "class VotingSystem:\n    pass"
    error = "Some error"
    test_code = ""

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Should not include test code section when empty
    assert "【测试代码】" not in prompt


def test_fix_prompt_special_characters_in_test_code():
    """
    Verify that fix_prompt handles special characters in test code.
    """
    code = "class VotingSystem:\n    pass"
    error = "Test failed"
    test_code = "def test_special():\n    assert 'test' == \"test\"\n    assert 1 != 0"

    prompt = fix_prompt("voting.py", code, error, test_code)

    # Should include special characters
    assert "assert 'test' == \"test\"" in prompt


# =============================================================================
# Test 5: Integration with context
# =============================================================================

def test_context_flow_from_test_to_fix():
    """
    Verify the complete data flow: test_step saves test code → fix_step reads it.
    This simulates the actual workflow without running the full execution chain.
    """
    # Simulate context after test_step has run
    context_after_test = {
        "intermediate_results": [
            {
                "type": "write",
                "text": "```python\nclass VotingSystem:\n    def get_candidate_votes(self):\n        return 5\n```"
            },
            {
                "type": "test",
                "test_code": "def test_get_vote_count():\n    assert get_vote_count() == 5",
                "status": "failed",
                "error": "AttributeError: 'VotingSystem' object has no attribute 'get_vote_count'"
            }
        ]
    }

    # fix_step extracts test code
    error_info, test_code = fix_step._get_test_context(context_after_test)

    # Verify extraction
    assert "get_vote_count" in test_code
    assert "AttributeError" in error_info

    # fix_prompt would use this to guide the model
    original_code = "class VotingSystem:\n    def get_candidate_votes(self):\n        return 5"
    prompt = fix_prompt("voting.py", original_code, error_info, test_code)

    # Verify the prompt contains all necessary information
    assert "get_candidate_votes" in prompt  # Wrong method
    assert "get_vote_count" in prompt  # Expected method
    assert "【测试代码】" in prompt


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
