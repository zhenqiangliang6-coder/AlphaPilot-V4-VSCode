# run_e2e_quick.ps1
# JS/TS Worker E2E 快速测试 — 各 5 题，直接调用 Qwen API
# 用法: cd D:\Copilot_Alphapilot\Copilot_Alphapilot; .\smoke_tests\run_e2e_quick.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot

# ── 获取 API Key ──
$apiKey = (python -c "import sys; sys.path.insert(0,'$ROOT'); from python_worker.worker_config import DASHSCOPE_API_KEY; print(DASHSCOPE_API_KEY)")
if (-not $apiKey) { Write-Host "[FATAL] DASHSCOPE_API_KEY not found!" -ForegroundColor Red; exit 1 }

# ── 5 道 JS 测试题 ──
$jsTests = @(
    @{
        id="JS-001"; label="express_crud_api"
        prompt="Create an Express.js REST API server server.js that manages a products catalog with in-memory storage. Routes: GET /api/products (list with ?category filter), GET /api/products/:id, POST /api/products (validate body), PUT /api/products/:id, DELETE /api/products/:id. Use express.json() middleware. Return proper HTTP status codes. Include error handling middleware for invalid JSON and 404s. Export the app (not listen) for testing."
        verify=@("server.js")
    },
    @{
        id="JS-004"; label="npm_package"
        prompt="Create a publishable npm package module string_kit.js that exports string utility functions: camelCase(str), snakeCase(str), kebabCase(str), pascalCase(str), titleCase(str), truncate(str, maxLen, suffix). Also create package.json with name 'string-kit', version 1.0.0, main entry point, keywords, and jest test script. Use regular expressions for case conversions. Handle edge cases: empty string, non-string input."
        verify=@("string_kit.js", "package.json")
    },
    @{
        id="JS-003"; label="event_emitter_logger"
        prompt="Create a custom Logger class extending EventEmitter in logger.js. Emit events: 'log' with {level, message, timestamp}, 'error' with {error, stack}, 'warn' with {message}. Methods: log(level, message), error(err), warn(msg), info(msg), debug(msg). Support log level filtering (DEBUG < INFO < WARN < ERROR). Add a file transport that writes to a log file when 'log' event fires. Export the Logger class."
        verify=@("logger.js")
    },
    @{
        id="JS-002"; label="async_file_processor"
        prompt="Write a Node.js module file_processor.js using fs/promises. Export async functions: processFiles(dirPath) — reads all .txt files in directory, counts words, and returns {filename: wordCount} map. mergeFiles(inputPaths[], outputPath) — concatenates files with separator headers. watchDirectory(dirPath, callback) — uses fs.watch to notify on file changes with debouncing (300ms). Handle ENOENT, EACCES errors gracefully."
        verify=@("file_processor.js")
    },
    @{
        id="JS-006"; label="promise_pool"
        prompt="Write a concurrency limiter promise_pool.js that exports async function promisePool(tasks, concurrency). tasks is an array of async functions. Execute at most <concurrency> tasks simultaneously. When one finishes, start the next. Return array of results in original order. If any task rejects, stop scheduling new tasks but let running ones finish, then reject with the first error. Use only native Promises (no external libs)."
        verify=@("promise_pool.js")
    }
)

