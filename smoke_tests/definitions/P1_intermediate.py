"""P1 intermediate: T7-T21. Medium-complexity Python defect scenarios."""

from smoke_tests.config import TEST_IMPORT_DIV

# ── T7: Q-002 可变默认参数 — list 默认参数在多次调用间共享 ──
BUGGY_MUTABLE_DEFAULT = (
    "def append_item(item, lst=[]):\n"
    "    lst.append(item)\n"
    "    return lst\n"
)
TEST_MUTABLE_DEFAULT = (
    TEST_IMPORT_DIV
    + "from src.collector import append_item\n"
    + "def test_fresh_list_each_call():\n"
    + "    r1 = append_item(1)\n"
    + "    r2 = append_item(2)\n"
    + "    assert r1 == [1]\n"
    + "    assert r2 == [2]\n"
    + "    assert r1 is not r2\n"
)

# ── T8: Q-003 过度宽泛异常 — except: 吞掉 TypeError ──
BUGGY_BARE_EXCEPT = (
    "def parse_int(s):\n"
    "    try:\n"
    "        return int(s)\n"
    "    except:\n"
    "        return 0\n"
)
TEST_BARE_EXCEPT = (
    TEST_IMPORT_DIV
    + "from src.safe_parser import parse_int\n"
    + "import pytest\n"
    + "def test_parse_valid():\n"
    + "    assert parse_int('42') == 42\n"
    + "def test_bad_type_should_raise():\n"
    + "    with pytest.raises(TypeError):\n"
    + "        parse_int(None)\n"
)

# ── T9: Q-004 遍历时修改列表 — for 循环中 remove 跳过相邻元素 ──
BUGGY_FILE_LEAK = (
    "def remove_odds(numbers):\n"
    "    for n in numbers:\n"
    "        if n % 2 != 0:\n"
    "            numbers.remove(n)\n"
    "    return numbers\n"
)
TEST_FILE_LEAK = (
    TEST_IMPORT_DIV
    + "from src.filter import remove_odds\n"
    + "def test_remove_odds():\n"
    + "    assert remove_odds([1, 1, 2, 3, 4]) == [2, 4]\n"
)

# ── T10: Q-005 None 传播链 — 函数可能返回 None，调用方直接使用属性 ──
BUGGY_NONE_CHAIN = (
    "def lookup_user(users, uid):\n"
    "    for u in users:\n"
    "        if u['id'] == uid:\n"
    "            return u\n"
    "    return None\n\n"
    "def get_username(users, uid):\n"
    "    user = lookup_user(users, uid)\n"
    "    return user['name']\n"
)
TEST_NONE_CHAIN = (
    TEST_IMPORT_DIV
    + "from src.user_svc import get_username\n"
    + "def test_found_user():\n"
    + "    users = [{'id': 1, 'name': 'Alice'}]\n"
    + "    assert get_username(users, 1) == 'Alice'\n"
    + "def test_missing_user():\n"
    + "    users = [{'id': 1, 'name': 'Alice'}]\n"
    + "    assert get_username(users, 999) is None\n"
)

# ── T11: Q-007 除零无保护 — 计算平均值时空列表导致 ZeroDivisionError ──
BUGGY_AVG_ZERO = (
    "def average(numbers):\n"
    "    return sum(numbers) / len(numbers)\n"
)
TEST_AVG_ZERO = (
    TEST_IMPORT_DIV
    + "from src.stats import average\n"
    + "def test_average_normal():\n"
    + "    assert average([1, 2, 3]) == 2.0\n"
    + "def test_average_empty():\n"
    + "    assert average([]) == 0.0\n"
)

# ── T12: Q-008 空列表索引 — 负索引在空列表上抛出 IndexError ──
BUGGY_LAST_ELEM = (
    "def last_element(lst):\n"
    "    return lst[-1]\n"
)
TEST_LAST_ELEM = (
    TEST_IMPORT_DIV
    + "from src.tools import last_element\n"
    + "def test_last_non_empty():\n"
    + "    assert last_element([1, 2, 3]) == 3\n"
    + "def test_last_empty():\n"
    + "    assert last_element([]) is None\n"
)

# ── T13: Q-009 字典键缺失 — 直接 dict[key] 无防御性处理 ──
BUGGY_DICT_KEY = (
    "def extract_value(data, key):\n"
    "    return data[key]\n"
)
TEST_DICT_KEY = (
    TEST_IMPORT_DIV
    + "from src.extractor import extract_value\n"
    + "def test_key_exists():\n"
    + "    assert extract_value({'a': 1}, 'a') == 1\n"
    + "def test_key_missing():\n"
    + "    assert extract_value({'a': 1}, 'b') is None\n"
)

# ── T14: Q-010 None 类型运算 — 返回值可能为 None 被用于算术 ──
BUGGY_NONE_ARITH = (
    "def fetch_score(records, name):\n"
    "    for r in records:\n"
    "        if r['name'] == name:\n"
    "            return r['score']\n"
    "    return None\n\n"
    "def total_score(records, names):\n"
    "    t = 0\n"
    "    for n in names:\n"
    "        t += fetch_score(records, n)\n"
    "    return t\n"
)
TEST_NONE_ARITH = (
    TEST_IMPORT_DIV
    + "from src.scorer import total_score\n"
    + "def test_all_found():\n"
    + "    records = [{'name': 'A', 'score': 10}, {'name': 'B', 'score': 20}]\n"
    + "    assert total_score(records, ['A', 'B']) == 30\n"
    + "def test_some_missing():\n"
    + "    records = [{'name': 'A', 'score': 10}]\n"
    + "    assert total_score(records, ['A', 'X']) == 10\n"
)

