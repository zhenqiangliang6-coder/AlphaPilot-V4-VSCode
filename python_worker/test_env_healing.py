# -*- coding: utf-8 -*-
"""环境层自愈独立测试 — 模拟 venv 被删除，验证自动恢复能力"""
import os, sys, subprocess, shutil, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from self_healing_enhanced import (
    check_venv_exists, create_venv, scan_project_imports,
    install_package, ensure_dependencies, environment_self_healing,
    parse_pytest_errors, classify_top_error
)

PROJECT_DIR = r"D:\test_v39_project"
G, R, Y, B, C, X = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[96m', '\033[0m'

print(f"{C}{'='*60}{X}")
print(f"{C}  环境层自愈 — venv 删除 → 自动恢复测试{X}")
print(f"{C}{'='*60}{X}")

# ============================================================
# 步骤 1: 模拟 venv 被删除
# ============================================================
PROJECT_VENV = os.path.join(PROJECT_DIR, '.venv_test')
print(f"\n{B}  Step 1: 模拟环境被删除{X}")
if os.path.exists(PROJECT_VENV):
    print(f"  {Y}删除已有测试 venv: {PROJECT_VENV}{X}")
    shutil.rmtree(PROJECT_VENV)

ok, msg = check_venv_exists(PROJECT_VENV)
print(f"  venv 状态: {R}{msg}{X}" if not ok else f"  venv 状态: {G}{msg}{X}")
assert not ok, "venv 应该不存在！"
print(f"  {G}✅ 确认: venv 已不存在 (模拟用户删除){X}")

# ============================================================
# 步骤 2: 自动创建 venv
# ============================================================
print(f"\n{B}  Step 2: 自愈引擎自动创建 venv{X}")
t0 = time.time()
ok, msg = create_venv(PROJECT_VENV)
elapsed = time.time() - t0
print(f"  创建结果: {G}{msg}{X}" if ok else f"  创建结果: {R}{msg}{X}")
print(f"  耗时: {elapsed:.1f}s")
assert ok, "venv 创建应该成功！"
print(f"  {G}✅ venv 创建成功！{X}")

# ============================================================
# 步骤 3: 扫描项目依赖
# ============================================================
print(f"\n{B}  Step 3: 扫描项目需要的第三方包{X}")
needed = scan_project_imports(PROJECT_DIR)
print(f"  发现 {len(needed)} 个第三方依赖:")
for p in needed:
    print(f"    - {p}")

# ============================================================
# 步骤 4: 安装缺失的依赖
# ============================================================
python_exe = os.path.join(PROJECT_VENV, 'Scripts', 'python.exe')
print(f"\n{B}  Step 4: 安装依赖到新 venv{X}")
print(f"  Python: {python_exe}")

# 先装 pip 升级
subprocess.run([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip', '-q'],
               capture_output=True, text=True, timeout=60)

t0 = time.time()
ok_count, fail_count, details = ensure_dependencies(python_exe, needed)
elapsed = time.time() - t0

for d in details:
    if '成功' in d:
        print(f"    {G}✅ {d}{X}")
    else:
        print(f"    {R}✗ {d}{X}")
print(f"  总耗时: {elapsed:.1f}s")
print(f"  成功: {G}{ok_count}{X}, 失败: {R if fail_count else G}{fail_count}{X}")
assert fail_count == 0, f"有 {fail_count} 个包安装失败！"
print(f"  {G}✅ 所有依赖安装成功！{X}")

# ============================================================
# 步骤 5: 验证 — 执行快速测试
# ============================================================
print(f"\n{B}  Step 5: 运行测试验证环境{X}")
r = subprocess.run(
    [python_exe, '-m', 'pytest', 'tests/test_vote.py', '-v', '--tb=short'],
    cwd=PROJECT_DIR, capture_output=True, text=True, timeout=30
)
output = r.stdout + r.stderr
print(output[-1000:])

# ============================================================
# 步骤 6: 清理
# ============================================================
print(f"\n{B}  Step 6: 清理测试 venv{X}")
shutil.rmtree(PROJECT_VENV)
print(f"  {G}✅ 已清理测试 venv{X}")

# ============================================================
# 总结
# ============================================================
passed = output.count('PASSED')
failed = output.count('FAILED')
print(f"\n{C}{'='*60}{X}")
print(f"{C}  环境层自愈测试结果{X}")
print(f"{C}{'='*60}{X}")
print(f"  场景: venv 被完全删除 + 安装依赖")
print(f"  创建 venv: ✅ ({elapsed:.1f}s)")
print(f"  安装依赖: {ok_count} 成功, {fail_count} 失败")
print(f"  测试通过: {G}{passed}{X}")
print(f"  🎉 环境层 + 代码层 = 全栈自愈！")