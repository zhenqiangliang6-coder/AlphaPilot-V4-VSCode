# smoke_tests/definitions/P4_expert_roles.py
"""Phase 2.4: 编程专家角色测试体系 — 5 大专家 × 10 题 = 50 题

架构信条（来自 python_worker/CHANGELOG.md 核心宪法）：
  Worker = 真相 | Extension = 映射 | Webview = 投影 | 协议 = 宪法

设计原则：
  - 每个Worker只接收自己领域的题，验证领域专长
  - 上层LLM检测语言 → 动态路由到对应Worker
  - 自然语言 + 专业术语，中等偏上难度
  - 单任务 + 多任务混合
"""

# ══════════════════════════════════════════════════════════════
#  Role 1: Python 编程专家 (Python Worker → queue:qwen_py)
#  领域：数据处理、Web框架、pytest、asyncio、CLI工具
# ══════════════════════════════════════════════════════════════

PYTHON_EXPERT_TESTS = [
    # ── 单任务 (6 题) ──
    {
        "id": "PY-001",
        "label": "data_pipeline",
        "prompt": (
            "编写一个Python模块 data_pipeline.py，实现CSV文件的读取、去重（按指定列）、"
            "聚合统计（count/sum/avg）功能。使用dataclass定义数据结构，使用pathlib处理路径，"
            "使用csv模块读写。包含完整的类型注解。"
        ),
        "verify_files": ["data_pipeline.py"],
        "verify_code": ["import csv", "from dataclasses import dataclass", "def ", "Path"],
        "task_type": "single",
    },
    {
        "id": "PY-002",
        "label": "fastapi_auth",
        "prompt": (
            "创建FastAPI路由模块 auth_router.py，实现JWT认证中间件。"
            "包含 /login 端点（返回access_token）、/logout 端点、"
            "以及一个受保护的 /me 端点（需要Bearer token验证）。"
            "使用pydantic BaseModel定义请求/响应模型，使用python-jose处理JWT。"
        ),
        "verify_files": ["auth_router.py"],
        "verify_code": ["from fastapi import", "APIRouter", "BaseModel", "jwt", "Bearer"],
        "task_type": "single",
    },
    {
        "id": "PY-003",
        "label": "pytest_suite",
        "prompt": (
            "为现有的 calculator.py 编写完整的pytest测试套件 test_calculator.py。"
            "calculator.py包含 add/subtract/multiply/divide 四个函数。"
            "使用pytest.mark.parametrize进行参数化测试（至少4组数据），"
            "使用pytest.raises测试除零异常，使用fixture管理测试数据。"
            "覆盖正常情况、边界值（0, 负数, 大数）和异常情况。"
        ),
        "verify_files": ["test_calculator.py"],
        "verify_code": ["import pytest", "parametrize", "raises", "fixture", "def test_"],
        "task_type": "single",
    },
    {
        "id": "PY-004",
        "label": "cli_tool",
        "prompt": (
            "编写一个Python命令行工具 git_stats.py，使用argparse解析参数。"
            "功能：统计Git仓库的提交次数、贡献者排名、文件变更统计。"
            "使用subprocess调用 git log --pretty=format 命令解析输出。"
            "支持 --since 和 --until 日期过滤参数。"
            "输出Markdown格式的统计报告。"
        ),
        "verify_files": ["git_stats.py"],
        "verify_code": ["argparse", "subprocess", "git log", "def ", "markdown"],
        "task_type": "single",
    },
    {
        "id": "PY-005",
        "label": "async_scraper",
        "prompt": (
            "使用asyncio和aiohttp实现并发网页爬虫 scraper.py。"
            "要求：使用asyncio.Semaphore限制并发数为10，"
            "使用aiohttp.ClientSession管理连接池，"
            "实现fetch(url)和fetch_all(urls)两个异步函数，"
            "正确处理超时（10s）和HTTP错误状态码（非200）。"
            "返回 {url: status_code, body_length} 的聚合结果。"
        ),
        "verify_files": ["scraper.py"],
        "verify_code": ["asyncio", "aiohttp", "Semaphore", "ClientSession", "async def"],
        "task_type": "single",
    },
    {
        "id": "PY-006",
        "label": "decorator_lib",
        "prompt": (
            "编写Python装饰器库 decorators.py，包含三个装饰器："
            "\n1. @retry(max_attempts=3, backoff=2) — 指数退避重试，捕获指定异常"
            "\n2. @timer — 使用time.perf_counter测量函数执行时间并打印"
            "\n3. @memoize — 使用functools.lru_cache的增强版，支持自定义maxsize"
            "\n使用functools.wraps保留原函数元数据，包含完整docstring。"
        ),
        "verify_files": ["decorators.py"],
        "verify_code": ["functools", "wraps", "def retry", "def timer", "def memoize"],
        "task_type": "single",
    },

    # ── 多任务 (4 题) ──
    {
        "id": "PY-007",
        "label": "refactor_and_test",
        "prompt": (
            "重构现有的 messy_module.py 中的重复代码，提取公共逻辑到工具函数。"
            "要求：消除所有重复代码块（3处以上重复），提取为独立函数，"
            "保持原有API兼容性。编写pytest测试文件 test_messy_module.py "
            "覆盖所有提取后的函数，验证重构前后行为完全一致。"
        ),
        "verify_files": ["messy_module.py", "test_messy_module.py"],
        "verify_code": ["def ", "import pytest", "assert"],
        "task_type": "multi",
    },
    {
        "id": "PY-008",
        "label": "write_and_changelog",
        "prompt": (
            "为用户管理模块添加基于角色的权限检查功能 permission_checker.py。"
            "实现 Role(Enum) 和 PermissionChecker 类，支持 has_permission(user, resource, action) "
            "方法。使用装饰器 @require_permission 做声明式权限控制。"
            "同时更新 CHANGELOG.md 记录本次功能变更，包含变更日期、模块和文件列表。"
        ),
        "verify_files": ["permission_checker.py"],
        "verify_code": ["Enum", "class", "def ", "permission", "@"],
        "verify_changelog": True,
        "task_type": "multi",
    },
    {
        "id": "PY-009",
        "label": "fix_timezone_and_test",
        "prompt": (
            "修复 report_generator.py 中的时区处理bug："
            "当前代码使用datetime.now()导致跨时区时间不一致，"
            "应该统一使用UTC时间并在输出时转换为本地时区。"
            "使用python-dateutil的pytz或zoneinfo处理时区。"
            "同时补充pytest测试 test_report_generator.py，"
            "验证UTC转换正确性和跨时区一致性。"
        ),
        "verify_files": ["report_generator.py", "test_report_generator.py"],
        "verify_code": ["timezone", "utc", "pytz", "def test_"],
        "task_type": "multi",
    },
    {
        "id": "PY-010",
        "label": "data_lib_with_docs",
        "prompt": (
            "编写Python数据分析工具库 data_lib.py，包含三个类："
            "\n1. DataFrame — 基于字典列表的轻量数据表，支持filter/select/group_by/join"
            "\n2. Series — 一维数据序列，支持map/reduce/rolling窗口操作"
            "\n3. Stats — 描述性统计（mean/median/std/percentile/correlation）"
            "\n要求：完整的Google风格docstring、类型注解（typing模块）、"
            "每个公共方法至少一个使用示例写在docstring中。"
        ),
        "verify_files": ["data_lib.py"],
        "verify_code": ["class DataFrame", "class Series", "class Stats",
                         "Args:", "Returns:", ">>>"],
        "task_type": "multi",
    },
]

