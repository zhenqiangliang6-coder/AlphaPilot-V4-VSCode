// node-api/test-confirmationManager.js
// Phase 2.4 P0-4: ConfirmationManager 测试套件
// ================================================================

const { ConfirmationManager, ConfirmationRecord } = require('./confirmationManager');

let pass = 0;
let fail = 0;

function assert(condition, label) {
  if (condition) {
    pass++;
  } else {
    fail++;
    console.error(`  FAIL: ${label}`);
  }
}

function assertOk(fn, label) {
  try {
    fn();
    pass++;
  } catch (e) {
    fail++;
    console.error(`  FAIL: ${label} — ${e.message}`);
  }
}

function assertFail(fn, label) {
  try {
    fn();
    fail++;
    console.error(`  FAIL: ${label} — expected exception but none thrown`);
  } catch (e) {
    pass++;
  }
}

// ================================================================
console.log('\n=== P0-4: 确认创建 ===');
{
  const mgr = new ConfirmationManager();
  const scope = {
    target_project_path: '/workspace/myproj',
    project_mode: 'create_new_project',
    allowed_paths: { read: ['/workspace/myproj'], write: ['/workspace/myproj'], execute: [] },
    estimated_impact: '创建新项目',
  };

  const record = mgr.createConfirmation('task-001', scope, 'hash-abc');
  assert(record.confirmationId.startsWith('confirm_'), 'confirmation ID starts with confirm_');
  assert(record.taskId === 'task-001', 'task ID matches');
  assert(record.status === 'pending', 'initial status is pending');
  assert(record.contextHash === 'hash-abc', 'context hash matches');
  assert(record.expiresAt !== null, 'expires_at is set');
  assert(record.contextSummary.length > 0, 'context_summary is not empty');
}

console.log('\n=== P0-4: 确认生命周期 ===');
{
  const mgr = new ConfirmationManager();
  const scope = {
    target_project_path: '/ws/test',
    project_mode: 'modify_existing_project',
    allowed_paths: { read: ['/ws/test'], write: ['/ws/test'], execute: ['/ws/test'] },
  };
  const record = mgr.createConfirmation('task-life', scope, 'hash-life');

  assert(mgr.hasPendingForTask('task-life'), 'has pending for task');

  const confirmResult = mgr.confirm(record.confirmationId);
  assert(confirmResult.success === true, 'confirm succeeds');
  assert(confirmResult.record.status === 'confirmed', 'status is confirmed');
  assert(confirmResult.record.confirmedAt !== null, 'confirmedAt is set');
  assert(confirmResult.record.usedAt !== null, 'usedAt is set');

  assert(!mgr.hasPendingForTask('task-life'), 'no longer pending after confirm');

  const doubleConfirm = mgr.confirm(record.confirmationId);
  assert(doubleConfirm.success === false, 'double confirm fails');
  assert(doubleConfirm.reason === 'already_confirmed', 'double confirm reason');
}

console.log('\n=== P0-4: 确认拒绝 ===');
{
  const mgr = new ConfirmationManager();
  const scope = { target_project_path: '/ws/deny', project_mode: 'modify_existing_project', allowed_paths: {} };
  const record = mgr.createConfirmation('task-deny', scope, 'hash-deny');

  const denyResult = mgr.deny(record.confirmationId);
  assert(denyResult.success === true, 'deny succeeds');
  assert(denyResult.reason === 'user_denied', 'deny reason');

  const recordAfter = mgr.getById(record.confirmationId);
  assert(recordAfter.status === 'denied', 'status is denied');
  assert(recordAfter.deniedAt !== null, 'deniedAt is set');

  const doubleDeny = mgr.deny(record.confirmationId);
  assert(doubleDeny.success === false, 'double deny fails');
}

console.log('\n=== P0-4: 确认过期 ===');
{
  const mgr = new ConfirmationManager();
  const scope = { target_project_path: '/ws/exp', project_mode: 'modify_existing_project', allowed_paths: {} };
  const pastExpiry = new Date(Date.now() - 1000).toISOString();
  const record = mgr.createConfirmation('task-exp', scope, 'hash-exp');
  record.expiresAt = pastExpiry;

  assert(record.isExpired() === true, 'expired record isExpired returns true');
  assert(record.isUsable() === false, 'expired record isUsable returns false');

  const confirmResult = mgr.confirm(record.confirmationId);
  assert(confirmResult.success === false, 'confirm expired fails');
  assert(confirmResult.reason === 'expired', 'reason is expired');
}

