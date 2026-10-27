"""P2 advanced: T22-T42. Advanced/edge-case Python defect scenarios."""

from smoke_tests.config import TEST_IMPORT_DIV

# ── T22: Q-018 SQL 拼接注入 — f-string 拼接用户输入到 SQL 语句 ──
BUGGY_SQL_INJECT = (
    "def search_query(name):\n"
    "    return f\"SELECT * FROM users WHERE name = '{name}'\"\n"
)
TEST_SQL_INJECT = (
    TEST_IMPORT_DIV
    + "from src.user_search import search_query\n"
    + "def test_no_raw_injection():\n"
    + "    sql = search_query(\"admin' OR '1'='1\")\n"
    + "    assert \"OR '1'='1\" not in sql\n"
)

# ── T23: Q-020 路径遍历注入 — 用户输入未校验直接拼入文件路径 ──
BUGGY_PATH_TRAVERSAL = (
    "import os\n"
    "def read_file(base_dir, filename):\n"
    "    return open(os.path.join(base_dir, filename)).read()\n"
)
TEST_PATH_TRAVERSAL = (
    TEST_IMPORT_DIV
    + "from src.file_access import read_file\n"
    + "import pytest\n"
    + "def test_block_path_traversal(tmp_path):\n"
    + "    base = tmp_path / 'safe'\n"
    + "    base.mkdir()\n"
    + "    (base / 'ok.txt').write_text('hello')\n"
    + "    with pytest.raises(ValueError):\n"
    + "        read_file(str(base), '../etc/passwd')\n"
    + "def test_normal_read(tmp_path):\n"
    + "    base = tmp_path / 'safe'\n"
    + "    base.mkdir()\n"
    + "    (base / 'ok.txt').write_text('hello')\n"
    + "    assert read_file(str(base), 'ok.txt') == 'hello'\n"
)

# ── T24: Q-021 import 后未用模块前缀 — import math 但直接用 pi ──
BUGGY_MOD_A = (
    "import math\n\n"
    "def circle_circumference(radius):\n"
    "    return 2 * pi * radius\n"
)
TEST_CIRCULAR_IMPORT = (
    TEST_IMPORT_DIV
    + "from src.mod_a import circle_circumference\n"
    + "def test_circumference():\n"
    + "    assert abs(circle_circumference(1) - 6.283185) < 0.001\n"
)

# ── T25: Q-022 str+int 拼接 TypeError ──
BUGGY_FULL_READ = (
    "def page_label(n):\n"
    "    return 'Page ' + n\n"
)
TEST_FULL_READ = (
    TEST_IMPORT_DIV
    + "from src.pager import page_label\n"
    + "def test_page():\n"
    + "    assert page_label(1) == 'Page 1'\n"
)

# ── T26: Q-023 字典遍历时删除 — RuntimeError ──
BUGGY_DICT_DEL = (
    "def clean_dict(d, remove_val):\n"
    "    for k, v in d.items():\n"
    "        if v == remove_val:\n"
    "            del d[k]\n"
    "    return d\n"
)
TEST_DICT_DEL = (
    TEST_IMPORT_DIV
    + "from src.cleaner import clean_dict\n"
    + "def test_clean():\n"
    + "    assert clean_dict({'a': 1, 'b': 2, 'c': 1}, 1) == {'b': 2}\n"
)

# ── T27: Q-024 list.insert(-1) 反直觉行为 ──
BUGGY_UNSAFE_CTR = (
    "def pad_right(items, n, val):\n"
    "    for _ in range(n):\n"
    "        items.insert(-1, val)\n"
    "    return items\n"
)
TEST_UNSAFE_CTR = (
    TEST_IMPORT_DIV
    + "from src.padder import pad_right\n"
    + "def test_pad_right():\n"
    + "    assert pad_right([1, 2, 3], 2, 0) == [1, 2, 3, 0, 0]\n"
)

# ── T28: Q-025 set 无序去重 — set 不保留原始顺序 ──
BUGGY_TZ_NAIVE = (
    "def unique_keep_order(items):\n"
    "    return list(set(items))\n"
)
TEST_TZ_NAIVE = (
    TEST_IMPORT_DIV
    + "from src.uniquer import unique_keep_order\n"
    + "def test_keep_order():\n"
    + "    assert unique_keep_order([3, 1, 2, 1, 3]) == [3, 1, 2]\n"
)

