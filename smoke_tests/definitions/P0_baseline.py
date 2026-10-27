"""P0 baseline: S0-S5 core scenarios + T1-T6 matrix questions."""

from smoke_tests.config import TEST_IMPORT_DIV

# ══════════════════════════════════════════════════════════════
#  核心自愈试题：基础缺陷类型
# ══════════════════════════════════════════════════════════════

BUGGY_DIV = "def div(a, b):\n    return a / b\n"
FIXED_DIV = (
    "def div(a, b):\n"
    "    if b == 0:\n"
    "        raise ValueError('division by zero')\n"
    "    return a / b\n"
)
UNFIXABLE = "def broken():\n    return undefined_var\n"

TEST_PASSING = (
    TEST_IMPORT_DIV
    + "from src.calc import div\nimport pytest\n"
    + "def test_div_normal():\n    assert div(10, 2) == 5\n"
    + "def test_div_zero():\n"
    + "    with pytest.raises(ValueError):\n        div(1, 0)\n"
)
TEST_FAILING = (
    TEST_IMPORT_DIV
    + "from src.calc import div\n"
    + "def test_div():\n    assert div(10, 2) == 5\n"
    + "def test_div_zero_should_fail():\n    div(1, 0)\n"
)
TEST_UNFIXABLE = (
    TEST_IMPORT_DIV
    + "from src.broken_mod import broken\n"
    + "def test_broken():\n    assert broken() is not None\n"
)

# S1：源文件缺 import（NameError）
BUGGY_MISSING_IMPORT = (
    "def to_json_string(data):\n"
    "    return json.dumps(data, ensure_ascii=False)\n"
)
TEST_MISSING_IMPORT = (
    TEST_IMPORT_DIV
    + "from src.serializer import to_json_string\n"
    + "def test_to_json_string():\n"
    + "    result = to_json_string({'key': 'value'})\n"
    + "    assert 'key' in result\n"
)

# S2：跨文件类型错误
BUGGY_CONSTANTS = 'DISCOUNT_RATE = "0.1"  # should be float\n'
BUGGY_CALC_CROSS = (
    "from src.constants import DISCOUNT_RATE\n\n"
    "def apply_discount(price: float) -> float:\n"
    "    return price * (1 - DISCOUNT_RATE)\n"
)
TEST_CROSS_FILE_TYPE = (
    TEST_IMPORT_DIV
    + "from src.calc import apply_discount\n"
    + "def test_apply_discount():\n"
    + "    assert apply_discount(100.0) == 90.0\n"
)

# S3：边界条件误判
BUGGY_TRUNCATE = (
    "def truncate(text: str, max_len: int) -> str:\n"
    "    return text[:max_len] + '...'\n"
)
TEST_TRUNCATE = (
    TEST_IMPORT_DIV
    + "from src.text_tools import truncate\n"
    + "def test_truncate_short():\n"
    + "    assert truncate('hi', 10) == 'hi'\n"
    + "def test_truncate_long():\n"
    + "    assert truncate('hello', 3) == 'hel...'\n"
)

# S4 mock 失败路径（fix_effect="never_fix"）— 无自定义定义

# S5：多文件连锁 — 改了返回值 key，调用方崩溃
BUGGY_STORE = (
    "def get_user(user_id: int) -> dict:\n"
    "    return {'user_id': user_id, 'name': 'test'}\n"
)
BUGGY_SERVICE = (
    "from src.store import get_user\n\n"
    "def format_greeting(user_id: int) -> str:\n"
    "    user = get_user(user_id)\n"
    "    return f\"Hello, {user['name']}!\"\n"
)
TEST_CROSS_FILE_KEY = (
    TEST_IMPORT_DIV
    + "from src.service import format_greeting\n"
    + "def test_format_greeting():\n"
    + "    assert format_greeting(1) == 'Hello, test!'\n"
)

# S5-alt：跨文件 import 链 — 缺 import 在链末端
BUGGY_ENCODER = (
    "def encode(data):\n"
    "    return json.dumps(data)\n"
    "\n"
    "def decode(text):\n"
    "    return json.loads(text)\n"
)
BUGGY_API_CHAIN = (
    "from src.encoder import encode, decode\n\n"
    "def to_json(data):\n"
    "    return encode(data)\n\n"
    "def from_json(text):\n"
    "    return decode(text)\n"
)
TEST_IMPORT_CHAIN = (
    TEST_IMPORT_DIV
    + "from src.api import to_json, from_json\n"
    + "def test_to_json():\n"
    + "    result = to_json({'k': 'v'})\n"
    + "    assert result == '{\"k\": \"v\"}'\n"
    + "def test_from_json():\n"
    + "    result = from_json('{\"k\": \"v\"}')\n"
    + "    assert result == {'k': 'v'}\n"
)

# ══════════════════════════════════════════════════════════════
#  P0 优先级：42 题矩阵 T1-T6
# ══════════════════════════════════════════════════════════════

