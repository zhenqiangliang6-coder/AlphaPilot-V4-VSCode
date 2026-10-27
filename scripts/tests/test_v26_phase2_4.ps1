# test_v26_phase2_4.ps1
# AlphaPilot v2.6 阶段2-4 集成测试脚本
# 测试 Dual-Persona Engine + Agent Execution Chain + 前端适配

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot v2.6 阶段2-4 集成测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ========================
# 测试1: 验证人格配置模块
# ========================
Write-Host "[测试1] 验证 personas.py 模块..." -ForegroundColor Yellow

try {
    python -c "
import sys
sys.path.insert(0, 'python_worker')
from agents.qwen.personas import get_persona_config, get_all_personas

# 测试工程师人格
engineer = get_persona_config('engineer')
assert 'system_prompt' in engineer
assert engineer['tone'] == 'professional'
print('OK: Engineer persona config correct')

# 测试创作者人格
creator = get_persona_config('creator')
assert creator['tone'] == 'artistic_and_expressive'
print('OK: Creator persona config correct')

# 测试对话人格
conversational = get_persona_config('conversational')
assert conversational['tone'] == 'friendly_and_empathetic'
print('OK: Conversational persona config correct')

# 测试所有人格
all_personas = get_all_personas()
assert len(all_personas) == 3
print(f'OK: Total {len(all_personas)} persona configs')

print('PASS: personas.py module test passed')
"
    Write-Host "✅ 测试1通过: 人格配置模块正常`n" -ForegroundColor Green
} catch {
    Write-Host "❌ 测试1失败: $_`n" -ForegroundColor Red
    exit 1
}

# ========================
# 测试2: 验证 qwen_api.py 人格注入功能
# ========================
Write-Host "[测试2] 验证 qwen_api.py 人格注入功能..." -ForegroundColor Yellow

try {
    python -c "
import sys
sys.path.insert(0, 'python_worker')
from agents.qwen.qwen_api import call_qwen_with_persona
from agents.qwen.personas import get_persona_config

# 测试函数存在性
assert callable(call_qwen_with_persona)
print('OK: call_qwen_with_persona function exists')

# 测试人格配置获取
persona = get_persona_config('engineer')
assert persona is not None
print('OK: Persona config retrieved successfully')

print('PASS: qwen_api.py persona injection test passed')
"
    Write-Host "✅ 测试2通过: qwen_api.py 人格注入功能正常`n" -ForegroundColor Green
} catch {
    Write-Host "❌ 测试2失败: $_`n" -ForegroundColor Red
    exit 1
}

# ========================
# 测试3: 验证步骤执行器人格注入
# ========================
Write-Host "[测试3] 验证步骤执行器人格注入..." -ForegroundColor Yellow

$step_files = @(
    "python_worker/agents/qwen/step_executor/write_step.py",
    "python_worker/agents/qwen/step_executor/analyze_step.py",
    "python_worker/agents/qwen/step_executor/plan_step.py",
    "python_worker/agents/qwen/step_executor/refine_step.py"
)