# ── 5 道 TS 测试题 ──
$tsTests = @(
    @{
        id="TS-001"; label="result_type"
        prompt="Write a TypeScript module result.ts implementing Result<T, E> type (similar to Rust's Result). Types: Ok<T> with {ok: true, value: T}, Err<E> with {ok: false, error: E}. Functions: ok<T>(value: T): Result<T, never>, err<E>(error: E): Result<never, E>. Methods on Result: map(fn), flatMap(fn), orElse(defaultValue), unwrap() throws if Err, unwrapOr(defaultValue). Use discriminated unions, never type, and strict mode."
        verify=@("result.ts")
    },
    @{
        id="TS-004"; label="type_guards"
        prompt="Write a TypeScript type guard module guards.ts with the following user-defined type guard functions: 1. isStringArray(value: unknown): value is string[] 2. isRecord(value: unknown): value is Record<string, unknown> 3. hasKey<T, K extends string>(obj: T, key: K): obj is T & Record<K, unknown> 4. isNonEmptyArray<T>(arr: T[]): arr is [T, ...T[]] 5. isValidDate(value: unknown): value is Date 6. isEnumValue<E>(value: unknown, enumObj: E): value is E[keyof E]. Each guard must properly narrow types in if-blocks. Include JSDoc examples."
        verify=@("guards.ts")
    },
    @{
        id="TS-002"; label="generic_utilities"
        prompt="Implement a TypeScript generic utility type library utils.ts containing: 1. DeepPartial<T> — recursively make all properties optional. 2. PickByValue<T, V> — pick keys whose values extend V. 3. ReadonlyDeep<T> — recursively make all properties readonly. 4. NonNullableKeys<T> — pick only non-nullable keys. 5. FunctionKeys<T> — pick only keys that are functions. Include unit tests using tsd (assert-type) style comments demonstrating each utility type works correctly."
        verify=@("utils.ts")
    },
    @{
        id="TS-006"; label="async_result"
        prompt="Write a TypeScript module async_result.ts that combines async/await with Result type for railway-oriented error handling. Types: AsyncResult<T, E> = Promise<Result<T, E>>. Functions: 1. asyncOk<T>(promise: Promise<T>): AsyncResult<T, never> 2. asyncErr<E>(promise: Promise<E>): AsyncResult<never, E> 3. fromPromise<T>(promise: Promise<T>): AsyncResult<T, Error> 4. flatMapAsync<T, U, E>(result, fn) 5. retry<T>(fn, maxRetries, delayMs). Use generic constraints and proper error propagation."
        verify=@("async_result.ts")
    },
    @{
        id="TS-005"; label="decorators"
        prompt="Implement TypeScript decorators (experimental) in decorators.ts: 1. @LogMethod — log method name, args, return value, duration. 2. @Cache(ttlMs: number) — cache method results in a Map with TTL. 3. @ValidateParams(schema: ZodSchema) — validate arguments before invocation (skip zod, use simple runtime check). 4. @Debounce(delayMs: number) — debounce method calls. Enable experimentalDecorators in tsconfig. Include proper type signatures using TypeScript's decorator type definitions."
        verify=@("decorators.ts")
    }
)

# ── 构建测试脚本模板 ──
function Build-TestScript {
    param($test, $sandbox, $workerDir)
    $promptEscaped = $test.prompt -replace "'", "\'" -replace "`n", "\n" -replace '"', '\"'
    $verifyArray = ($test.verify | ForEach-Object { "'$_'" }) -join ", "
  $ws = $sandbox -replace '\\', '\\'
    return @"
const fs = require('fs');
const path = require('path');
const sandbox = process.env.SMOKE_TEST_WORKSPACE || '$ws';
fs.mkdirSync(path.join(sandbox, 'src'), { recursive: true });
fs.mkdirSync(path.join(sandbox, 'tests'), { recursive: true });

(async () => {
  const t0 = Date.now();
  const mod = await import('./qwen_worker.js');
  const worker = new mod.QwenWorker(
    {
      on: () => ({}), lpush: async () => 1, lrange: async () => [],
      del: async () => 1, setex: async () => 'OK', get: async () => null,
      keys: async () => [], rpoplpush: async () => null,
      blPop: async () => null, publish: async () => 1,
    },
    { workerQueue: 'q', resultChannel: 'r', language: '${test.id.StartsWith("JS") ? "javascript" : "typescript"}' }
  );
  await worker.executeTask({
    task_id: '${test.id.ToLower()}',
    payload: { prompt: "${promptEscaped}", workspace_path: sandbox, task_context: { language: '${test.id.StartsWith("JS") ? "javascript" : "typescript"}' } },
  });
  const dur = ((Date.now() - t0) / 1000).toFixed(1);
  const verifyFiles = [${verifyArray}];
  function findFile(dir, name) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) { const r = findFile(full, name); if (r) return r; }
      else if (e.name === name) return full;
    }
    return null;
  }
  let missing = 0;
  for (const f of verifyFiles) {
    const found = fs.existsSync(path.join(sandbox, f)) ? path.join(sandbox, f) : findFile(sandbox, f);
    if (!found) { console.log('  MISSING: ' + f); missing++; }
    else { const sz = fs.statSync(found).size; const rel = path.relative(sandbox, found); console.log('  OK: ' + rel + ' (' + sz + 'B)'); }
  }
  console.log(missing === 0 ? 'E2E_RESULT: PASS' : 'E2E_RESULT: PARTIAL (${dur}s)');
  process.exit(missing === 0 ? 0 : 1);
})().catch(e => { console.log('E2E_RESULT: FAIL — ' + e.message); process.exit(1); });
"@
}

