// Runtime validation coverage for test command authorization and completion gates.
const assert = require('node:assert/strict');
const test = require('node:test');
const {
  evaluateStopHook,
  isAllowedTestCommand,
} = require('../out/services/taskLifecycle.js');

test('allows recognized test commands and rejects shell chaining', () => {
  assert.equal(isAllowedTestCommand('python -m pytest'), true);
  assert.equal(isAllowedTestCommand('npm run test:unit'), true);
  assert.equal(isAllowedTestCommand('python -m pytest && whoami'), false);
  assert.equal(isAllowedTestCommand('echo unsafe'), false);
});

test('accepts only clean successful test evidence', () => {
  const cleanEvidence = {
    command: 'python -m pytest',
    exitCode: 0,
    stdout: '3 passed',
    stderr: '',
    timedOut: false,
    repairRounds: 0,
    changedAfterTest: false,
  };
  assert.deepEqual(evaluateStopHook(cleanEvidence), { complete: true, reasons: [] });
  assert.equal(evaluateStopHook({ ...cleanEvidence, exitCode: 1 }).complete, false);
  assert.equal(evaluateStopHook({ ...cleanEvidence, stdout: 'FAILED test_case' }).complete, false);
  assert.equal(evaluateStopHook({ ...cleanEvidence, changedAfterTest: true }).complete, false);
});