# ══════════════════════════════════════════════════════════════
#  Role 2: Java 编程专家 (Java Worker → queue:qwen_java)
#  领域：Spring Boot、JPA/Hibernate、Maven/Gradle、JUnit 5
# ══════════════════════════════════════════════════════════════

JAVA_EXPERT_TESTS = [
    # ── 单任务 (6 题) ──
    {
        "id": "JV-001",
        "label": "spring_controller",
        "prompt": (
            "Create a Spring Boot REST controller UserController.java "
            "with @RestController and @RequestMapping(\"/api/users\"). "
            "Implement CRUD endpoints: GET /{id}, POST /, PUT /{id}, DELETE /{id}. "
            "Use @PathVariable, @RequestBody, @Valid annotations. "
            "Return ResponseEntity with proper HTTP status codes (200/201/404). "
            "Inject UserService via constructor injection."
        ),
        "verify_files": ["UserController.java"],
        "verify_code": ["@RestController", "@RequestMapping", "ResponseEntity",
                         "@PathVariable", "@RequestBody", "UserService"],
        "task_type": "single",
    },
    {
        "id": "JV-002",
        "label": "jpa_repository",
        "prompt": (
            "Create JPA Entity Order.java with @Entity, @Table, @Id, @GeneratedValue. "
            "Fields: Long id, String orderNumber, LocalDateTime createdAt, "
            "BigDecimal totalAmount, OrderStatus status (enum). "
            "Also create OrderRepository.java extending JpaRepository<Order, Long> "
            "with custom query methods: findByStatus, findByCreatedAtBetween, "
            "findTop10ByOrderByTotalAmountDesc. Use @Query for complex queries."
        ),
        "verify_files": ["Order.java", "OrderRepository.java"],
        "verify_code": ["@Entity", "@Table", "JpaRepository", "@Query",
                         "OrderStatus", "enum"],
        "task_type": "single",
    },
    {
        "id": "JV-003",
        "label": "maven_pom",
        "prompt": (
            "Create a Maven pom.xml for a Spring Boot 3.2 project. "
            "Dependencies: spring-boot-starter-web, spring-boot-starter-data-jpa, "
            "spring-boot-starter-validation, postgresql driver, "
            "lombok, junit-jupiter, spring-boot-starter-test. "
            "Configure maven-surefire-plugin for JUnit 5. "
            "Use Java 17 source/target. GroupId: com.alphapilot."
        ),
        "verify_files": ["pom.xml"],
        "verify_code": ["spring-boot-starter-web", "spring-boot-starter-data-jpa",
                         "junit-jupiter", "java.version", "alphapilot"],
        "task_type": "single",
    },
    {
        "id": "JV-004",
        "label": "junit5_suite",
        "prompt": (
            "Write JUnit 5 test class CalculatorTest.java for a Calculator class "
            "with methods: add(int,int), subtract(int,int), multiply(int,int), "
            "divide(int,int) throws IllegalArgumentException. "
            "Use @ParameterizedTest with @CsvSource for multiple inputs. "
            "Use @DisplayName for descriptive test names. "
            "Use assertThrows for divide-by-zero. "
            "Use @BeforeEach to initialize the Calculator instance."
        ),
        "verify_files": ["CalculatorTest.java"],
        "verify_code": ["@ParameterizedTest", "@CsvSource", "@DisplayName",
                         "assertThrows", "@BeforeEach", "Calculator"],
        "task_type": "single",
    },
    {
        "id": "JV-005",
        "label": "service_layer",
        "prompt": (
            "Write a Spring @Service class PaymentService.java that handles payment processing. "
            "Use @Transactional annotation for database operations. "
            "Implement: processPayment(PaymentRequest), refund(Long paymentId), "
            "getPaymentStatus(Long paymentId). "
            "Inject PaymentRepository and NotificationService via constructor. "
            "Throw custom PaymentException for invalid amounts or duplicate transactions. "
            "Use Optional<Payment> for repository lookups."
        ),
        "verify_files": ["PaymentService.java"],
        "verify_code": ["@Service", "@Transactional", "PaymentRepository",
                         "Optional", "PaymentException", "class"],
        "task_type": "single",
    },
    {
        "id": "JV-006",
        "label": "builder_pattern",
        "prompt": (
            "Implement the Builder pattern in Java using Lombok @Builder on a "
            "CustomerDTO.java class. Fields: Long id, String firstName, "
            "String lastName, String email, LocalDate birthDate, "
            "List<Address> addresses (inner Address class with street/city/zip). "
            "Add @JsonProperty annotations for JSON serialization. "
            "Add @NotNull/@Size bean validation annotations. "
            "Include a manual builder method toAddressString() that formats "
            "the primary address."
        ),
        "verify_files": ["CustomerDTO.java"],
        "verify_code": ["@Builder", "@JsonProperty", "@NotNull", "@Size",
                         "class Address", "String"],
        "task_type": "single",
    },

    # ── 多任务 (4 题) ──
    {
        "id": "JV-007",
        "label": "write_compile_and_test",
        "prompt": (
            "Write a Java utility class StringUtils.java with static methods: "
            "reverse(String), countVowels(String), isPalindrome(String), "
            "camelToSnake(String). Use streams for processing where appropriate. "
            "Also write StringUtilsTest.java with JUnit 5 parameterized tests "
            "covering edge cases (null, empty string, special characters, unicode)."
        ),
        "verify_files": ["StringUtils.java", "StringUtilsTest.java"],
        "verify_code": ["public static", "return", "class StringUtils",
                         "@ParameterizedTest", "assert"],
        "task_type": "multi",
    },
    {
        "id": "JV-008",
        "label": "dto_and_mapper",
        "prompt": (
            "Create UserEntity.java (JPA entity) and UserDTO.java (data transfer object). "
            "Entity has: id, username, email, passwordHash, createdAt, isActive. "
            "DTO has: id, username, email, createdAt (no password field). "
            "Write UserMapper.java with static methods toDTO(UserEntity) and "
            "toEntity(UserDTO) using manual mapping (no MapStruct/ModelMapper). "
            "Handle null inputs gracefully returning Optional.empty()."
        ),
        "verify_files": ["UserEntity.java", "UserDTO.java", "UserMapper.java"],
        "verify_code": ["@Entity", "class UserDTO", "class UserMapper",
                         "Optional", "static"],
        "task_type": "multi",
    },
    {
        "id": "JV-009",
        "label": "exception_handler",
        "prompt": (
            "Write a global exception handler GlobalExceptionHandler.java "
            "using @ControllerAdvice. Handle: "
            "\n1. ResourceNotFoundException → 404 with error details"
            "\n2. ValidationException (MethodArgumentNotValidException) → 400 with field errors"
            "\n3. DuplicateResourceException → 409 Conflict"
            "\n4. Generic Exception → 500 Internal Server Error"
            "\nReturn a consistent ErrorResponse.java DTO with timestamp, status, "
            "error message, and path. Use @ExceptionHandler for each type."
        ),
        "verify_files": ["GlobalExceptionHandler.java", "ErrorResponse.java"],
        "verify_code": ["@ControllerAdvice", "@ExceptionHandler",
                         "ErrorResponse", "ResponseEntity", "class"],
        "task_type": "multi",
    },
    {
        "id": "JV-010",
        "label": "security_config",
        "prompt": (
            "Write Spring Security configuration class SecurityConfig.java. "
            "Configure: JWT authentication filter chain, stateless session management, "
            "CORS configuration (allow localhost:3000), CSRF disabled for API, "
            "permitAll for /api/auth/** and /actuator/health, "
            "authenticated for /api/** paths. "
            "Use SecurityFilterChain bean (lambda DSL, not deprecated WebSecurityConfigurerAdapter). "
            "Inject JwtAuthFilter and UserDetailsService."
        ),
        "verify_files": ["SecurityConfig.java"],
        "verify_code": ["@Configuration", "@EnableWebSecurity", "SecurityFilterChain",
                         "JwtAuthFilter", "CORS", "csrf"],
        "task_type": "multi",
    },
]

