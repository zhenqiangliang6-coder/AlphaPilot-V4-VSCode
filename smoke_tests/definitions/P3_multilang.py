# smoke_tests/definitions/P3_multilang.py
"""Phase 2.4: 多语言Worker横向扩展 — 语言路由 + 队列映射 + Worker执行链测试定义"""

# ================================================================
# 语言检测路由规则（与 node-api/index.js LANGUAGE_DETECT_PATTERNS 一致）
# ================================================================

LANGUAGE_ROUTE_TESTS = [
    # (label, prompt, expected_language, expected_target_path, expected_queue)
    # Python 路由
    (
        "LANG-PY1",
        "帮我写一个 Python 数据处理的脚本",
        "python",
        "python_worker",
        "queue:qwen_py",
    ),
    (
        "LANG-PY2",
        "Create a Python Django REST API module",
        "python",
        "python_worker",
        "queue:qwen_py",
    ),
    (
        "LANG-PY3",
        "Fix the FastAPI middleware error handling",
        "python",
        "python_worker",
        "queue:qwen_py",
    ),

    # Java 路由
    (
        "LANG-JAVA1",
        "帮我写一个 Java Spring Boot Controller",
        "java",
        "java_worker",
        "queue:qwen_java",
    ),
    (
        "LANG-JAVA2",
        "Create a Java Maven project with JUnit tests",
        "java",
        "java_worker",
        "queue:qwen_java",
    ),
    (
        "LANG-JAVA3",
        "Fix the NullPointerException in this Java class",
        "java",
        "java_worker",
        "queue:qwen_java",
    ),
    (
        "LANG-JAVA4",
        "Generate a Java .properties config file",
        "java",
        "java_worker",
        "queue:qwen_java",
    ),

    # Node.js 路由
    (
        "LANG-NODE1",
        "帮我写一个 Node.js Express API 服务",
        "javascript",
        "node_worker",
        "queue:qwen_node",
    ),
    (
        "LANG-NODE2",
        "Create a Node.js script with package.json",
        "javascript",
        "node_worker",
        "queue:qwen_node",
    ),
    (
        "LANG-NODE3",
        "Fix the async/await error in this JavaScript module",
        "javascript",
        "node_worker",
        "queue:qwen_node",
    ),
    (
        "LANG-NODE4",
        "npm install express && run the server",
        "javascript",
        "node_worker",
        "queue:qwen_node",
    ),

    # TypeScript 路由
    (
        "LANG-TS1",
        "帮我写一个 TypeScript 类型安全的工具函数",
        "typescript",
        "ts_worker",
        "queue:qwen_ts",
    ),
    (
        "LANG-TS2",
        "Create a TypeScript React component with props interface",
        "typescript",
        "ts_worker",
        "queue:qwen_ts",
    ),
    (
        "LANG-TS3",
        "Fix the tsconfig.json and type errors in this project",
        "typescript",
        "ts_worker",
        "queue:qwen_ts",
    ),
    (
        "LANG-TS4",
        "tsc --noEmit && jest --coverage",
        "typescript",
        "ts_worker",
        "queue:qwen_ts",
    ),
]

# ================================================================
# 每个 Worker 的 E2E 冒烟场景
# ================================================================

E2E_SMOKE_SCENARIOS = {
    "node_worker": {
        "label": "Node.js Worker E2E",
        "prompt": (
            "Write a Node.js module 'src/math.js' that exports functions add(a,b) and multiply(a,b). "
            "Create a package.json with jest as test runner. "
            "Write tests/test_math.js that tests both functions. "
            "Return only valid code files."
        ),
        "expected_files": ["src/math.js", "package.json", "tests/test_math.js"],
        "build_command": ["npm", "install", "--silent"],
        "test_command": ["npm", "test", "--", "--passWithNoTests"],
        "language": "javascript",
    },
    "ts_worker": {
        "label": "TypeScript Worker E2E",
        "prompt": (
            "Write a TypeScript module 'src/calc.ts' that exports functions add(a:number, b:number):number "
            "and multiply(a:number, b:number):number. Include tsconfig.json with strict mode. "
            "Write tests/calc.test.ts using jest with ts-jest. Return only valid code files."
        ),
        "expected_files": ["src/calc.ts", "tsconfig.json", "tests/calc.test.ts", "package.json"],
        "build_command": ["npx", "tsc", "--noEmit"],
        "test_command": ["npx", "jest", "--passWithNoTests"],
        "language": "typescript",
    },
    "python_worker": {
        "label": "Python Worker E2E (Baseline)",
        "prompt": (
            "Write a Python module 'src/utils.py' that contains a function fibonacci(n: int) -> list[int] "
            "returning the first n Fibonacci numbers. Write pytest test in tests/test_utils.py."
        ),
        "expected_files": ["src/utils.py", "tests/test_utils.py"],
        "build_command": None,
        "test_command": None,
        "language": "python",
    },
}

# ================================================================
# Java 路由映射表
# ================================================================

JAVA_KEYWORDS = [
    "Java", "Spring Boot", "Maven", "JUnit", ".java", "pom.xml",
    "JpaRepository", "NullPointerException", "ClassNotFoundException",
    "gradle", "build.gradle",
]

# ================================================================
# Node.js 路由映射表
# ================================================================

NODE_KEYWORDS = [
    "Node.js", "Express", "Express.js", "npm ", "package.json",
    "require(", "module.exports", "async/await", "JavaScript",
    "callback", "Promise",
]

# ================================================================
# TypeScript 路由映射表
# ================================================================

TYPESCRIPT_KEYWORDS = [
    "TypeScript", "tsconfig.json", "interface ", "type ",
    "tsc ", ".tsx", ".ts ", "ts-jest", "type annotation",
    "Generics", "enum ",
]

# ================================================================
# Python 路由映射表
# ================================================================

PYTHON_KEYWORDS = [
    "Python", "Django", "Flask", "FastAPI", "pytest",
    "def ", "import ", "from ", "__init__", "pip ",
    "requirements.txt",
]