# ── T29: Q-026 浅拷贝嵌套陷阱 — list[:] 仅浅拷贝 ──
BUGGY_SHALLOW_COPY = (
    "def clone_grid(grid):\n"
    "    return grid[:]\n"
)
TEST_SHALLOW_COPY = (
    TEST_IMPORT_DIV
    + "from src.grid_util import clone_grid\n"
    + "def test_deep_independence():\n"
    + "    original = [[1, 2], [3, 4]]\n"
    + "    copy = clone_grid(original)\n"
    + "    copy[0][0] = 99\n"
    + "    assert original[0][0] == 1\n"
)

# ── T30: Q-027 敏感信息泄漏 — print/日志直接输出 token ──
BUGGY_LOG_LEAK = (
    "import os\n"
    "API_TOKEN = os.environ.get('API_TOKEN', 'tk_test_12345')\n"
    "def fetch_data(endpoint):\n"
    "    print(f'Requesting {endpoint} with token={API_TOKEN}')\n"
    "    return {'status': 'ok'}\n"
)
TEST_LOG_LEAK = (
    TEST_IMPORT_DIV
    + "from src.api_client import fetch_data, API_TOKEN\n"
    + "def test_no_token_in_text():\n"
    + "    import io, sys\n"
    + "    old = sys.stdout\n"
    + "    sys.stdout = io.StringIO()\n"
    + "    try:\n"
    + "        fetch_data('/users')\n"
    + "        output = sys.stdout.getvalue()\n"
    + "    finally:\n"
    + "        sys.stdout = old\n"
    + "    assert 'tk_test_12345' not in output\n"
)

# ── T31: Q-029 生成器复用 — 耗尽后二次迭代为空 ──
BUGGY_GEN_REUSE = (
    "def rank_and_split(items):\n"
    "    ranked = (x * 2 for x in sorted(items))\n"
    "    top = list(ranked)\n"
    "    rest = list(ranked)\n"
    "    return top, rest\n"
)
TEST_GEN_REUSE = (
    TEST_IMPORT_DIV
    + "from src.ranker import rank_and_split\n"
    + "def test_rank_and_split():\n"
    + "    top, rest = rank_and_split([3, 1, 2])\n"
    + "    assert top == [2, 4, 6]\n"
    + "    assert len(rest) > 0\n"
)

# ── T32: Q-030 类属性共享 — 类级 list 被实例共享 ──
BUGGY_CLASS_ATTR = (
    "class ShoppingCart:\n"
    "    items = []\n\n"
    "    def add(self, product):\n"
    "        self.items.append(product)\n\n"
    "    def get_items(self):\n"
    "        return self.items\n"
)
TEST_CLASS_ATTR = (
    TEST_IMPORT_DIV
    + "from src.cart import ShoppingCart\n"
    + "def test_cart_independence():\n"
    + "    c1 = ShoppingCart()\n"
    + "    c2 = ShoppingCart()\n"
    + "    c1.add('apple')\n"
    + "    c2.add('banana')\n"
    + "    assert c1.get_items() == ['apple']\n"
    + "    assert c2.get_items() == ['banana']\n"
)

# ── T33: Q-032 NaN 比较 — NaN != NaN ──
BUGGY_NAN_CMP = (
    "def has_nan(values):\n"
    "    return None in [v for v in values if v != v]\n"
)
TEST_NAN_CMP = (
    TEST_IMPORT_DIV
    + "from src.validator import has_nan\n"
    + "def test_has_nan():\n"
    + "    assert has_nan([1.0, float('nan'), 2.0])\n"
    + "def test_no_nan():\n"
    + "    assert not has_nan([1.0, 2.0, 3.0])\n"
)

# ── T34: Q-033 HTTP 无超时 — requests.get 缺 timeout ──
BUGGY_NO_TIMEOUT = (
    "import requests\n\n"
    "def fetch_url(url):\n"
    "    return requests.get(url).text\n"
)
TEST_NO_TIMEOUT = (
    TEST_IMPORT_DIV
    + "from src.fetcher import fetch_url\n"
    + "def test_fetch_with_timeout():\n"
    + "    import inspect\n"
    + "    src = inspect.getsource(fetch_url)\n"
    + "    assert 'timeout' in src\n"
)

# ── T35: Q-034 JSON 序列化 — datetime 非标准类型 ──
# 测试要求：(1) 可 json.loads 反序列化 (2) 原始字段不丢失 (3) timestamp 字段保留
BUGGY_JSON_SERIALIZE = (
    "import json\n"
    "from datetime import datetime\n"
    "def to_json(record):\n"
    "    record['timestamp'] = datetime.now()\n"
    "    return json.dumps(record)\n"
)
TEST_JSON_SERIALIZE = (
    TEST_IMPORT_DIV
    + "import json\n"
    + "from src.serializer import to_json\n"
    + "def test_json_roundtrip():\n"
    + "    result = to_json({'event': 'login'})\n"
    + "    data = json.loads(result)\n"
    + "    assert data['event'] == 'login'\n"
    + "    assert 'timestamp' in data\n"
)