# ══════════════════════════════════════════════════════════════
#  Role 3: JavaScript 编程专家 (Node Worker → queue:qwen_node)
#  领域：Express、async/await、EventEmitter、Stream、npm
# ══════════════════════════════════════════════════════════════

JAVASCRIPT_EXPERT_TESTS = [
    # ── 单任务 (6 题) ──
    {
        "id": "JS-001",
        "label": "express_crud_api",
        "prompt": (
            "Create an Express.js REST API server server.js that manages a "
            "products catalog with in-memory storage. "
            "Routes: GET /api/products (list with ?category filter), "
            "GET /api/products/:id, POST /api/products (validate body), "
            "PUT /api/products/:id, DELETE /api/products/:id. "
            "Use express.json() middleware. Return proper HTTP status codes. "
            "Include error handling middleware for invalid JSON and 404s. "
            "Export the app (not listen) for testing."
        ),
        "verify_files": ["server.js"],
        "verify_code": ["express", "app.get", "app.post", "app.put",
                         "app.delete", "module.exports"],
        "task_type": "single",
    },
    {
        "id": "JS-002",
        "label": "async_file_processor",
        "prompt": (
            "Write a Node.js module file_processor.js using fs/promises. "
            "Export async functions: "
            "processFiles(dirPath) — reads all .txt files in directory, "
            "counts words, and returns {filename: wordCount} map. "
            "mergeFiles(inputPaths[], outputPath) — concatenates files "
            "with separator headers. "
            "watchDirectory(dirPath, callback) — uses fs.watch to notify "
            "on file changes with debouncing (300ms). "
            "Handle ENOENT, EACCES errors gracefully."
        ),
        "verify_files": ["file_processor.js"],
        "verify_code": ["fs/promises", "async ", "await", "readdir",
                         "Promise.all", "module.exports"],
        "task_type": "single",
    },
    {
        "id": "JS-003",
        "label": "event_emitter_logger",
        "prompt": (
            "Create a custom Logger class extending EventEmitter in logger.js. "
            "Emit events: 'log' with {level, message, timestamp}, "
            "'error' with {error, stack}, 'warn' with {message}. "
            "Methods: log(level, message), error(err), warn(msg), info(msg), debug(msg). "
            "Support log level filtering (DEBUG < INFO < WARN < ERROR). "
            "Add a file transport that writes to a log file when 'log' event fires. "
            "Export the Logger class."
        ),
        "verify_files": ["logger.js"],
        "verify_code": ["EventEmitter", "extends", "this.emit",
                         "class Logger", "module.exports"],
        "task_type": "single",
    },
    {
        "id": "JS-004",
        "label": "npm_package",
        "prompt": (
            "Create a publishable npm package module string_kit.js that exports "
            "string utility functions: "
            "camelCase(str), snakeCase(str), kebabCase(str), "
            "pascalCase(str), titleCase(str), truncate(str, maxLen, suffix). "
            "Also create package.json with name 'string-kit', version 1.0.0, "
            "main entry point, keywords, and jest test script. "
            "Use regular expressions for case conversions. "
            "Handle edge cases: empty string, non-string input."
        ),
        "verify_files": ["string_kit.js", "package.json"],
        "verify_code": ["module.exports", "regex", "replace",
                         "function ", "\"name\":", "\"main\":"],
        "task_type": "single",
    },
    {
        "id": "JS-005",
        "label": "stream_transform",
        "prompt": (
            "Implement a Transform stream csv_to_json.js that converts CSV input "
            "to JSON array output. "
            "Extend stream.Transform, parse CSV headers from first line, "
            "map each row to {header: value} objects. "
            "Handle quoted fields (with commas inside quotes), "
            "escape double-quotes (\"\"), trim whitespace. "
            "Emit 'error' for malformed CSV. "
            "Export a factory function createCsvToJsonTransform()."
        ),
        "verify_files": ["csv_to_json.js"],
        "verify_code": ["stream", "Transform", "_transform",
                         "csv", "json", "module.exports"],
        "task_type": "single",
    },
    {
        "id": "JS-006",
        "label": "promise_pool",
        "prompt": (
            "Write a concurrency limiter promise_pool.js that exports "
            "async function promisePool(tasks, concurrency). "
            "tasks is an array of async functions. Execute at most "
            "<concurrency> tasks simultaneously. When one finishes, "
            "start the next. Return array of results in original order. "
            "If any task rejects, stop scheduling new tasks but let "
            "running ones finish, then reject with the first error. "
            "Use only native Promises (no external libs)."
        ),
        "verify_files": ["promise_pool.js"],
        "verify_code": ["async ", "Promise", "concurrency",
                         "module.exports", "function "],
        "task_type": "single",
    },

    # ── 多任务 (4 题) ──
    {
        "id": "JS-007",
        "label": "validator_and_jest",
        "prompt": (
            "Write a Node.js validator module validator.js that validates: "
            "email (RFC 5322 simplified), URL (with protocol), "
            "phone number (international format), credit card (Luhn algorithm), "
            "IP address (v4 and v6), and date string (ISO 8601). "
            "Each function returns {valid: boolean, message: string}. "
            "Also write jest test suite validator.test.js with describe/it blocks, "
            "covering at least 3 valid and 3 invalid cases per validator. "
            "Target >80% branch coverage."
        ),
        "verify_files": ["validator.js", "validator.test.js"],
        "verify_code": ["module.exports", "describe(", "it(", "expect(",
                         "valid:", "regex"],
        "task_type": "multi",
    },
    {
        "id": "JS-008",
        "label": "refactor_callback_to_async",
        "prompt": (
            "Refactor the callback-style data_fetcher.js to use async/await. "
            "Original uses Node.js callback pattern: fetchUser(id, callback), "
            "fetchOrders(userId, callback) with nested callbacks for "
            "fetchUserWithOrders(id, callback). "
            "Rewrite as: fetchUser(id) → Promise<User>, "
            "fetchOrders(userId) → Promise<Order[]>, "
            "fetchUserWithOrders(id) using Promise.all. "
            "Add proper error handling with try/catch and custom DataFetchError. "
            "Keep backward compatibility by exporting both styles."
        ),
        "verify_files": ["data_fetcher.js"],
        "verify_code": ["async ", "await", "Promise", "try", "catch",
                         "module.exports", "class DataFetchError"],
        "task_type": "multi",
    },
    {
        "id": "JS-009",
        "label": "express_middleware_suite",
        "prompt": (
            "Create an Express application app.js with a complete middleware stack: "
            "\n1. requestId middleware — assign UUID to each request"
            "\n2. requestLogger middleware — log method, url, duration, status"
            "\n3. rateLimiter middleware — 100 requests per minute per IP (in-memory)"
            "\n4. errorHandler middleware — catch errors, return JSON {error, requestId}"
            "\n5. cors middleware — allow specific origins"
            "\nCreate a demo route GET /api/health that returns {status, uptime, requestId}. "
            "Write jest test app.test.js using supertest to test all middleware behaviors. "
            "Create package.json with dependencies: express, uuid, jest, supertest."
        ),
        "verify_files": ["app.js", "app.test.js", "package.json"],
        "verify_code": ["app.use", "middleware", "next()", "describe(",
                         "supertest", "uuid"],
        "task_type": "multi",
    },
    {
        "id": "JS-010",
        "label": "ws_chat_with_changelog",
        "prompt": (
            "Write a WebSocket chat server chat_server.js using the 'ws' library. "
            "Features: broadcast messages to all clients, @username private messages, "
            "join/leave room notifications, message history (last 100), "
            "heartbeat ping/pong with 30s timeout to detect dead connections. "
            "Export ChatServer class with start(port) and stop() methods. "
            "Include a CHANGELOG.md entry documenting this new feature addition."
        ),
        "verify_files": ["chat_server.js"],
        "verify_code": ["WebSocket", "class ChatServer", "broadcast",
                         "ping", "pong", "ws"],
        "verify_changelog": True,
        "task_type": "multi",
    },
]

