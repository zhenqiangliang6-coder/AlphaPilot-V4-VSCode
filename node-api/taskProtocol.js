const path = require('path');
const crypto = require('crypto');
const os = require('os');

const PROTOCOL_VERSION = '1.0';
const CONTEXT_VERSION = '1.0';

const VALID_PROJECT_MODES = new Set([
  'create_new_project',
  'modify_existing_project',
]);

const VALID_COMPAT_POLICIES = new Set([
  'strict',
  'compat_readonly',
  'none',
]);

class TaskProtocolError extends Error {
  constructor(message) {
    super(message);
    this.name = 'TaskProtocolError';
  }
}

class TaskContextValidationError extends Error {
  constructor(message, reasonCode, field) {
    super(message);
    this.name = 'TaskContextValidationError';
    this.reasonCode = reasonCode || 'UNKNOWN';
    this.field = field || '';
  }
}

function normalizePath(p) {
  if (!p) return '';
  return path.resolve(p).replace(/\\/g, '/');
}

function isPathWithin(child, parent) {
  const nc = normalizePath(child);
  const np = normalizePath(parent);
  if (nc === np) return true;
  if (nc.startsWith(np + '/')) return true;
  return false;
}

function computeContextHash(fields) {
  const obj = {
    allowed_paths: {
      execute: (fields.allowed_paths.execute || []).map(p => normalizePath(p)).sort(),
      read: (fields.allowed_paths.read || []).map(p => normalizePath(p)).sort(),
      write: (fields.allowed_paths.write || []).map(p => normalizePath(p)).sort(),
    },
    authorized_roots: (fields.authorized_roots || []).map(p => normalizePath(p)).sort(),
    project_mode: fields.project_mode || '',
    schema_version: fields.schema_version || '1.0',
    target_project_path: normalizePath(fields.target_project_path || ''),
    workspace_roots: (fields.workspace_roots || []).map(p => normalizePath(p)).sort(),
  };
  function sortKeys(obj) {
    if (Array.isArray(obj)) {
      return obj.map(sortKeys);
    }
    if (obj !== null && typeof obj === 'object') {
      const sorted = {};
      Object.keys(obj).sort().forEach(k => {
        sorted[k] = sortKeys(obj[k]);
      });
      return sorted;
    }
    return obj;
  }
  const canonical = JSON.stringify(sortKeys(obj));
  return crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
}

function normalizeTaskContext(taskContext) {
  if (!taskContext || typeof taskContext !== 'object' || Array.isArray(taskContext)) {
    throw new TaskContextValidationError('task_context must be an object', 'INVALID_TYPE', 'task_context');
  }

  const required = ['context_id', 'workspace_roots', 'authorized_roots', 'allowed_paths',
    'target_project_path', 'project_mode', 'created_at'];
  for (const f of required) {
    if (!(f in taskContext)) {
      throw new TaskContextValidationError(
        `task_context.${f} is required`, 'MISSING_REQUIRED', `task_context.${f}`
      );
    }
  }

  if (!Array.isArray(taskContext.workspace_roots) || taskContext.workspace_roots.some(p => typeof p !== 'string')) {
    throw new TaskContextValidationError('workspace_roots must be a string array', 'INVALID_TYPE', 'task_context.workspace_roots');
  }
  if (taskContext.workspace_roots.length !== 1) {
    throw new TaskContextValidationError(
      'v1 supports exactly one workspace root', 'MULTI_ROOT_NOT_SUPPORTED', 'task_context.workspace_roots'
    );
  }
  if (!Array.isArray(taskContext.authorized_roots) || taskContext.authorized_roots.some(p => typeof p !== 'string')) {
    throw new TaskContextValidationError('authorized_roots must be a string array', 'INVALID_TYPE', 'task_context.authorized_roots');
  }
  if (taskContext.authorized_roots.length === 0) {
    throw new TaskContextValidationError('authorized_roots must not be empty', 'INVALID_VALUE', 'task_context.authorized_roots');
  }

  const wsRoot = taskContext.workspace_roots[0];
  for (const ar of taskContext.authorized_roots) {
    if (!isPathWithin(ar, wsRoot)) {
      throw new TaskContextValidationError(
        `authorized_root ${ar} is not within workspace_root`, 'AUTH_ROOT_OUTSIDE_WORKSPACE', 'task_context.authorized_roots'
      );
    }
  }

  if (typeof taskContext.target_project_path !== 'string' || !taskContext.target_project_path.trim()) {
    throw new TaskContextValidationError(
      'target_project_path must be a non-empty string', 'INVALID_VALUE', 'task_context.target_project_path'
    );
  }

  const mode = taskContext.project_mode;
  if (!VALID_PROJECT_MODES.has(mode)) {
    throw new TaskContextValidationError(
      `project_mode must be one of [${[...VALID_PROJECT_MODES].join(', ')}]`, 'INVALID_ENUM', 'task_context.project_mode'
    );
  }

  const allowed = taskContext.allowed_paths || {};
  for (const domain of ['read', 'write', 'execute']) {
    if (!Array.isArray(allowed[domain])) {
      throw new TaskContextValidationError(
        `allowed_paths.${domain} must be an array`, 'INVALID_TYPE', `task_context.allowed_paths.${domain}`
      );
    }
  }

  const targetPath = path.resolve(taskContext.target_project_path);
  let targetInAuth = false;
  for (const ar of taskContext.authorized_roots) {
    if (isPathWithin(targetPath, ar)) { targetInAuth = true; break; }
  }
  if (!targetInAuth) {
    throw new TaskContextValidationError(
      `target_project_path outside authorized_roots`, 'TARGET_OUTSIDE_AUTH', 'task_context.target_project_path'
    );
  }

  for (const domain of ['read', 'write', 'execute']) {
    for (const p of allowed[domain]) {
      let inAuth = false;
      for (const ar of taskContext.authorized_roots) {
        if (isPathWithin(p, ar)) { inAuth = true; break; }
      }
      if (!inAuth) {
        throw new TaskContextValidationError(
          `allowed_paths.${domain} path outside authorized_roots: ${p}`, 'ALLOWED_PATH_OUTSIDE_AUTH', `task_context.allowed_paths.${domain}`
        );
      }
    }
  }

  const compatPolicy = taskContext.compatibility_policy || 'strict';
  if (compatPolicy !== undefined && !VALID_COMPAT_POLICIES.has(compatPolicy)) {
    throw new TaskContextValidationError(
      `compatibility_policy must be one of [${[...VALID_COMPAT_POLICIES].join(', ')}]`, 'INVALID_ENUM', 'task_context.compatibility_policy'
    );
  }

  const existingHash = taskContext.context_hash || '';
  const computedHash = computeContextHash({
    workspace_roots: taskContext.workspace_roots,
    authorized_roots: taskContext.authorized_roots,
    allowed_paths: allowed,
    target_project_path: targetPath,
    project_mode: mode,
  });
  if (existingHash && existingHash !== computedHash) {
    throw new TaskContextValidationError(
      `context_hash mismatch: expected ${existingHash.slice(0, 16)}..., computed ${computedHash.slice(0, 16)}...`,
      'HASH_MISMATCH', 'task_context.context_hash'
    );
  }

  return {
    context_id: taskContext.context_id,
    workspace_roots: taskContext.workspace_roots,
    authorized_roots: taskContext.authorized_roots,
    allowed_paths: allowed,
    target_project_path: targetPath,
    project_mode: mode,
    created_at: taskContext.created_at,
    schema_version: taskContext.schema_version || '1.0',
    context_hash: existingHash || computedHash,
    compatibility_policy: compatPolicy,
    user_confirmation: taskContext.user_confirmation || null,
  };
}