# ── 执行 ──
$totalJS = 0; $passJS = 0
$totalTS = 0; $passTS = 0

Write-Host "`n══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  JS/TS Worker E2E 快速测试 (各 5 题)"
Write-Host "  实时 Qwen API | 每道题 ~30-90s"
Write-Host "══════════════════════════════════════════════`n" -ForegroundColor Cyan

# ── JavaScript Worker ──
Write-Host "── JavaScript Worker ──" -ForegroundColor Yellow
$jsWorkerDir = Join-Path $ROOT "node_worker"
foreach ($test in $jsTests) {
    $sandbox = Join-Path $env:TEMP "e2e-$($test.id)-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path (Join-Path $sandbox "src") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $sandbox "tests") | Out-Null
    $script = Build-TestScript $test $sandbox $jsWorkerDir
    Write-Host "  [$($test.id)] $($test.label) ... " -NoNewline
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $env:DASHSCOPE_API_KEY = $apiKey
    $env:SMOKE_TEST_WORKSPACE = $sandbox
    Push-Location $jsWorkerDir
    $output = node -e $script 2>&1
    $exitCode = $LASTEXITCODE
    Pop-Location

    $sw.Stop()
    $totalJS++
    if ($exitCode -eq 0) {
        $passJS++
        Write-Host "PASS ($([math]::Round($sw.Elapsed.TotalSeconds,1))s)" -ForegroundColor Green
    } else {
        $errLines = ($output | Select-Object -Last 3) -join ' | '
        Write-Host "FAIL ($([math]::Round($sw.Elapsed.TotalSeconds,1))s) — $errLines" -ForegroundColor Red
    }
    Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue
}

# ── TypeScript Worker ──
Write-Host "`n── TypeScript Worker ──" -ForegroundColor Blue
$tsWorkerDir = Join-Path $ROOT "ts_worker"
foreach ($test in $tsTests) {
    $sandbox = Join-Path $env:TEMP "e2e-$($test.id)-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path (Join-Path $sandbox "src") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $sandbox "tests") | Out-Null
    $script = Build-TestScript $test $sandbox $tsWorkerDir
    Write-Host "  [$($test.id)] $($test.label) ... " -NoNewline
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $env:DASHSCOPE_API_KEY = $apiKey
    $env:SMOKE_TEST_WORKSPACE = $sandbox
    Push-Location $tsWorkerDir
    $output = node -e $script 2>&1
    $exitCode = $LASTEXITCODE
    Pop-Location

    $sw.Stop()
    $totalTS++
    if ($exitCode -eq 0) {
        $passTS++
        Write-Host "PASS ($([math]::Round($sw.Elapsed.TotalSeconds,1))s)" -ForegroundColor Green
    } else {
        $errLines = ($output | Select-Object -Last 3) -join ' | '
        Write-Host "FAIL ($([math]::Round($sw.Elapsed.TotalSeconds,1))s) — $errLines" -ForegroundColor Red
    }
    Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue
}

# ── 结果 ──
Write-Host "`n══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  JS Worker:  $passJS / $totalJS PASS" -ForegroundColor $(if ($passJS -eq $totalJS) { "Green" } else { "Red" })
Write-Host "  TS Worker:  $passTS / $totalTS PASS" -ForegroundColor $(if ($passTS -eq $totalTS) { "Green" } else { "Red" })
Write-Host "══════════════════════════════════════════════`n" -ForegroundColor Cyan