# T1: Q-028 LRU 缓存驱逐顺序
BUGGY_LRU = (
    "from collections import OrderedDict\n\n"
    "class LRUCache:\n"
    "    def __init__(self, capacity):\n"
    "        self.capacity = capacity\n"
    "        self.cache = OrderedDict()\n"
    "    def get(self, key):\n"
    "        if key not in self.cache:\n"
    "            return -1\n"
    "        return self.cache[key]\n"
    "    def put(self, key, value):\n"
    "        if key in self.cache:\n"
    "            self.cache.move_to_end(key)\n"
    "        self.cache[key] = value\n"
    "        if len(self.cache) > self.capacity:\n"
    "            self.cache.popitem(last=False)\n"
)
TEST_LRU = (
    TEST_IMPORT_DIV
    + "from src.lru import LRUCache\n"
    + "def test_lru_eviction():\n"
    + "    c = LRUCache(2)\n"
    + "    c.put(1, 1); c.put(2, 2)\n"
    + "    assert c.get(1) == 1\n"
    + "    c.put(3, 3)\n"
    + "    assert c.get(2) == -1\n"
    + "    assert c.get(1) == 1\n"
    + "    assert c.get(3) == 3\n"
)

# T2: Q-001 验证缺陷 — 漏上界检查
BUGGY_VALIDATOR = (
    "def validate_range(value, min_val, max_val):\n"
    "    if min_val > max_val:\n"
    "        raise ValueError(f'min({min_val}) > max({max_val})')\n"
    "    if value < min_val:\n"
    "        raise ValueError(f'{value} < {min_val}')\n"
    "    return True\n"
)
TEST_VALIDATOR = (
    TEST_IMPORT_DIV
    + "from src.validator import validate_range\n"
    + "def test_validate_ok():\n"
    + "    assert validate_range(5, 0, 10)\n"
    + "def test_exceed_max():\n"
    + "    import pytest\n"
    + "    with pytest.raises(ValueError):\n"
    + "        validate_range(15, 0, 10)\n"
)

# T3: Q-031 输入验证 — 缺 else 分支
BUGGY_PARSER = (
    "def parse_range(s):\n"
    "    if '-' in s:\n"
    "        start, end = s.split('-')\n"
    "        return int(start), int(end)\n"
)
TEST_PARSER = (
    TEST_IMPORT_DIV
    + "from src.parser import parse_range\n"
    + "def test_parse_range_valid():\n"
    + "    assert parse_range('1-10') == (1, 10)\n"
    + "def test_parse_range_invalid():\n"
    + "    import pytest\n"
    + "    with pytest.raises(ValueError):\n"
    + "        parse_range('abc')\n"
    + "    with pytest.raises(ValueError):\n"
    + "        parse_range('1-xyz')\n"
)

# T4: Q-006 闭包陷阱 — late binding
BUGGY_CLOSURE = (
    "def make_multipliers(n):\n"
    "    result = []\n"
    "    for i in range(1, n + 1):\n"
    "        result.append(lambda x: x * i)\n"
    "    return result\n"
)
TEST_CLOSURE = (
    TEST_IMPORT_DIV
    + "from src.closure import make_multipliers\n"
    + "def test_multipliers():\n"
    + "    funcs = make_multipliers(3)\n"
    + "    assert funcs[0](10) == 10\n"
    + "    assert funcs[1](10) == 20\n"
    + "    assert funcs[2](10) == 30\n"
)

# T5: Q-019 配置脆弱 — os.environ[...] 无默认值
BUGGY_CONFIG = (
    "import os\n\n"
    "DATABASE_URL = os.environ['DATABASE_URL']\n"
)
TEST_CONFIG = (
    TEST_IMPORT_DIV
    + "def test_config_default():\n"
    + "    import os\n"
    + "    old = os.environ.get('DATABASE_URL')\n"
    + "    if 'DATABASE_URL' in os.environ:\n"
    + "        del os.environ['DATABASE_URL']\n"
    + "    try:\n"
    + "        from src.config import DATABASE_URL\n"
    + "        assert DATABASE_URL is not None\n"
    + "    finally:\n"
    + "        if old is not None:\n"
    + "            os.environ['DATABASE_URL'] = old\n"
)

# T6: Q-035 CLI 文件操作 — 写了内部结果但未写入 out_path
BUGGY_CLI = (
    "def transform_file(in_path, out_path):\n"
    "    with open(in_path) as f:\n"
    "        data = f.read()\n"
    "    result = []\n"
    "    for line in data.split('\\n'):\n"
    "        result.append(line.upper())\n"
    "    return result\n"
)
TEST_CLI = (
    TEST_IMPORT_DIV
    + "from src.cli import transform_file\n"
    + "def test_transform(tmp_path):\n"
    + "    inp = tmp_path / 'in.txt'\n"
    + "    inp.write_text('hello')\n"
    + "    out = tmp_path / 'out.txt'\n"
    + "    n = transform_file(str(inp), str(out))\n"
    + "    assert out.exists()\n"
    + "    assert out.read_text() == 'HELLO'\n"
    + "    assert isinstance(n, int)\n"
)