function buildTaskContext({ contextId, workspaceRoots, authorizedRoots, allowedPaths,
  targetProjectPath, projectMode, createdAt, userConfirmation, compatibilityPolicy }) {

  const ctx = {
    context_id: contextId,
    workspace_roots: workspaceRoots,
    authorized_roots: authorizedRoots,
    allowed_paths: allowedPaths,
    target_project_path: targetProjectPath,
    project_mode: projectMode,
    created_at: createdAt,
    schema_version: '1.0',
    compatibility_policy: compatibilityPolicy || 'strict',
  };

  if (userConfirmation) {
    ctx.user_confirmation = userConfirmation;
  }

  ctx.context_hash = computeContextHash({
    workspace_roots: workspaceRoots,
    authorized_roots: authorizedRoots,
    allowed_paths: allowedPaths,
    target_project_path: targetProjectPath,
    project_mode: projectMode,
  });

  return ctx;
}

function buildCompatTaskContext(workspacePath, contextId, createdAt) {
  const resolved = path.resolve(workspacePath || '');
  const cid = contextId || `compat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const now = createdAt || new Date().toISOString();

  return buildTaskContext({
    contextId: cid,
    workspaceRoots: [resolved],
    authorizedRoots: [resolved],
    allowedPaths: {
      read: [resolved],
      write: [],     // compat_readonly does NOT grant write
      execute: [],   // compat_readonly does NOT grant execute
    },
    targetProjectPath: resolved,
    projectMode: 'modify_existing_project',
    createdAt: now,
    compatibilityPolicy: 'compat_readonly',
  });
}

function buildOrExtractTaskContext(payload) {
  if (payload.task_context && typeof payload.task_context === 'object') {
    return normalizeTaskContext(payload.task_context);
  }

  const wsPath = payload.workspace_path || '';
  if (!wsPath) {
    throw new TaskContextValidationError(
      'No task_context and no workspace_path in payload', 'MISSING_REQUIRED', 'payload.task_context|workspace_path'
    );
  }

  console.warn('[TaskProtocol] task_context missing; building compat_readonly context from workspace_path');
  return buildCompatTaskContext(wsPath);
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
  const hasImages = payload.images && Array.isArray(payload.images) && payload.images.length > 0;
  if (requiresPrompt && !hasImages && (typeof payload.prompt !== 'string' || !payload.prompt.trim())) {
    throw new TaskProtocolError('Task payload must include a non-empty prompt or images');
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

module.exports = {
  PROTOCOL_VERSION,
  CONTEXT_VERSION,
  VALID_PROJECT_MODES,
  VALID_COMPAT_POLICIES,
  TaskProtocolError,
  TaskContextValidationError,
  normalizePath,
  isPathWithin,
  computeContextHash,
  normalizeTaskContext,
  buildTaskContext,
  buildCompatTaskContext,
  buildOrExtractTaskContext,
  normalizeTaskSubmission,
};