# test_intent_router_v26.ps1
# AlphaPilot v2.6 Intent Router Quick Validation Test Script

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlphaPilot v2.6 Intent Router Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
Set-Location $projectRoot

# Step 1: Activate virtual environment
Write-Host "[1/3] Activating virtual environment..." -ForegroundColor Yellow

$venvActivate = Join-Path $projectRoot ".venv_worker\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    Write-Host "OK: Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "FAIL: Virtual environment not found" -ForegroundColor Red
    exit 1
}

# Step 2: Run unit tests
Write-Host "`n[2/3] Running unit tests..." -ForegroundColor Yellow

python python_worker/tests/test_intent_router.py

if ($?) {
    Write-Host "`nOK: All unit tests passed!" -ForegroundColor Green
} else {
    Write-Host "`nFAIL: Some tests failed" -ForegroundColor Red
    exit 1
}

# Step 3: Interactive demo
Write-Host "`n[3/3] Interactive Demo" -ForegroundColor Yellow
Write-Host ""
Write-Host "Testing sample inputs:" -ForegroundColor White
Write-Host ""

$testCases = @(
    @{prompt="write a sorting algorithm"; expected="write_code"},
    @{prompt="write a poem about spring"; expected="creative_writing"},
    @{prompt="explain this code"; expected="explain_code"},
    @{prompt="fix this bug"; expected="fix_code"},
    @{prompt="what do you think about AI"; expected="chat"}
)

foreach ($test in $testCases) {
    $prompt = $test.prompt
    $expected = $test.expected
    
    Write-Host "Input: '$prompt'" -ForegroundColor Cyan
    Write-Host "Expected intent: $expected" -ForegroundColor Gray
    
    # Run Python one-liner to test
    $result = python -c "from python_worker.intent_router import IntentRouter; intent, persona, chain = IntentRouter.detect_intent('$prompt'); print(f'{intent}|{persona}|{','.join(chain)}')" 2>&1
    
    if ($result -match "^(?<intent>\w+)\|(?<persona>\w+)\|(?<chain>.+)$") {
        $actualIntent = $Matches.intent
        $persona = $Matches.persona
        $chain = $Matches.chain
        
        if ($actualIntent -eq $expected) {
            Write-Host "Result: OK PASS" -ForegroundColor Green
            Write-Host "  Intent: $actualIntent" -ForegroundColor White
            Write-Host "  Persona: $persona" -ForegroundColor White
            Write-Host "  Chain: $chain" -ForegroundColor White
        } else {
            Write-Host "Result: FAIL (expected: $expected, actual: $actualIntent)" -ForegroundColor Red
        }
    } else {
        Write-Host "Result: ERROR parsing result" -ForegroundColor Red
        Write-Host "Output: $result" -ForegroundColor DarkGray
    }
    
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Intent Router v2.6 Test Completed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Qwen Worker to apply changes" -ForegroundColor White
Write-Host "  2. Test with real tasks in VSCode" -ForegroundColor White
Write-Host "  3. Check console logs for intent detection" -ForegroundColor White
Write-Host ""