# ══════════════════════════════════════════════════════════════
#  Role 4: TypeScript 编程专家 (TS Worker → queue:qwen_ts)
#  领域：类型系统、泛型、React、装饰器、类型守卫
# ══════════════════════════════════════════════════════════════

TYPESCRIPT_EXPERT_TESTS = [
    # ── 单任务 (6 题) ──
    {
        "id": "TS-001",
        "label": "result_type",
        "prompt": (
            "Write a TypeScript module result.ts implementing Result<T, E> type "
            "(similar to Rust's Result). "
            "Types: Ok<T> with {ok: true, value: T}, Err<E> with {ok: false, error: E}. "
            "Functions: ok<T>(value: T): Result<T, never>, "
            "err<E>(error: E): Result<never, E>. "
            "Methods on Result: map(fn), flatMap(fn), orElse(defaultValue), "
            "unwrap() throws if Err, unwrapOr(defaultValue). "
            "Use discriminated unions, never type, and strict mode."
        ),
        "verify_files": ["result.ts"],
        "verify_code": ["export type", "Result<T", "Ok<T>", "Err<E>",
                         "never", "map(", "flatMap("],
        "task_type": "single",
    },
    {
        "id": "TS-002",
        "label": "generic_utilities",
        "prompt": (
            "Implement a TypeScript generic utility type library utils.ts containing: "
            "\n1. DeepPartial<T> — recursively make all properties optional"
            "\n2. PickByValue<T, V> — pick keys whose values extend V"
            "\n3. ReadonlyDeep<T> — recursively make all properties readonly"
            "\n4. NonNullableKeys<T> — pick only non-nullable keys"
            "\n5. FunctionKeys<T> — pick only keys that are functions"
            "\nInclude unit tests using tsd (assert-type) style comments "
            "demonstrating each utility type works correctly."
        ),
        "verify_files": ["utils.ts"],
        "verify_code": ["export type DeepPartial", "export type PickByValue",
                         "ReadonlyDeep", "NonNullableKeys", "FunctionKeys",
                         "extends"],
        "task_type": "single",
    },
    {
        "id": "TS-003",
        "label": "react_datatable",
        "prompt": (
            "Write a TypeScript React component DataTable.tsx with generic row type. "
            "Props: data: T[], columns: Column<T>[], pageSize?: number, "
            "onSort?: (key: keyof T, dir: 'asc'|'desc') => void. "
            "Column type: {key: keyof T, header: string, render?: (val: T[key]) => ReactNode, "
            "sortable?: boolean}. "
            "Features: client-side pagination, column sorting (click header to toggle), "
            "striped rows, empty state message, responsive wrapper. "
            "Use useState, useMemo, React.memo. Export as default."
        ),
        "verify_files": ["DataTable.tsx"],
        "verify_code": ["interface", "<T", "React", "useState", "useMemo",
                         "keyof", "export default"],
        "task_type": "single",
    },
    {
        "id": "TS-004",
        "label": "type_guards",
        "prompt": (
            "Write a TypeScript type guard module guards.ts with the following "
            "user-defined type guard functions: "
            "\n1. isStringArray(value: unknown): value is string[]"
            "\n2. isRecord(value: unknown): value is Record<string, unknown>"
            "\n3. hasKey<T, K extends string>(obj: T, key: K): obj is T & Record<K, unknown>"
            "\n4. isNonEmptyArray<T>(arr: T[]): arr is [T, ...T[]]"
            "\n5. isValidDate(value: unknown): value is Date"
            "\n6. isEnumValue<E>(value: unknown, enumObj: E): value is E[keyof E]"
            "\nEach guard must properly narrow types in if-blocks. Include JSDoc examples."
        ),
        "verify_files": ["guards.ts"],
        "verify_code": ["export function", "is ", "value is",
                         "unknown", "type guard", "keyof"],
        "task_type": "single",
    },
    {
        "id": "TS-005",
        "label": "decorators",
        "prompt": (
            "Implement TypeScript decorators (experimental) in decorators.ts: "
            "\n1. @LogMethod — log method name, args, return value, duration"
            "\n2. @Cache(ttlMs: number) — cache method results in a Map with TTL"
            "\n3. @ValidateParams(schema: ZodSchema) — validate arguments before invocation"
            "\n4. @Debounce(delayMs: number) — debounce method calls"
            "\nUse reflect-metadata for metadata storage where needed. "
            "Enable experimentalDecorators in tsconfig. Include proper type signatures "
            "using TypeScript's decorator type definitions."
        ),
        "verify_files": ["decorators.ts"],
        "verify_code": ["export function", "decorator", "PropertyDescriptor",
                         "reflect", "Map", "TTL"],
        "task_type": "single",
    },
    {
        "id": "TS-006",
        "label": "async_result",
        "prompt": (
            "Write a TypeScript module async_result.ts that combines async/await "
            "with Result type for railway-oriented error handling. "
            "Types: AsyncResult<T, E> = Promise<Result<T, E>>. "
            "Functions: "
            "\n1. asyncOk<T>(promise: Promise<T>): AsyncResult<T, never>"
            "\n2. asyncErr<E>(promise: Promise<E>): AsyncResult<never, E>"
            "\n3. fromPromise<T>(promise: Promise<T>): AsyncResult<T, Error>"
            "\n4. flatMapAsync<T, U, E>(result: AsyncResult<T,E>, fn: (t:T) => AsyncResult<U,E>)"
            "\n5. retry<T>(fn: () => Promise<T>, maxRetries: number, delayMs: number)"
            "\nUse generic constraints and proper error propagation."
        ),
        "verify_files": ["async_result.ts"],
        "verify_code": ["export type AsyncResult", "Promise<Result",
                         "async function", "fromPromise", "retry",
                         "flatMapAsync"],
        "task_type": "single",
    },

    # ── 多任务 (4 题) ──
    {
        "id": "TS-007",
        "label": "priority_queue_typed",
        "prompt": (
            "Write a TypeScript generic PriorityQueue.ts class. "
            "Generic: PriorityQueue<T> with constructor taking "
            "comparator: (a: T, b: T) => number. "
            "Methods: enqueue(item: T), dequeue(): T | undefined, "
            "peek(): T | undefined, size: number, isEmpty(): boolean, "
            "toArray(): T[]. "
            "Implement using a binary heap (array-based). "
            "Also write tests/priority_queue.test.ts using jest + ts-jest. "
            "Also create tsconfig.json with strict mode enabled. "
            "The complete project must pass tsc --noEmit and jest."
        ),
        "verify_files": ["PriorityQueue.ts", "tests/priority_queue.test.ts", "tsconfig.json"],
        "verify_code": ["class PriorityQueue<T>", "comparator", "binary heap",
                         "enqueue", "dequeue", "strict"],
        "task_type": "multi",
    },
    {
        "id": "TS-008",
        "label": "js_to_ts_migration",
        "prompt": (
            "Migrate the existing JavaScript module math_utils.js to TypeScript "
            "math_utils.ts. The JS module exports: "
            "gcd(a,b), lcm(a,b), isPrime(n), factorial(n), "
            "fibonacci(n), primeFactors(n). "
            "Add complete type annotations, create interfaces for return types "
            "(MathResult {value, computation, duration}). "
            "Create tsconfig.json with strict, noImplicitAny, strictNullChecks. "
            "Write tests/math_utils.test.ts with comprehensive jest tests. "
            "The migration must produce zero type errors with tsc --noEmit."
        ),
        "verify_files": ["math_utils.ts", "tsconfig.json", "tests/math_utils.test.ts"],
        "verify_code": ["export function", ": number", "interface",
                         "strict", "describe(", "expect("],
        "task_type": "multi",
    },
    {
        "id": "TS-009",
        "label": "event_bus_typed",
        "prompt": (
            "Write a type-safe EventBus.ts in TypeScript. "
            "Support typed event map: EventBus<Events extends Record<string, any>>. "
            "Methods: on<K extends keyof Events>(event: K, handler: (data: Events[K]) => void): void, "
            "off<K>(event: K, handler): void, emit<K>(event: K, data: Events[K]): void, "
            "once<K>(event: K, handler): void. "
            "Include an index.ts barrel export. "
            "Update CHANGELOG.md documenting this new EventBus module. "
            "Write tests/event_bus.test.ts testing type safety scenarios "
            "(different event types with different payload shapes)."
        ),
        "verify_files": ["EventBus.ts", "index.ts", "tests/event_bus.test.ts"],
        "verify_code": ["class EventBus<Events", "Record<string",
                         "keyof Events", "emit(", "on(", "off("],
        "verify_changelog": True,
        "task_type": "multi",
    },
    {
        "id": "TS-010",
        "label": "fix_any_types",
        "prompt": (
            "Fix the data_mapper.ts file that currently uses 'any' types throughout. "
            "The mapper converts between API response DTOs and domain models. "
            "Current: function mapResponse(data: any): any. "
            "Required: "
            "\n1. Define proper interfaces: ApiResponse<T>, DomainModel, UserDTO, User"
            "\n2. Create generic mapper: mapApiResponse<T, U>(data: ApiResponse<T>, mapper: (t: T) => U): U"
            "\n3. Implement specific mappers: mapUser, mapOrder, mapProduct"
            "\n4. Add runtime validation using type guards before mapping"
            "\n5. Write tests/data_mapper.test.ts with both valid and invalid inputs"
            "\nFinal code must have zero 'any' types and pass tsc --strict."
        ),
        "verify_files": ["data_mapper.ts", "tests/data_mapper.test.ts"],
        "verify_code": ["interface", "export function", "<T", "<U>",
                         "is ", "type guard", "expect("],
        "task_type": "multi",
    },
]

