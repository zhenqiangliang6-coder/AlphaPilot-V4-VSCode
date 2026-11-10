// node-api/confirmationManager.js
// ================================================================
// Phase 2.4 P0-4: 用户确认管理器
// 确保确认记录不可重放、不可扩大授权、不可跨任务复用
// ================================================================

const crypto = require('crypto');
const { computeContextHash } = require('./taskProtocol');

const DEFAULT_CONFIRMATION_TTL_MS = 5 * 60 * 1000;  // 5 分钟过期

class ConfirmationRecord {
  constructor({
    confirmationId,
    taskId,
    scope,
    contextHash,
    contextSummary,
    expiresAt,
    createdAt,
  }) {
    this.confirmationId = confirmationId;
    this.taskId = taskId;
    this.scope = scope;
    this.contextHash = contextHash;
    this.contextSummary = contextSummary || '';
    this.expiresAt = expiresAt || new Date(Date.now() + DEFAULT_CONFIRMATION_TTL_MS).toISOString();
    this.createdAt = createdAt || new Date().toISOString();
    this.status = 'pending';   // pending | confirmed | denied | expired
    this.confirmedAt = null;
    this.deniedAt = null;
    this.usedAt = null;        // 一次性使用：确认后标记 usedAt，不可再使用
  }

  isExpired() {
    try {
      return new Date() > new Date(this.expiresAt);
    } catch {
      return true;
    }
  }

  isUsable() {
    return this.status === 'pending' && !this.isExpired();
  }

  toDict() {
    return {
      confirmation_id: this.confirmationId,
      task_id: this.taskId,
      scope: this.scope,
      context_hash: this.contextHash,
      context_summary: this.contextSummary,
      expires_at: this.expiresAt,
      created_at: this.createdAt,
      status: this.status,
    };
  }

  toWebviewPayload() {
    const scope = this.scope || {};
    return {
      confirmation_id: this.confirmationId,
      task_id: this.taskId,
      target_path: scope.target_project_path || scope.targetProjectPath || '',
      project_mode: scope.project_mode || scope.projectMode || '',
      allowed_paths: scope.allowed_paths || scope.allowedPaths || { read: [], write: [], execute: [] },
      estimated_impact: scope.estimated_impact || scope.estimatedImpact || '',
      operation_specific: scope.operation_specific || scope.operationSpecific || {},
      context_hash: this.contextHash,
      context_summary: this.contextSummary,
      expires_at: this.expiresAt,
      expires_in_seconds: Math.max(0, Math.floor((new Date(this.expiresAt) - Date.now()) / 1000)),
    };
  }
}

class ConfirmationManager {
  constructor() {
    this._store = new Map();
  }

  createConfirmation(taskId, scope, contextHash) {
    if (!taskId) {
      throw new Error('taskId is required for confirmation');
    }
    const confirmationId = `confirm_${crypto.randomUUID()}`;
    const contextSummary = this._buildContextSummary(scope);

    const record = new ConfirmationRecord({
      confirmationId,
      taskId,
      scope: this._normalizeScope(scope),
      contextHash: contextHash || this._computeScopeHash(scope),
      contextSummary,
    });
    this._store.set(confirmationId, record);
    this._store.set(`task:${taskId}`, confirmationId);  // 反向索引

    this._cleanupExpired();

    return record;
  }

  confirm(confirmationId) {
    const record = this._store.get(confirmationId);
    if (!record) {
      return { success: false, reason: 'confirmation_not_found' };
    }
    if (record.status !== 'pending') {
      return { success: false, reason: `already_${record.status}` };
    }
    if (record.isExpired()) {
      record.status = 'expired';
      return { success: false, reason: 'expired' };
    }

    record.status = 'confirmed';
    record.confirmedAt = new Date().toISOString();
    record.usedAt = new Date().toISOString();
    return { success: true, record };
  }

  deny(confirmationId) {
    const record = this._store.get(confirmationId);
    if (!record) {
      return { success: false, reason: 'confirmation_not_found' };
    }
    if (record.status !== 'pending') {
      return { success: false, reason: `already_${record.status}` };
    }
    if (record.isExpired()) {
      record.status = 'expired';
      return { success: false, reason: 'expired' };
    }

    record.status = 'denied';
    record.deniedAt = new Date().toISOString();
    return { success: true, reason: 'user_denied' };
  }

  getByTaskId(taskId) {
    const confirmationId = this._store.get(`task:${taskId}`);
    if (!confirmationId) return null;
    return this._store.get(confirmationId) || null;
  }

