"""Compound decomposition tests — LLM classify output parsing & integration."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intent_router._decompose import Phase, CompoundPlan


def test_phase_creation():
    p = Phase(type="write_code", prompt="Write a login function")
    assert p.type == "write_code"
    assert "login" in p.prompt


def test_phase_empty_type_rejected():
    try:
        Phase(type="", prompt="test")
        assert False, "should raise"
    except ValueError:
        pass


def test_phase_empty_prompt_rejected():
    try:
        Phase(type="write_code", prompt="")
        assert False, "should raise"
    except ValueError:
        pass


def test_compound_plan_simple():
    cp = CompoundPlan(
        is_compound=False,
        fallback_intent="chat",
        fallback_persona="assistant",
        fallback_chain=["respond"],
    )
    assert not cp.is_compound
    assert cp.validate()
    i, p, c = cp.to_single()
    assert i == "chat"
    assert len(c) == 1


def test_compound_plan_to_single_raises():
    cp = CompoundPlan(
        is_compound=True,
        phases=[
            Phase("write_code", "make a login"),
            Phase("execute_operation", "push to git"),
        ],
    )
    assert cp.validate()
    try:
        cp.to_single()
        assert False, "should raise"
    except RuntimeError:
        pass


def test_from_llm_result_simple():
    def fallback():
        return ("chat", "assistant", ["respond"])

    llm_result = {
        "intent": "chat",
        "confidence": 0.9,
        "is_compound": False,
        "phases": [],
    }
    cp = CompoundPlan.from_llm_result(llm_result, fallback)
    assert not cp.is_compound
    assert cp.fallback_intent == "chat"


def test_from_llm_result_compound():
    def fallback():
        return ("write_code", "engineer", ["analyze", "plan", "write"])

    llm_result = {
        "intent": "write_code",
        "confidence": 0.95,
        "is_compound": True,
        "phases": [
            {"type": "write_code", "prompt": "Write a login function, update CHANGELOG"},
            {"type": "execute_operation", "prompt": "Push to GitHub"},
        ],
    }
    cp = CompoundPlan.from_llm_result(llm_result, fallback)
    assert cp.is_compound
    assert len(cp.phases) == 2
    assert cp.phases[0].type == "write_code"
    assert cp.phases[1].type == "execute_operation"
    assert "login" in cp.phases[0].prompt
    assert "GitHub" in cp.phases[1].prompt
    assert cp.validate()


def test_from_llm_result_single_phase_falls_back():
    """If LLM says is_compound=true but only gives 1 phase, should fall back."""
    def fallback():
        return ("write_code", "engineer", ["write"])

    llm_result = {
        "intent": "write_code",
        "confidence": 0.9,
        "is_compound": True,
        "phases": [{"type": "write_code", "prompt": "Just one"}],
    }
    cp = CompoundPlan.from_llm_result(llm_result, fallback)
    assert not cp.is_compound


def test_from_llm_result_none_falls_back():
    def fallback():
        return ("chat", "assistant", ["respond"])

    cp = CompoundPlan.from_llm_result(None, fallback)
    assert not cp.is_compound
    assert cp.fallback_intent == "chat"


def test_from_llm_result_bad_phases_falls_back():
    """If phases is not a list, fall back."""
    def fallback():
        return ("chat", "assistant", ["respond"])

    llm_result = {
        "intent": "write_code",
        "confidence": 0.9,
        "is_compound": True,
        "phases": "not-a-list",
    }
    cp = CompoundPlan.from_llm_result(llm_result, fallback)
    assert not cp.is_compound


def test_validate_compound_needs_2_phases():
    cp = CompoundPlan(
        is_compound=True,
        phases=[Phase("write_code", "only one")],
    )
    assert not cp.validate()


def test_validate_bad_phase_type():
    cp = CompoundPlan(
        is_compound=True,
        phases=[
            Phase("write_code", "make a login"),
            Phase("unknown_type", "do something"),
        ],
    )
    assert not cp.validate()


if __name__ == "__main__":
    tests = [
        ("Phase creation", test_phase_creation),
        ("Phase empty type rejected", test_phase_empty_type_rejected),
        ("Phase empty prompt rejected", test_phase_empty_prompt_rejected),
        ("CompoundPlan simple", test_compound_plan_simple),
        ("CompoundPlan to_single raises", test_compound_plan_to_single_raises),
        ("from_llm_result simple", test_from_llm_result_simple),
        ("from_llm_result compound", test_from_llm_result_compound),
        ("from_llm_result single phase fallback", test_from_llm_result_single_phase_falls_back),
        ("from_llm_result None fallback", test_from_llm_result_none_falls_back),
        ("from_llm_result bad phases fallback", test_from_llm_result_bad_phases_falls_back),
        ("validate compound needs 2 phases", test_validate_compound_needs_2_phases),
        ("validate bad phase type", test_validate_bad_phase_type),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {name} - {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)