# ══════════════════════════════════════════════════════════════
#  Role 5: 系统工程专家 (Python Worker, 复合意图 + 跨语言协调)
#  领域：代码分析、Git操作、Shell执行、CHANGELOG管理、多语言项目
# ══════════════════════════════════════════════════════════════

SYSTEM_EXPERT_TESTS = [
    # ── 单任务 (4 题：操作型能力) ──
    {
        "id": "SY-001",
        "label": "code_analysis",
        "prompt": (
            "分析当前项目的代码结构和依赖关系。"
            "统计Python文件数量、总代码行数、空白行数和注释行数。"
            "列出所有import的第三方库及其使用次数。"
            "输出Markdown格式的代码健康度报告。"
        ),
        "verify_files": [],
        "verify_code": ["import", "count", "lines", "statistics"],
        "intent": "execute_operation",
        "task_type": "single",
    },
    {
        "id": "SY-002",
        "label": "git_commit_and_push",
        "prompt": (
            "将当前项目的所有变更暂存（git add -A）、"
            "提交（自动生成有意义的commit message）并推送到GitHub。"
            "推送前检查是否有敏感文件（.env, *.pem, secrets.*）"
        ),
        "verify_files": [],
        "verify_code": [],
        "intent": "execute_operation",
        "task_type": "single",
    },
    {
        "id": "SY-003",
        "label": "environment_check",
        "prompt": (
            "检测系统开发环境：Python版本（需>=3.11）、"
            "Node.js版本（需>=18），npm/yarn/pnpm可用性，"
            "Docker是否安装并运行，MySQL/PostgreSQL可用性。"
            "输出JSON格式的环境兼容性报告，标注每个组件的状态（available/unavailable）。"
        ),
        "verify_files": [],
        "verify_code": [],
        "intent": "execute_operation",
        "task_type": "single",
    },
    {
        "id": "SY-004",
        "label": "dependency_audit",
        "prompt": (
            "审计当前Python项目的依赖安全性。"
            "解析 requirements.txt 或 pyproject.toml 中的依赖列表，"
            "检查是否有已知漏洞（CVE）的包版本，"
            "检查是否有过期的直接依赖（与PyPI最新版本对比），"
            "输出审计报告包含：安全风险（高/中/低）、过期依赖建议升级版本。"
        ),
        "verify_files": [],
        "verify_code": [],
        "intent": "execute_operation",
        "task_type": "single",
    },

    # ── 多任务 (6 题：复合意图) ──
    {
        "id": "SY-005",
        "label": "write_changelog_push",
        "prompt": (
            "为项目的REST API模块添加健康检查端点 health_check.py。"
            "功能：检查数据库连接、Redis连接、磁盘空间。"
            "返回 JSON {status: 'healthy'|'degraded'|'unhealthy', checks: {...}}。"
            "使用FastAPI或Flask适配现有架构。"
            "完成后更新CHANGELOG.md记录新增的健康检查功能。"
            "最后将变更提交并推送到GitHub。"
        ),
        "verify_files": ["health_check.py"],
        "verify_code": ["def ", "status", "healthy", "check_"],
        "verify_changelog": True,
        "intent": "write_code",
        "compound": True,
        "task_type": "multi",
    },
    {
        "id": "SY-006",
        "label": "refactor_changelog_push",
        "prompt": (
            "重构 config_loader.py 消除所有硬编码配置值。"
            "将硬编码的数据库URL、API密钥、超时时间等移到环境变量或配置文件。"
            "支持 .env 文件和系统环境变量两层配置（dotenv优先）。"
            "保持原有API兼容性——已有的调用方不需要修改。"
            "更新CHANGELOG.md记录重构变更。"
            "将变更提交并推送到GitHub。"
        ),
        "verify_files": ["config_loader.py"],
        "verify_code": ["os.environ", "getenv", "load_dotenv", "def "],
        "verify_changelog": True,
        "intent": "refactor",
        "compound": True,
        "task_type": "multi",
    },
    {
        "id": "SY-007",
        "label": "write_test_and_push",
        "prompt": (
            "编写Python LRU缓存装饰器 cache_decorator.py。"
            "支持 @cached(maxsize=128, ttl_seconds=300) 参数。"
            "使用OrderedDict实现LRU淘汰，使用time.monotonic实现TTL过期。"
            "线程安全（使用threading.Lock）。"
            "编写pytest测试 test_cache_decorator.py 覆盖："
            "缓存命中/未命中、TTL过期、LRU淘汰、线程安全。"
            "将代码推送到GitHub。"
        ),
        "verify_files": ["cache_decorator.py", "test_cache_decorator.py"],
        "verify_code": ["OrderedDict", "monotonic", "threading.Lock",
                         "def cached", "def test_"],
        "intent": "write_code",
        "compound": True,
        "task_type": "multi",
    },
    {
        "id": "SY-008",
        "label": "fix_docs_push",
        "prompt": (
            "修复 rate_limiter.py 中滑动窗口算法在高并发下的竞态条件bug。"
            "当前实现使用 time.time() + list 导致检查-清除之间存在窗口。"
            "修复方案：使用Redis有序集合（Sorted Set）实现精确的滑动窗口。"
            "若无Redis可用，使用threading.Lock + deque 作为本地回退方案。"
            "更新函数docstring为Google风格，添加使用示例。"
            "更新CHANGELOG.md，然后将修复推送到GitHub。"
        ),
        "verify_files": ["rate_limiter.py"],
        "verify_code": ["redis", "Sorted", "Lock", "deque", "def "],
        "verify_changelog": True,
        "intent": "fix_code",
        "compound": True,
        "task_type": "multi",
    },
    {
        "id": "SY-009",
        "label": "fullstack_coordination",
        "prompt": (
            "协调构建一个数据分析管道："
            "\n1. Python端 data_analyzer.py：使用pandas读取CSV数据，"
            "执行数据清洗（去重、缺失值填充）、聚合统计，"
            "输出JSON格式的分析结果为 analysis_result.json。"
            "\n2. Node.js端 report_server.js：Express服务读取 analysis_result.json，"
            "提供 GET /api/summary 和 GET /api/details 端点返回JSON数据。"
            "\n两端各自包含测试文件（pytest / jest）。"
            "\n编写 start_pipeline.py 作为编排脚本，按顺序启动两个服务。"
        ),
        "verify_files": ["data_analyzer.py", "report_server.js", "start_pipeline.py"],
        "verify_code": ["pandas", "DataFrame", "express", "app.get",
                         "subprocess", "jest"],
        "intent": "write_code",
        "compound": True,
        "cross_language": True,
        "task_type": "multi",
    },
    {
        "id": "SY-010",
        "label": "multilang_logging",
        "prompt": (
            "在项目中添加统一日志系统，跨越Python和Node.js边界："
            "\n1. Python模块 logger.py：使用logging模块，输出JSON格式日志，"
            "支持文件轮转（RotatingFileHandler），5MB/文件，保留3个备份。"
            "日志格式：{timestamp, level, module, message, extra}。"
            "\n2. Node.js模块 log_forwarder.js：使用winston库，"
            "读取Python生成的JSON日志，转发到统一日志文件，"
            "支持日志级别过滤和环境变量配置。"
            "\n3. 共享配置 log_config.json：定义日志级别、输出路径、格式模板。"
            "\n两者写入统一的日志目录 logs/。更新CHANGELOG.md。"
        ),
        "verify_files": ["logger.py", "log_forwarder.js", "log_config.json"],
        "verify_code": ["logging", "RotatingFileHandler", "winston",
                         "json", "level", "module.exports"],
        "verify_changelog": True,
        "intent": "write_code",
        "compound": True,
        "cross_language": True,
        "task_type": "multi",
    },
]

