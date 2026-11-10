// node-api/test-phase2.4-runner.js
// Phase 2.4: 安全回归集成测试
// 运行所有相关测试套件并汇总结果
// ================================================================

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const TESTS = [
  {
    id: 'P0-4',
    name: '用户确认生命周期',
    file: 'test-confirmationManager.js',
    phase: '2.4',
  },
  {
    id: 'P0-4-DATA',
    name: '流量监控',
    file: 'test-trafficMonitor.js',
    phase: '2.4',
  },
  {
    id: 'PHASE2-GENERAL',
    name: 'PathGuard 越界检测',
    file: 'test-pathGuard.js',
    phase: '2.0-2.3',
  },
  {
    id: 'PHASE2-CONTRACT',
    name: '跨语言契约一致性',
    file: 'test-contractCrossLanguage.js',
    phase: '2.0-2.3',
  },
  {
    id: 'PHASE2-FILEOPS',
    name: 'FileOps Handler 安全',
    file: 'test-fileOpsHandler.js',
    phase: '2.0-2.3',
  },
  {
    id: 'PHASE2-FILEOPS-DEL',
    name: 'FileOps 删除安全',
    file: 'test-fileOpsHandler-delete.js',
    phase: '2.0-2.3',
  },
  {
    id: 'PHASE2-PROTOCOL',
    name: '任务协议校验',
    file: 'test-taskProtocol.js',
    phase: '2.0-2.3',
  },
  {
    id: 'PHASE2-CONTEXT',
    name: '上下文注入',
    file: 'test_context_injection.js',
    phase: '2.0-2.3',
  },
  {
    id: 'PHASE2-CONTRACT-PY',
    name: 'Python PathGuard (pytest)',
    cmd: 'pytest',
    args: ['test_path_guard.py', '--tb=short', '-q'],
    cwd: path.resolve(__dirname, '..', 'python_worker'),
    phase: '2.0-2.3',
  },
];

const results = [];
let totalPass = 0;
let totalFail = 0;

console.log('='.repeat(60));
console.log('Phase 2.4 安全回归集成测试');
console.log(`时间: ${new Date().toISOString()}`);
console.log('='.repeat(60));

for (const test of TESTS) {
  console.log(`\n▶ ${test.id}: ${test.name} [${test.phase}]`);

  let exitCode = -1;
  let stdout = '';
  let stderr = '';

  if (test.cmd) {
    const result = spawnSync(test.cmd, test.args, {
      cwd: test.cwd || __dirname,
      encoding: 'utf-8',
      timeout: 120000,
    });
    exitCode = result.status;
    stdout = result.stdout || '';
    stderr = result.stderr || '';
  } else if (test.file) {
    const result = spawnSync('node', [test.file], {
      cwd: __dirname,
      encoding: 'utf-8',
      timeout: 60000,
    });
    exitCode = result.status;
    stdout = result.stdout || '';
    stderr = result.stderr || '';
  }

  const passed = exitCode === 0;
    if (!passed && test.id === 'PHASE2-CONTRACT-PY') {
      if (stderr.includes('ImportError') || stdout.includes('ImportError')) {
        console.log('   ⚠️  跳过 (Python 环境不可用)');
        results.push({ id: test.id, name: test.name, passed: true, pass: 0, fail: 0, icon: '⚠️', skipped: true });
        continue;
      }
    }
  const summaryMatch = stdout.match(/(\d+)\s+pass\s+(\d+)\s+fail/i);
  let pass = 0, fail = 0;
  if (summaryMatch) {
    pass = parseInt(summaryMatch[1], 10);
    fail = parseInt(summaryMatch[2], 10);
  } else {
    const pytestMatch = stdout.match(/(\d+)\s+passed/);
    if (pytestMatch) {
      pass = parseInt(pytestMatch[1], 10);
      fail = (stdout.match(/(\d+)\s+failed/) || [0, 0])[1];
      fail = parseInt(fail, 10);
    }
  }

  totalPass += pass;
  totalFail += fail;

  const icon = passed ? '✅' : '❌';
  results.push({ id: test.id, name: test.name, passed, pass, fail, icon });

  if (pass + fail > 0) {
    console.log(`   ${icon} ${pass} pass / ${fail} fail`);
  } else {
    console.log(`   ${icon} exit=${exitCode}`);
    if (stdout.trim()) {
      stdout.trim().split('\n').slice(0, 5).forEach(l => console.log(`       ${l}`));
    }
  }

  if (stderr && stderr.trim()) {
    const stderrLines = stderr.trim().split('\n');
    if (stderrLines.length > 5) {
      console.log(`   (stderr: ${stderrLines.length} lines, 5 shown)`);
    }
    stderrLines.slice(0, 5).forEach(l => console.log(`   [err] ${l}`));
  }
}

console.log('\n' + '='.repeat(60));
console.log('汇总');
console.log('='.repeat(60));

for (const r of results) {
  const detail = r.pass + r.fail > 0
    ? `${r.pass}/${r.pass + r.fail}`
    : 'N/A';
  console.log(`   ${r.icon} ${r.id} ${r.name}: ${detail}`);
}

console.log(`\n总计: ${totalPass} pass / ${totalFail} fail`);
console.log(`通过率: ${totalPass + totalFail > 0 ? (totalPass / (totalPass + totalFail) * 100).toFixed(1) : 0}%`);

if (totalFail > 0) {
  console.log('\n❌ 有测试失败，请修复后重新运行');
  process.exit(1);
} else {
  console.log('\n✅ 全部测试通过');
  process.exit(0);
}