const assert = require('node:assert/strict');
const test = require('node:test');
const {
  TASK_STATE_PENDING,
  TASK_STATE_RUNNING,
  TASK_STATE_COMPLETED,
  TASK_STATE_FAILED,
  TASK_STATE_WAITING_AUTHORIZATION,
  TASK_STATE_VALUES,
  TASK_STATE_TO_STATUS,
  resolveStatus,
} = require('./taskStateContract');

// ================================================================
// T1: 缺少 status 和 task_state → 不得默认成功
// ================================================================

test('T1: both fields missing → invalid, not defaulted to done', () => {
  const resolved = resolveStatus({});
  assert.equal(resolved.valid, false, 'empty result must be invalid');
  assert.equal(resolved.status, null, 'status must be null, not "done"');
  assert.ok(resolved.violations.length > 0, 'must have violations');
  assert.ok(
    resolved.violations.some(v => v.field === 'task_state|status'),
    'must report both fields missing'
  );
});

test('T1b: null result → invalid', () => {
  const resolved = resolveStatus(null);
  assert.equal(resolved.valid, false);
});

test('T1c: undefined result → invalid', () => {
  const resolved = resolveStatus(undefined);
  assert.equal(resolved.valid, false);
});

// ================================================================
// T2: task_state = COMPLETED → 映射为 done（成功兼容状态）
// ================================================================

test('T2: task_state COMPLETED without status → maps to done', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_COMPLETED });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'done');
  assert.ok(resolved.warnings.some(w => w.field === 'status'), 'should warn about missing status');
});

test('T2b: task_state COMPLETED with matching status → clean', () => {
  const resolved = resolveStatus({
    task_state: TASK_STATE_COMPLETED,
    status: 'done',
  });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'done');
  assert.equal(resolved.violations.length, 0);
  assert.equal(resolved.warnings.length, 0);
});

// ================================================================
// T3: task_state = FAILED → 映射为 error（失败兼容状态）
// ================================================================

test('T3: task_state FAILED without status → maps to error', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_FAILED });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'error');
});

test('T3b: task_state FAILED with matching status → clean', () => {
  const resolved = resolveStatus({
    task_state: TASK_STATE_FAILED,
    status: 'error',
  });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'error');
  assert.equal(resolved.violations.length, 0);
});

// ================================================================
// T4: WAITING_AUTHORIZATION → 保持等待授权语义
// ================================================================

test('T4: task_state WAITING_AUTHORIZATION → maps to awaiting_authorization', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_WAITING_AUTHORIZATION });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'awaiting_authorization');
});

test('T4b: WAITING_AUTHORIZATION is NOT mapped to done', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_WAITING_AUTHORIZATION });
  assert.notEqual(resolved.status, 'done');
});

test('T4c: WAITING_AUTHORIZATION is NOT mapped to error', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_WAITING_AUTHORIZATION });
  assert.notEqual(resolved.status, 'error');
});

// ================================================================
// T5: 未知 task_state → 拒绝或隔离，不得冒充成功
// ================================================================

test('T5: unknown task_state → invalid', () => {
  const resolved = resolveStatus({ task_state: 'BOGUS_STATE' });
  assert.equal(resolved.valid, false);
  assert.equal(resolved.status, null);
  assert.ok(
    resolved.violations.some(v => v.field === 'task_state'),
    'must report unknown task_state'
  );
});

// ================================================================
// T6: task_state 与 status 冲突 → 契约违规，不得静默放行
// ================================================================

test('T6: task_state COMPLETED vs status error → violation', () => {
  const resolved = resolveStatus({
    task_state: TASK_STATE_COMPLETED,
    status: 'error',
  });
  assert.equal(resolved.valid, false);
  assert.equal(resolved.status, null);
  assert.ok(
    resolved.violations.some(v => v.field === 'status'),
    'must report status mismatch'
  );
});

test('T6b: task_state FAILED vs status done → violation', () => {
  const resolved = resolveStatus({
    task_state: TASK_STATE_FAILED,
    status: 'done',
  });
  assert.equal(resolved.valid, false);
});

test('T6c: task_state COMPLETED vs status pending → violation', () => {
  const resolved = resolveStatus({
    task_state: TASK_STATE_COMPLETED,
    status: 'pending',
  });
  assert.equal(resolved.valid, false);
});

// ================================================================
// T7: 旧 Worker 仅提供合法 status → 保持兼容
// ================================================================

test('T7: only status "done" → valid, infers COMPLETED', () => {
  const resolved = resolveStatus({ status: 'done' });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'done');
  assert.ok(
    resolved.warnings.some(w => w.field === 'task_state'),
    'should warn about missing task_state'
  );
});

test('T7b: only status "error" → valid', () => {
  const resolved = resolveStatus({ status: 'error' });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'error');
});

test('T7c: only status "pending" → valid', () => {
  const resolved = resolveStatus({ status: 'pending' });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'pending');
});

// ================================================================
// T8: RUNNING → pending（非终态映射正确）
// ================================================================

test('T8: task_state RUNNING → maps to pending (non-terminal)', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_RUNNING });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'pending');
});

test('T8b: task_state PENDING → maps to pending', () => {
  const resolved = resolveStatus({ task_state: TASK_STATE_PENDING });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'pending');
});

// ================================================================
// T9: 常量一致性 — 与 Python 契约对齐
// ================================================================

test('T9: all defined task_state values are in VALUES set', () => {
  assert.ok(TASK_STATE_VALUES.has(TASK_STATE_PENDING));
  assert.ok(TASK_STATE_VALUES.has(TASK_STATE_RUNNING));
  assert.ok(TASK_STATE_VALUES.has(TASK_STATE_COMPLETED));
  assert.ok(TASK_STATE_VALUES.has(TASK_STATE_FAILED));
  assert.ok(TASK_STATE_VALUES.has(TASK_STATE_WAITING_AUTHORIZATION));
});

test('T9b: TASK_STATE_TO_STATUS covers all known states', () => {
  for (const state of TASK_STATE_VALUES) {
    assert.ok(
      state in TASK_STATE_TO_STATUS,
      `${state} must have a status mapping`
    );
  }
});

test('T9c: valid state constants match Python contract values', () => {
  assert.equal(TASK_STATE_COMPLETED, 'COMPLETED');
  assert.equal(TASK_STATE_FAILED, 'FAILED');
  assert.equal(TASK_STATE_WAITING_AUTHORIZATION, 'WAITING_AUTHORIZATION');
  assert.equal(TASK_STATE_RUNNING, 'RUNNING');
  assert.equal(TASK_STATE_PENDING, 'PENDING');
});

// ================================================================
// T10: status "completed" → backward-compatible alias
// ================================================================

test('T10: status "completed" with task_state COMPLETED → valid, mapped to done', () => {
  const resolved = resolveStatus({
    task_state: TASK_STATE_COMPLETED,
    status: 'completed',
  });
  assert.equal(resolved.valid, true);
  assert.equal(resolved.status, 'done');
  assert.ok(
    resolved.warnings.some(w =>
      w.field === 'status' && w.message.includes('compatibility')
    ),
    'should warn about compatibility alias'
  );
});