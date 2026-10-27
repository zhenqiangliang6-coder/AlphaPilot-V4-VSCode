# test_fileops_execution.ps1
# Test FileOps Execution Link

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "FileOps Execution Link Test" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Node API
Write-Host "[1/4] Checking Node API..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/workspace/set" -Method Post -Body '{"path":"C:\\Test"}' -ContentType "application/json" -ErrorAction Stop
    Write-Host "PASS: Node API is running" -ForegroundColor Green
} catch {
    Write-Host "FAIL: Node API not started" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 2. Test workspace setup
Write-Host "[2/4] Testing workspace setup..." -ForegroundColor Yellow
$workspacePath = (Get-Location).Path
try {
    $body = @{path=$workspacePath} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "http://localhost:3000/workspace/set" -Method Post -Body $body -ContentType "application/json"
    Write-Host "PASS: Workspace set to: $($response.workspace)" -ForegroundColor Green
} catch {
    Write-Host "FAIL: Workspace setup failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 3. Test FileOps execution
Write-Host "[3/4] Testing FileOps execution..." -ForegroundColor Yellow
$testFileOps = @(
    @{op="create"; path="test_hello.py"; content="def greet():`n    return 'Hello'"},
    @{op="create"; path="docs/test.md"; content="# Test"}
)

try {
    $body = @{file_ops=$testFileOps} | ConvertTo-Json -Depth 10
    $response = Invoke-RestMethod -Uri "http://localhost:3000/fileops/execute" -Method Post -Body $body -ContentType "application/json"
    
    if ($response.success) {
        Write-Host "PASS: FileOps executed successfully" -ForegroundColor Green
        Write-Host "   Files generated:" -ForegroundColor Cyan
        foreach ($file in $response.files) {
            Write-Host "      - $($file.path)" -ForegroundColor White
        }
    } else {
        Write-Host "FAIL: FileOps execution failed" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "FAIL: FileOps request failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 4. Verify files
Write-Host "[4/4] Verifying files..." -ForegroundColor Yellow
$testFiles = @("test_hello.py", "docs\test.md")
$allExist = $true

foreach ($file in $testFiles) {
    $fullPath = Join-Path $workspacePath $file
    if (Test-Path $fullPath) {
        Write-Host "PASS: $file exists" -ForegroundColor Green
    } else {
        Write-Host "FAIL: $file not found" -ForegroundColor Red
        $allExist = $false
    }
}
Write-Host ""

# Cleanup
Write-Host "Cleaning up test files..." -ForegroundColor Yellow
foreach ($file in $testFiles) {
    $fullPath = Join-Path $workspacePath $file
    if (Test-Path $fullPath) {
        Remove-Item $fullPath -Force
    }
}
Write-Host ""

# Summary
Write-Host "======================================" -ForegroundColor Cyan
if ($allExist) {
    Write-Host "SUCCESS: All tests passed!" -ForegroundColor Green
} else {
    Write-Host "FAILURE: Some tests failed" -ForegroundColor Red
}
Write-Host "======================================" -ForegroundColor Cyan