foreach ($file in $step_files) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        if ($content -match "call_qwen_with_persona") {
            Write-Host "  ✅ $file 已集成人格配置" -ForegroundColor Green
        } else {
            Write-Host "  ❌ $file 未找到人格配置调用" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  ❌ $file 不存在" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ 测试3通过: 所有步骤执行器已集成人格配置`n" -ForegroundColor Green

# ========================
# 测试4: 验证动态步骤生成优化
# ========================
Write-Host "[测试4] 验证动态步骤生成优化..." -ForegroundColor Yellow

try {
    python -c "
import sys
sys.path.insert(0, 'python_worker')
from agents.qwen.qwen_worker_v2 import create_steps_from_chain

# 测试创意写作意图（应跳过 test 步骤）
chain = ['analyze', 'plan', 'write', 'refine', 'test']
steps = create_steps_from_chain(chain, 'write a poem', 'creator', 'creative_writing')
step_types = [s['type'] for s in steps]
assert 'test' not in step_types, 'Creative writing should skip test step'
print(f'OK: Creative writing intent: {len(steps)} steps (skipped test)')

# 测试闲聊意图（只保留 write）
steps_chat = create_steps_from_chain(chain, 'hello', 'conversational', 'chat')
step_types_chat = [s['type'] for s in steps_chat]
assert len(step_types_chat) == 1 and step_types_chat[0] == 'write', 'Chat should only keep write'
print(f'OK: Chat intent: {len(steps_chat)} steps (only write)')

# 测试代码生成意图（保留所有步骤）
steps_code = create_steps_from_chain(chain, 'write a sort algorithm', 'engineer', 'write_code')
step_types_code = [s['type'] for s in steps_code]
assert 'test' in step_types_code, 'Code generation should include test step'
print(f'OK: Code generation intent: {len(steps_code)} steps (full chain)')

print('PASS: Dynamic step generation optimization test passed')
"
    Write-Host "✅ 测试4通过: 动态步骤生成优化正常`n" -ForegroundColor Green
} catch {
    Write-Host "❌ 测试4失败: $_`n" -ForegroundColor Red
    exit 1
}

# ========================
# 测试5: 验证前端组件
# ========================
Write-Host "[测试5] 验证前端组件..." -ForegroundColor Yellow

$frontend_files = @(
    "vscode-extension/webview/src/components/IntentBadge.tsx",
    "vscode-extension/webview/src/components/PersonaIcon.tsx",
    "vscode-extension/webview/src/store/chatStore.ts",
    "vscode-extension/webview/src/App.tsx",
    "vscode-extension/webview/src/components/MessageList.tsx"
)

foreach ($file in $frontend_files) {
    if (Test-Path $file) {
        Write-Host "  ✅ $file 存在" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $file 不存在" -ForegroundColor Red
        exit 1
    }
}

# 检查 chatStore 是否包含 intent/persona 字段
$chatstore_content = Get-Content "vscode-extension/webview/src/store/chatStore.ts" -Raw
if ($chatstore_content -match "intent\?:\s*string" -and $chatstore_content -match "persona\?:\s*string") {
    Write-Host "  ✅ chatStore.ts 包含 intent/persona 字段" -ForegroundColor Green
} else {
    Write-Host "  ❌ chatStore.ts 缺少 intent/persona 字段" -ForegroundColor Red
    exit 1
}

# 检查 MessageList 是否导入新组件
$messagelist_content = Get-Content "vscode-extension/webview/src/components/MessageList.tsx" -Raw
if ($messagelist_content -match "IntentBadge" -and $messagelist_content -match "PersonaIcon") {
    Write-Host "  ✅ MessageList.tsx 已集成 IntentBadge 和 PersonaIcon" -ForegroundColor Green
} else {
    Write-Host "  ❌ MessageList.tsx 未集成新组件" -ForegroundColor Red
    exit 1
}

Write-Host "✅ 测试5通过: 前端组件正常`n" -ForegroundColor Green

# ========================
# 总结
# ========================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "All tests passed!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Phase 2: Dual-Persona Engine Integration Complete" -ForegroundColor Green
Write-Host "   - qwen_api.py supports persona config injection" -ForegroundColor Gray
Write-Host "   - 4 step executors integrated with persona config" -ForegroundColor Gray
Write-Host ""

Write-Host "Phase 3: Agent Execution Chain Optimization Complete" -ForegroundColor Green
Write-Host "   - Dynamic step generation supports smart skipping" -ForegroundColor Gray
Write-Host "   - Different intents auto-adjust step combinations" -ForegroundColor Gray
Write-Host ""

Write-Host "Phase 4: Frontend Adaptation Complete" -ForegroundColor Green
Write-Host "   - IntentBadge component displays intent labels" -ForegroundColor Gray
Write-Host "   - PersonaIcon component displays persona icons" -ForegroundColor Gray
Write-Host "   - MessageList integrated with new components" -ForegroundColor Gray
Write-Host ""

Write-Host "Next step: Run full system test to verify end-to-end flow" -ForegroundColor Yellow
Write-Host "Command: .\start_all.ps1`n" -ForegroundColor Cyan