console.log('\n=== P0-4: 不可扩大授权验证 ===');
{
  const mgr = new ConfirmationManager();
  const scope = {
    target_project_path: '/ws/safe',
    project_mode: 'modify_existing_project',
    allowed_paths: { read: ['/ws/safe'], write: ['/ws/safe'], execute: [] },
  };
  const record = mgr.createConfirmation('task-scope', scope, 'hash-scope');
  mgr.confirm(record.confirmationId);

  const sameScope = {
    allowed_paths: { read: ['/ws/safe'], write: ['/ws/safe'], execute: [] },
    project_mode: 'modify_existing_project',
  };
  const result1 = mgr.verifyConfirmationNotExpanded(record.confirmationId, sameScope);
  assert(result1.valid === true, 'same scope is valid');

  const expandedScope = {
    allowed_paths: { read: ['/ws/safe'], write: ['/ws/safe', '/etc'], execute: [] },
    project_mode: 'modify_existing_project',
  };
  const result2 = mgr.verifyConfirmationNotExpanded(record.confirmationId, expandedScope);
  assert(result2.valid === false, 'expanded write scope is rejected');
  assert(result2.reason.includes('scope_expansion'), 'reason mentions scope expansion');

  const extraOpScope = {
    allowed_paths: { read: ['/ws/safe'], write: ['/ws/safe'], execute: ['/ws/safe'] },
    project_mode: 'modify_existing_project',
  };
  const result3 = mgr.verifyConfirmationNotExpanded(record.confirmationId, extraOpScope);
  assert(result3.valid === false, 'extra execute scope is rejected');
}

console.log('\n=== P0-4: 一次性使用验证 ===');
{
  const mgr = new ConfirmationManager();
  const scope = { target_project_path: '/ws/once', project_mode: 'modify_existing_project', allowed_paths: {} };
  const record = mgr.createConfirmation('task-once', scope, 'hash-once');

  assert(record.isUsable(), 'fresh record is usable');
  mgr.confirm(record.confirmationId);
  assert(!record.isUsable(), 'confirmed record is not usable');

  const secondConfirm = mgr.confirm(record.confirmationId);
  assert(secondConfirm.success === false, 'second confirm is rejected');
}

console.log('\n=== P0-4: 上下文摘要生成 ===');
{
  const mgr = new ConfirmationManager();
  const scope = {
    target_project_path: '/workspace/myapp',
    project_mode: 'create_new_project',
    allowed_paths: { read: ['/workspace/myapp'], write: ['/workspace/myapp'], execute: [] },
    estimated_impact: '将在工作区创建全新的项目结构',
  };
  const record = mgr.createConfirmation('task-summary', scope, 'hash-summary');

  const summary = record.contextSummary;
  assert(summary.includes('创建新项目'), 'summary mentions create mode');
  assert(summary.includes('/workspace/myapp'), 'summary includes target path');
  assert(summary.length > 0, 'summary is not empty');
}

console.log('\n=== P0-4: Task 反向索引 ===');
{
  const mgr = new ConfirmationManager();
  const scope = { target_project_path: '/ws/idx', project_mode: 'modify_existing_project', allowed_paths: {} };
  const record = mgr.createConfirmation('task-idx', scope, 'hash-idx');

  const byTask = mgr.getByTaskId('task-idx');
  assert(byTask !== null, 'getByTaskId returns record');
  assert(byTask.confirmationId === record.confirmationId, 'same confirmation ID');
  assert(mgr.getByTaskId('task-nonexistent') === null, 'nonexistent task returns null');
}

console.log('\n=== P0-4: 状态统计 ===');
{
  const mgr = new ConfirmationManager();
  const scope = { target_project_path: '/ws/stats', project_mode: 'modify_existing_project', allowed_paths: {} };

  mgr.createConfirmation('task-s1', scope, 'hash-1');
  const r2 = mgr.createConfirmation('task-s2', scope, 'hash-2');
  mgr.createConfirmation('task-s3', scope, 'hash-3');

  mgr.confirm(r2.confirmationId);

  const stats = mgr.getStats();
  assert(stats.total === 3, '3 total records');
  assert(stats.pending === 2, '2 pending');
  assert(stats.confirmed === 1, '1 confirmed');
}

console.log(`\n==================================================`);
console.log(`Results: ${pass} pass  ${fail} fail  ${pass + fail} total`);
console.log(`==================================================`);

process.exit(fail > 0 ? 1 : 0);