  getById(confirmationId) {
    return this._store.get(confirmationId) || null;
  }

  hasPendingForTask(taskId) {
    const record = this.getByTaskId(taskId);
    return record ? record.isUsable() : false;
  }

  verifyConfirmationNotExpanded(confirmationId, currentScope) {
    const record = this._store.get(confirmationId);
    if (!record || record.status !== 'confirmed') {
      return { valid: false, reason: 'not_confirmed' };
    }

    const original = record.scope || {};
    const originalPaths = original.allowed_paths || original.allowedPaths || {};
    const currentPaths = currentScope.allowed_paths || currentScope.allowedPaths || {};

    const operations = ['read', 'write', 'execute'];
    for (const op of operations) {
      const origArr = originalPaths[op] || [];
      const currArr = currentPaths[op] || [];

      if (currArr.length > origArr.length) {
        return {
          valid: false,
          reason: `scope_expansion_detected: ${op} has ${currArr.length} paths, originally ${origArr.length}`,
        };
      }

      for (const currPath of currArr) {
        const allowed = origArr.some(origPath => {
          return this._isPathWithin(currPath, origPath);
        });
        if (!allowed) {
          return {
            valid: false,
            reason: `scope_expansion_detected: ${op} path "${currPath}" not covered by original scope`,
          };
        }
      }
    }

    if (original.project_mode && currentScope.project_mode && original.project_mode !== currentScope.project_mode) {
      return {
        valid: false,
        reason: `project_mode mismatch: ${currentScope.project_mode} vs ${original.project_mode}`,
      };
    }

    return { valid: true };
  }

  _isPathWithin(child, parent) {
    const nc = this._normalizePath(child);
    const np = this._normalizePath(parent);
    if (nc === np) return true;
    if (!np.endsWith('/')) return nc.startsWith(np + '/') ? true : false;
    return nc.startsWith(np) ? true : false;
  }

  _normalizePath(p) {
    if (!p) return '';
    return require('path').resolve(p).replace(/\\/g, '/').replace(/\/+$/, '') || '/';
  }

  _normalizeScope(scope) {
    if (!scope) return {};
    if (scope.toDict) return scope.toDict();
    return scope;
  }

  _buildContextSummary(scope) {
    const s = this._normalizeScope(scope);
    const target = s.target_project_path || s.targetProjectPath || '';
    const mode = s.project_mode || s.projectMode || '';
    const impact = s.estimated_impact || s.estimatedImpact || '';

    const modeLabel = {
      'create_new_project': '创建新项目',
      'modify_existing_project': '修改现有项目',
      'modify_alphapilot': '修改 AlphaPilot 自身代码',
    }[mode] || mode;

    const paths = s.allowed_paths || s.allowedPaths || {};
    const readCount = (paths.read || []).length;
    const writeCount = (paths.write || []).length;
    const execCount = (paths.execute || []).length;

    const parts = [
      `即将在路径 "${target}" ${modeLabel}`,
    ];
    if (readCount > 0) parts.push(`读取 ${readCount} 个路径`);
    if (writeCount > 0) parts.push(`写入 ${writeCount} 个路径`);
    if (execCount > 0) parts.push(`可执行命令`);
    if (impact) parts.push(`影响: ${impact}`);

    return parts.join('，');
  }

  _computeScopeHash(scope) {
    const s = this._normalizeScope(scope);
    return computeContextHash({
      workspace_roots: [],
      authorized_roots: [],
      allowed_paths: s.allowed_paths || s.allowedPaths || {},
      target_project_path: s.target_project_path || s.targetProjectPath || '',
      project_mode: s.project_mode || s.projectMode || '',
      schema_version: '1.0',
    });
  }

  _cleanupExpired() {
    const now = Date.now();
    for (const [id, record] of this._store) {
      if (id.startsWith('task:')) continue;
      if (record.isExpired() && record.status === 'pending') {
        record.status = 'expired';
      }
    }
  }

  getStats() {
    const records = [];
    for (const [id, record] of this._store) {
      if (id.startsWith('task:')) continue;
      records.push(record.toDict());
    }
    return {
      total: records.length,
      pending: records.filter(r => r.status === 'pending').length,
      confirmed: records.filter(r => r.status === 'confirmed').length,
      denied: records.filter(r => r.status === 'denied').length,
      expired: records.filter(r => r.status === 'expired').length,
    };
  }
}

module.exports = {
  ConfirmationManager,
  ConfirmationRecord,
  DEFAULT_CONFIRMATION_TTL_MS,
};