# ── T15: Q-011 递归无终止条件 — 阶乘缺少 n<=1 基例 ──
BUGGY_FACTORIAL = (
    "def factorial(n):\n"
    "    return n * factorial(n - 1)\n"
)
TEST_FACTORIAL = (
    TEST_IMPORT_DIV
    + "from src.math_utils import factorial\n"
    + "def test_factorial_zero():\n"
    + "    assert factorial(0) == 1\n"
    + "def test_factorial_five():\n"
    + "    assert factorial(5) == 120\n"
)

# ── T16: Q-012 编码缺失 — 文本文件读取无 encoding ──
BUGGY_ENCODING = (
    "def read_text(path):\n"
    "    with open(path) as f:\n"
    "        return f.read()\n"
)
TEST_ENCODING = (
    TEST_IMPORT_DIV
    + "from src.reader import read_text\n"
    + "def test_read_utf8(tmp_path):\n"
    + "    p = tmp_path / 'hello.txt'\n"
    + "    p.write_text('\u4f60\u597d\u4e16\u754c', encoding='utf-8')\n"
    + "    assert '\u4f60\u597d' in read_text(str(p))\n"
)

# ── T17: Q-013 浮点数直等比较 — 0.1+0.2==0.3 为 False ──
BUGGY_FLOAT_EQ = (
    "def is_total_correct(items):\n"
    "    return sum(items) == 0.3\n"
)
TEST_FLOAT_EQ = (
    TEST_IMPORT_DIV
    + "from src.checker import is_total_correct\n"
    + "def test_float_sum():\n"
    + "    assert is_total_correct([0.1, 0.2])\n"
)

# ── T18: Q-014 正则表达式注入 — 用户输入未转义直接拼入正则模式 ──
BUGGY_REGEX = (
    "import re\n\n"
    "def find_match(pattern, text):\n"
    "    return bool(re.search(pattern, text))\n"
)
TEST_REGEX = (
    TEST_IMPORT_DIV
    + "from src.matcher import find_match\n"
    + "def test_literal_dot():\n"
    + "    assert find_match('example.com', 'Visit example.com today')\n"
    + "def test_special_char_escaped():\n"
    + "    assert not find_match('a+b', 'ab')\n"
)

# ── T19: Q-015 跨文件 None 传播 — service 返回 None，handler 不检查 ──
BUGGY_SERVICE_NONE = (
    "def get_user(users, uid):\n"
    "    for u in users:\n"
    "        if u['id'] == uid:\n"
    "            return u\n"
    "    return None\n"
)
BUGGY_HANDLER_NONE = (
    "from src.users_db import get_user\n\n"
    "def greet_user(users, uid):\n"
    "    user = get_user(users, uid)\n"
    "    return f\"Hello, {user['name']}!\"\n"
)
TEST_CROSS_NONE = (
    TEST_IMPORT_DIV
    + "from src.greeter import greet_user\n"
    + "def test_greet_found():\n"
    + "    users = [{'id': 1, 'name': 'Alice'}]\n"
    + "    assert greet_user(users, 1) == 'Hello, Alice!'\n"
    + "def test_greet_missing():\n"
    + "    users = [{'id': 1, 'name': 'Alice'}]\n"
    + "    assert greet_user(users, 999) == 'Hello, Guest!'\n"
)

# ── T20: Q-016 跨文件类型语义错误 — 数值以字符串返回，消费者做算术崩溃 ──
BUGGY_STR_RETURN = (
    "def fetch_price(products, pid):\n"
    "    for p in products:\n"
    "        if p['id'] == pid:\n"
    "            return p['price']\n"
    "    return '0'\n"
)
BUGGY_STR_CONSUMER = (
    "from src.pricing import fetch_price\n\n"
    "def calc_total(products, ids):\n"
    "    total = 0\n"
    "    for pid in ids:\n"
    "        total += fetch_price(products, pid)\n"
    "    return total\n"
)
TEST_CROSS_STR_TYPE = (
    TEST_IMPORT_DIV
    + "from src.checkout import calc_total\n"
    + "def test_calc_total():\n"
    + "    products = [{'id': 1, 'price': '10'}, {'id': 2, 'price': '20'}]\n"
    + "    assert calc_total(products, [1, 2]) == 30\n"
    + "def test_missing_product_defaults_zero():\n"
    + "    products = [{'id': 1, 'price': '10'}]\n"
    + "    assert calc_total(products, [1, 999]) == 10\n"
)

# ── T21: Q-017 模块级可变全局状态 — 函数未声明 global 直接赋值 ──
BUGGY_GLOBAL_CTR = (
    "counter = 0\n\n"
    "def increment():\n"
    "    counter += 1\n"
    "    return counter\n\n"
    "def reset_counter():\n"
    "    counter = 0\n"
)
TEST_GLOBAL_CTR = (
    TEST_IMPORT_DIV
    + "from src.tally import increment, reset_counter\n"
    + "def test_increment_reset():\n"
    + "    reset_counter()\n"
    + "    assert increment() == 1\n"
    + "    assert increment() == 2\n"
    + "    reset_counter()\n"
    + "    assert increment() == 1\n"
)