const PROTOCOL_VERSION = '1.0';

class TaskProtocolError extends Error {
  constructor(message) {
    super(message);
    this.name = 'TaskProtocolError';
  }
}

function normalizeTaskSubmission(body, createId) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new TaskProtocolError('Task submission must be an object');
  }

  const protocolVersion = body.protocol_version;
  if (protocolVersion !== undefined && protocolVersion !== PROTOCOL_VERSION) {
    throw new TaskProtocolError(`Unsupported task protocol version: ${protocolVersion}`);
  }

  const { type, payload } = body;
  if (typeof type !== 'string' || !type.trim()) {
    throw new TaskProtocolError('Task type must be a non-empty string');
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new TaskProtocolError('Task payload must be an object');
  }
  const requiresPrompt = type === 'task.generate' || type.endsWith('_generate');
  if (requiresPrompt && (typeof payload.prompt !== 'string' || !payload.prompt.trim())) {
    throw new TaskProtocolError('Task payload must include a non-empty prompt');
  }
  if (payload.prompt !== undefined && typeof payload.prompt !== 'string') {
    throw new TaskProtocolError('Task prompt must be a string when provided');
  }
  if (
    payload.context !== undefined &&
    (!payload.context || typeof payload.context !== 'object' || Array.isArray(payload.context))
  ) {
    throw new TaskProtocolError('Task context must be an object when provided');
  }
  if (payload.workspace_path !== undefined && typeof payload.workspace_path !== 'string') {
    throw new TaskProtocolError('workspace_path must be a string when provided');
  }

  const traceId = body.trace_id === undefined ? createId() : body.trace_id;
  if (typeof traceId !== 'string' || !traceId.trim() || traceId.length > 128) {
    throw new TaskProtocolError('trace_id must be a non-empty string of at most 128 characters');
  }
  if (
    body.source !== undefined &&
    (typeof body.source !== 'string' || !body.source.trim())
  ) {
    throw new TaskProtocolError('source must be a non-empty string when provided');
  }
  if (
    body.meta !== undefined &&
    (!body.meta || typeof body.meta !== 'object' || Array.isArray(body.meta))
  ) {
    throw new TaskProtocolError('meta must be an object when provided');
  }

  return {
    protocol_version: PROTOCOL_VERSION,
    trace_id: traceId,
    type,
    payload,
    source: body.source === undefined ? 'vscode-plugin' : body.source,
    meta: body.meta === undefined ? {} : body.meta
  };
}

module.exports = { PROTOCOL_VERSION, TaskProtocolError, normalizeTaskSubmission };