# ── T36: Q-036 正则贪婪匹配 — {.*} 跨越多组 ──
BUGGY_CMD_INJECT = (
    "import re\n\n"
    "def extract_tags(text):\n"
    "    return re.findall(r'\\{.*\\}', text)\n"
)
TEST_CMD_INJECT = (
    TEST_IMPORT_DIV
    + "from src.tagger import extract_tags\n"
    + "def test_extract_non_greedy():\n"
    + "    result = extract_tags('{a} and {b}')\n"
    + "    assert result == ['{a}', '{b}']\n"
)

# ── T37: Q-037 浮点累积误差 — 循环累加 ──
BUGGY_FLOAT_ACCUM = (
    "def total_price(unit_price, qty):\n"
    "    total = 0.0\n"
    "    for _ in range(qty):\n"
    "        total += unit_price\n"
    "    return total\n"
)
TEST_FLOAT_ACCUM = (
    TEST_IMPORT_DIV
    + "from src.pricing import total_price\n"
    + "def test_total():\n"
    + "    assert total_price(0.1, 3) == 0.3\n"
)

# ── T38: Q-038 assert 校验 — 生产环境跳过 ──
BUGGY_ASSERT_CHECK = (
    "def set_age(age):\n"
    "    assert age >= 0\n"
    "    return age\n"
)
TEST_ASSERT_CHECK = (
    TEST_IMPORT_DIV
    + "from src.age_setter import set_age\n"
    + "import pytest\n"
    + "def test_set_valid():\n"
    + "    assert set_age(25) == 25\n"
    + "def test_set_negative():\n"
    + "    with pytest.raises(ValueError):\n"
    + "        set_age(-5)\n"
)

# ── T39: Q-039 字符串版本比较 — '9' > '10' ──
BUGGY_HANDLE_LEAK = (
    "def newer(v1, v2):\n"
    "    return max(v1, v2)\n"
)
TEST_HANDLE_LEAK = (
    TEST_IMPORT_DIV
    + "from src.vercmp import newer\n"
    + "def test_newer():\n"
    + "    assert newer('1.9', '1.10') == '1.10'\n"
)

# ── T40: Q-040 __init__ 默认参数 — items=[] ──
BUGGY_INIT_DEFAULT = (
    "class Collector:\n"
    "    def __init__(self, items=[]):\n"
    "        self.items = items\n"
    "    def add(self, x):\n"
    "        self.items.append(x)\n"
    "    def get(self):\n"
    "        return self.items\n"
)
TEST_INIT_DEFAULT = (
    TEST_IMPORT_DIV
    + "from src.collector_cls import Collector\n"
    + "def test_collector_independence():\n"
    + "    a = Collector()\n"
    + "    b = Collector()\n"
    + "    a.add(1)\n"
    + "    b.add(2)\n"
    + "    assert a.get() == [1]\n"
    + "    assert b.get() == [2]\n"
)

# ── T41: Q-041 is 比较字符串 — 'hell'+'o' is 'hello' ──
BUGGY_STAR_IMPORT = (
    "def is_hello(s):\n"
    "    return s is 'hello'\n"
)
TEST_STAR_IMPORT = (
    TEST_IMPORT_DIV
    + "from src.strcmp import is_hello\n"
    + "def test_is_hello():\n"
    + "    h = ''.join([chr(104), chr(101), chr(108), chr(108), chr(111)])\n"
    + "    assert is_hello(h)\n"
    + "    assert not is_hello('world')\n"
)

# ── T42: Q-042 协程未 await — 返回 coroutine 对象 ──
BUGGY_MISSING_AWAIT = (
    "import asyncio\n\n"
    "async def get_user(user_id):\n"
    "    await asyncio.sleep(0.01)\n"
    "    return {'id': user_id, 'name': 'Alice'}\n\n"
    "def get_user_sync(user_id):\n"
    "    return get_user(user_id)\n"
)
TEST_MISSING_AWAIT = (
    TEST_IMPORT_DIV
    + "from src.user_async import get_user_sync\n"
    + "def test_get_user_returns_dict():\n"
    + "    result = get_user_sync(1)\n"
    + "    assert isinstance(result, dict)\n"
    + "    assert result['name'] == 'Alice'\n"
)