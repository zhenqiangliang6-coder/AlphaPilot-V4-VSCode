const assert = require('node:assert/strict');
const test = require('node:test');
const { normalizeTaskSubmission } = require('./taskProtocol');

const fixedId = () => 'generated-trace-id';

test('normalizes versioned generation submissions without changing trace identity', () => {
  const submission = normalizeTaskSubmission({
    protocol_version: '1.0',
    trace_id: 'trace-123',
    type: 'qwen_generate',
    payload: { prompt: 'Build a parser' },
    source: 'vscode-extension'
  }, fixedId);

  assert.equal(submission.protocol_version, '1.0');
  assert.equal(submission.trace_id, 'trace-123');
  assert.equal(submission.payload.prompt, 'Build a parser');
});

test('accepts legacy submissions and assigns protocol metadata', () => {
  const submission = normalizeTaskSubmission({
    type: 'qwen_generate',
    payload: { prompt: 'Legacy request' }
  }, fixedId);

  assert.equal(submission.protocol_version, '1.0');
  assert.equal(submission.trace_id, 'generated-trace-id');
});

test('preserves non-generation payloads without requiring a prompt', () => {
  const submission = normalizeTaskSubmission({
    type: 'cancel_task',
    payload: { task_id: 'task-1' }
  }, fixedId);

  assert.equal(submission.payload.task_id, 'task-1');
});

test('rejects unsupported versions, invalid trace IDs, and empty generation prompts', () => {
  assert.throws(() => normalizeTaskSubmission({
    protocol_version: '2.0',
    type: 'qwen_generate',
    payload: { prompt: 'hello' }
  }, fixedId), /Unsupported task protocol version/);

  assert.throws(() => normalizeTaskSubmission({
    trace_id: '',
    type: 'qwen_generate',
    payload: { prompt: 'hello' }
  }, fixedId), /trace_id/);

  assert.throws(() => normalizeTaskSubmission({
    type: 'qwen_generate',
    payload: { prompt: ' ' }
  }, fixedId), /non-empty prompt/);

  assert.throws(() => normalizeTaskSubmission({
    type: 'qwen_generate',
    payload: { prompt: 'hello', context: [] }
  }, fixedId), /context must be an object/);

  assert.throws(() => normalizeTaskSubmission({
    type: 'qwen_generate',
    payload: { prompt: 'hello' },
    meta: []
  }, fixedId), /meta must be an object/);
});
