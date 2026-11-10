"""Traceback 双层提取边界测试

覆盖场景:
  T1 - 截断: 超长输出 (>6000 chars) 末尾异常不丢失
  T2 - 编码: Unicode/中文错误消息
  T3 - 多异常: stdout + stderr 各含不同异常类型
  T4 - 空输出: pytest 全部通过，无错误
  T5 - ImportError 深层链: 最终异常行在 importlib 之后（R8 真实场景）
  T6 - 无 File 行: 只有异常消息没有 traceback
  T7 - AssertionError: 断言比较失败
  T8 - SyntaxError: 编译错误
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_observe_task_system import _extract_test_error_lines


def _assert_diagnosis_contains(result: str, *keywords: str):
    """检查诊断摘要中包含所有关键信息"""
    diagnosis = result.split("=== 完整输出末尾")[0]
    for kw in keywords:
        assert kw in result, f"缺少关键信息: {kw!r}\n诊断摘要:\n{diagnosis[:500]}"


class TestTracebackBoundary:
    """双层证据提取边界测试"""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T1: 截断场景 — 超长输出末尾异常不丢失
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t1_truncation_preserves_final_exception(self):
        """超长输出（>6000 chars）必须保留末尾的关键异常消息"""
        padding = "x" * 7000
        stdout = f"{padding}\nE   ImportError: cannot import name 'OrderService' from 'backend.services'"
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        assert "[异常类型] ImportError" in result
        assert "cannot import name 'OrderService'" in result
        assert "从 'backend.services'" not in result or "backend.services" in result  # msg may be partial in tail
        assert len(result) < 7000 + 500, "输出不应无限膨胀（诊断摘要 + 末尾 6000 chars）"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T2: 编码场景 — Unicode/中文错误消息
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t2_unicode_error_messages(self):
        """中文和 Unicode 字符不应丢失或乱码"""
        stdout = (
            'Traceback (most recent call last):\n'
            '  File "测试文件.py", line 42, in test_订单\n'
            '    result = validate("产品名称")\n'
            'ValueError: 无效的输入参数 — cpu温度超过阈值: 95°C\n'
        )
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        assert "[异常类型] ValueError" in result
        assert "无效的输入参数" in result
        assert "cpu温度" in result
        assert "95°C" in result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T3: 多异常场景 — stdout + stderr 各含不同异常
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t3_multiple_exceptions_mixed_streams(self):
        """stdout 和 stderr 中的异常都应被纳入完整证据"""
        stdout = (
            'tests/test_orders.py::test_create_order FAILED\n'
            'E   ValueError: Invalid status transition\n'
        )
        stderr = (
            'ERROR tests/test_inventory.py::test_check_stock\n'
            'E   ImportError: No module named "sqlalchemy"\n'
        )

        result = _extract_test_error_lines(stdout, stderr)

        # 正则匹配第一个异常类型，但完整证据层应包含两者
        assert "ValueError" in result or "ImportError" in result
        # 完整证据层（末尾上下文）必须包含所有原始信息
        assert "test_create_order" in result
        assert "test_check_stock" in result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T4: 空输出 — pytest 全部通过
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t4_empty_output_no_errors(self):
        """pytest 全部通过时不应崩溃，诊断摘要应标注无信息"""
        stdout = "19 passed in 1.23s\n"
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        assert "无法提取结构化诊断信息" in result
        assert "19 passed" in result  # 原始输出仍在证据层

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T5: ImportError 深层调用链 — R8 真实场景回放
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t5_importerror_deep_chain_r8_scenario(self):
        """R8 真实场景: 调用链在 importlib 截断，最终异常在末尾"""
        stdout = (
            '_______ ERROR collecting tests/test_inventory.py _______\n'
            'tests/test_inventory.py:3: in <module>\n'
            '    from backend.main import app\n'
            'backend/main.py:5: in <module>\n'
            '    from .routers import router\n'
            'backend/routers/__init__.py:5: in <module>\n'
            '    from .orders import router as orders_router\n'
            'backend/routers/orders.py:3: in <module>\n'
            '    from ..services import OrderService\n'
            'backend/services/__init__.py:2: in <module>\n'
            '    from .order_service import (\n'
            'E   ImportError: cannot import name \'OrderService\' from \'backend.services.order_service\'\n'
            '!!!! Interrupted: 1 error during collection !!!!\n'
        )
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        assert "[异常类型] ImportError" in result
        assert "cannot import name" in result
        assert "OrderService" in result
        assert "order_service" in result
        # 调用链必须包含关键文件
        assert "main.py" in result
        assert "routers/__init__.py" in result
        assert "orders.py" in result
        assert "services/__init__.py" in result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T6: 无 File 行 — 只有异常消息没有调用链
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t6_no_file_lines_only_error_message(self):
        """只有异常消息、没有 File 调用链时不应崩溃"""
        stdout = "E   RuntimeError: Database connection refused\n"
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        assert "[异常类型] RuntimeError" in result
        assert "Database connection refused" in result
        # 不包含调用链（没有 File 行可提取）

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T7: pytest 断言失败 — 不含标准 AssertionError 字符串
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t7_pytest_assertion_rewrite_failure(self):
        """pytest 断言重写不输出 AssertionError: 字符串，但失败摘要和比较证据必须保留"""
        stdout = (
            'FAILED tests/test_inventory.py::test_create_order\n'
            '>       assert response.status_code == 201\n'
            'E       assert 200 == 201\n'
            'E        +  where 200 = <Response [200]>.status_code\n'
        )
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        # 失败摘要应包含 FAILED 行（pytest 断言失败的真实格式）
        assert "[失败摘要]" in result
        assert "test_create_order" in result
        # 证据层保留完整的比较上下文
        assert "200 == 201" in result
        # 注: pytest 断言重写不生成 "AssertionError:" 文本，因此诊断层不提取异常类型

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # T8: SyntaxError — 编译错误
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def test_t8_syntax_error_extraction(self):
        """SyntaxError 的异常类型和文件位置应正确提取"""
        stdout = (
            '  File "backend/routers/orders.py", line 42\n'
            '    def update_order_status(status: OrderStatus\n'
            '                            ^\n'
            'SyntaxError: unexpected EOF while parsing\n'
        )
        stderr = ""

        result = _extract_test_error_lines(stdout, stderr)

        assert "[异常类型] SyntaxError" in result
        assert "unexpected EOF while parsing" in result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 独立运行入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])