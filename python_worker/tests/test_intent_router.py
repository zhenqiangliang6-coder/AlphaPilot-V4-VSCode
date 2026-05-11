# -*- coding: utf-8 -*-
# test_intent_router.py
# ---------------------------------------------------------
# Intent Router 单元测试 (v2.6)
# 验证意图识别的准确性和鲁棒性
# ---------------------------------------------------------

import sys
import os

# 设置控制台编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from intent_router import IntentRouter


def test_write_code_detection():
    """测试代码生成意图识别"""
    test_cases = [
        ("写一个排序算法", "write_code", "engineer"),
        ("实现快速排序", "write_code", "engineer"),
        ("创建一个函数来计算斐波那契数列", "write_code", "engineer"),
        ("write a sorting algorithm", "write_code", "engineer"),
        ("implement binary search", "write_code", "engineer"),
    ]
    
    print("\n🧪 测试代码生成意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_explain_code_detection():
    """测试代码解释意图识别"""
    test_cases = [
        ("解释一下这段代码", "explain_code", "engineer"),
        ("这是什么意思", "explain_code", "engineer"),
        ("帮我看看这个函数", "explain_code", "engineer"),  # ⭐ 修改: 避免与 analysis 冲突
        ("explain this code", "explain_code", "engineer"),
        ("what does this function do", "explain_code", "engineer"),
    ]
    
    print("\n🧪 测试代码解释意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_fix_code_detection():
    """测试错误修复意图识别"""
    test_cases = [
        ("修复这个bug", "fix_code", "engineer"),
        ("这段代码报错了", "fix_code", "engineer"),
        ("为什么运行不了", "fix_code", "engineer"),
        ("fix this error", "fix_code", "engineer"),
        ("debug the code", "fix_code", "engineer"),
    ]
    
    print("\n🧪 测试错误修复意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_creative_writing_detection():
    """测试创意写作意图识别"""
    test_cases = [
        ("写一首关于春天的诗", "creative_writing", "creator"),
        ("创作一个故事", "creative_writing", "creator"),
        ("写一篇散文", "creative_writing", "creator"),
        ("write a poem about love", "creative_writing", "creator"),
        ("create a short story", "creative_writing", "creator"),
    ]
    
    print("\n🧪 测试创意写作意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_chat_detection():
    """测试闲聊意图识别"""
    test_cases = [
        ("你觉得人工智能未来会怎样", "chat", "conversational"),
        ("你怎么看这个问题", "chat", "conversational"),
        ("聊聊你的想法", "chat", "conversational"),
        ("what do you think about AI", "chat", "conversational"),
        ("how are you today", "chat", "conversational"),
    ]
    
    print("\n🧪 测试闲聊意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_default_fallback():
    """测试默认降级逻辑"""
    test_cases = [
        ("这是一个普通的句子", "write_code", "engineer"),
        ("你好", "write_code", "engineer"),
        ("", "write_code", "engineer"),
    ]
    
    print("\n🧪 测试默认降级逻辑")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona}) [default]")


def test_execution_chain_mapping():
    """测试执行链路映射"""
    test_cases = [
        ("写代码", ["analyze", "plan", "write", "test", "refine"]),
        ("解释代码", ["analyze", "write"]),
        ("修复bug", ["analyze", "fix", "test"]),
        ("写诗", ["write", "refine"]),
        ("聊天", ["write"]),
        ("创作故事", ["write", "refine"]),  # ⭐ 添加这个测试
    ]
    
    print("\n🧪 测试执行链路映射")
    for prompt, expected_chain in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert chain == expected_chain, f"预期 {expected_chain}, 实际 {chain}"
        print(f"  ✅ '{prompt}' → {' → '.join(chain)}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Intent Router 单元测试 (v2.6)")
    print("=" * 60)
    
    try:
        test_write_code_detection()
        test_explain_code_detection()
        test_fix_code_detection()
        test_creative_writing_detection()
        test_chat_detection()
        test_default_fallback()
        test_execution_chain_mapping()
        
        print("\n" + "=" * 60)
        print("  ✅ 所有测试通过!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