# ══════════════════════════════════════════════════════════════
#  Role → Worker 路由映射
# ══════════════════════════════════════════════════════════════

ROLE_CONFIG = {
    "python_expert": {
        "role_name": "Python 编程专家",
        "worker": "python_worker",
        "queue": "queue:qwen_py",
        "language": "python",
        "test_count": 10,
        "tests": PYTHON_EXPERT_TESTS,
    },
    "java_expert": {
        "role_name": "Java 编程专家",
        "worker": "java_worker",
        "queue": "queue:qwen_java",
        "language": "java",
        "test_count": 10,
        "tests": JAVA_EXPERT_TESTS,
    },
    "javascript_expert": {
        "role_name": "JavaScript 编程专家",
        "worker": "node_worker",
        "queue": "queue:qwen_node",
        "language": "javascript",
        "test_count": 10,
        "tests": JAVASCRIPT_EXPERT_TESTS,
    },
    "typescript_expert": {
        "role_name": "TypeScript 编程专家",
        "worker": "ts_worker",
        "queue": "queue:qwen_ts",
        "language": "typescript",
        "test_count": 10,
        "tests": TYPESCRIPT_EXPERT_TESTS,
    },
    "system_expert": {
        "role_name": "系统工程专家",
        "worker": "python_worker",
        "queue": "queue:qwen_py",
        "language": "python",
        "test_count": 10,
        "tests": SYSTEM_EXPERT_TESTS,
    },
}

# ══════════════════════════════════════════════════════════════
#  测试统计
# ══════════════════════════════════════════════════════════════

TOTAL_QUESTIONS = sum(len(role["tests"]) for role in ROLE_CONFIG.values())

ALL_ROLES = list(ROLE_CONFIG.keys())