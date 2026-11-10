const path = require('path');
const fs = require('fs');

const { computeContextHash } = require('./taskProtocol');

const VALID_MODES = new Set([
  'create_new_project',
  'modify_existing_project',
]);

const NEW_PROJECT_TEMPLATES = {
  create_new_project(targetPath, authorizedRoots) {
    const resolved = path.resolve(targetPath);
    return {
      read: [resolved],
      write: [resolved],
      execute: [resolved],
    };
  },
  modify_existing_project(targetPath, authorizedRoots) {
    const resolved = path.resolve(targetPath);
    return {
      read: [resolved],
      write: [resolved],
      execute: [resolved],
    };
  },
};

class ProjectStrategyError extends Error {
  constructor(message, reasonCode, field) {
    super(message);
    this.name = 'ProjectStrategyError';
    this.reasonCode = reasonCode || 'UNKNOWN';
    this.field = field || '';
  }
}

class AuthorizationDeniedError extends Error {
  constructor(message, reasonCode, auditRecord) {
    super(message);
    this.name = 'AuthorizationDeniedError';
    this.reasonCode = reasonCode || 'UNAUTHORIZED';
    this.auditRecord = auditRecord || {};
  }
}

class ConfirmationRequiredError extends Error {
  constructor(message, scope) {
    super(message);
    this.name = 'ConfirmationRequiredError';
    this.scope = scope;
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

class StrategyProposal {
  constructor({ mode, targetPath, confidence, reasoning, tags }) {
    this.mode = mode;
    this.targetPath = targetPath;
    this.confidence = confidence;
    this.reasoning = reasoning || '';
    this.tags = tags || [];
  }

  toDict() {
    return {
      mode: this.mode,
      target_path: this.targetPath,
      confidence: this.confidence,
      reasoning: this.reasoning,
      tags: this.tags,
    };
  }
}

class ConfirmationScope {
  constructor({ targetProjectPath, projectMode, allowedPaths, estimatedImpact, operationSpecific }) {
    this.targetProjectPath = targetProjectPath;
    this.projectMode = projectMode;
    this.allowedPaths = allowedPaths || { read: [], write: [], execute: [] };
    this.estimatedImpact = estimatedImpact || '';
    this.operationSpecific = operationSpecific || {};
  }

  toDict() {
    const r = {
      target_project_path: this.targetProjectPath,
      project_mode: this.projectMode,
      allowed_paths: this.allowedPaths,
      estimated_impact: this.estimatedImpact,
    };
    if (Object.keys(this.operationSpecific).length > 0) {
      r.operation_specific = this.operationSpecific;
    }
    return r;
  }
}

class UserConfirmation {
  constructor({ confirmationId, taskId, scope, grantedAt, contextHash, expiresAt }) {
    this.confirmationId = confirmationId;
    this.taskId = taskId;
    this.scope = scope;
    this.grantedAt = grantedAt;
    this.contextHash = contextHash;
    this.expiresAt = expiresAt || null;
  }

  toDict() {
    const r = {
      confirmation_id: this.confirmationId,
      task_id: this.taskId,
      scope: this.scope instanceof ConfirmationScope ? this.scope.toDict() : this.scope,
      granted_at: this.grantedAt,
      context_hash: this.contextHash,
    };
    if (this.expiresAt) {
      r.expires_at = this.expiresAt;
    }
    return r;
  }
}

class AuthorizedStrategy {
  constructor(proposal, allowedPaths, contextHash) {
    this.proposal = proposal;
    this.allowedPaths = allowedPaths;
    this.contextHash = contextHash || '';
  }
}

class ProjectStrategyResolver {
  resolve(userPrompt, workspaceRoots, workspaceStructure, activeFile) {
    const prompt = (userPrompt || '').toLowerCase();
    const roots = Array.isArray(workspaceRoots) ? workspaceRoots : [];
    const primaryRoot = roots.length > 0 ? roots[0] : null;

    if (!primaryRoot) {
      return new StrategyProposal({
        mode: 'modify_existing_project',
        targetPath: '.',
        confidence: 0.1,
        reasoning: 'no workspace roots available; defaulting to modify existing',
      });
    }

    const newProjectKeywords = ['create', 'new project', 'scaffold', 'generate', 'build a new', 'initialize'];
    const isNewProject = newProjectKeywords.some(kw => prompt.includes(kw));

    if (isNewProject) {
      let targetPath = primaryRoot;
      const projectName = this._extractProjectName(userPrompt || '');
      if (projectName) {
        targetPath = path.join(primaryRoot, 'projects', projectName);
      }
      return new StrategyProposal({
        mode: 'create_new_project',
        targetPath,
        confidence: 0.85,
        reasoning: projectName
          ? `detected new project creation intent with name: ${projectName}`
          : 'detected new project creation intent (no explicit project name)',
        tags: ['new_project'],
      });
    }

    return new StrategyProposal({
      mode: 'modify_existing_project',
      targetPath: primaryRoot,
      confidence: 0.7,
      reasoning: 'default strategy: modify existing project at workspace root',
    });
  }

  _extractProjectName(prompt) {
    const patterns = [
      /(?:create|build|generate|scaffold|make|new)\s+(?:a\s+)?(?:new\s+)?(?:\w+\s+)?project\s+(?:called|named|for\s+)?["']?([\w-]+)["']?/i,
      /(?:create|build|generate|scaffold|make)\s+(?:a\s+)?(?:new\s+)?["']?([\w-]+)["']?\s*(?:project|app|service|tool)/i,
      /(?:project|app|service|tool)\s+(?:called|named)\s+["']?([\w-]+)["']?/i,
    ];
    for (const pattern of patterns) {
      const match = prompt.match(pattern);
      if (match && match[1]) {
        return match[1].toLowerCase().replace(/[^a-z0-9_-]/g, '-');
      }
    }
    return null;
  }
}

class ProjectStrategyAuthorizer {
  constructor() {
    this._confirmationStore = new Map();
  }

  authorize(proposal, authorizedRoots, userConfirmations) {
    if (!proposal || !(proposal instanceof StrategyProposal)) {
      throw new ProjectStrategyError('proposal must be a StrategyProposal', 'INVALID_PROPOSAL');
    }

    if (!Array.isArray(authorizedRoots) || authorizedRoots.length === 0) {
      throw new AuthorizationDeniedError(
        'authorized_roots must be a non-empty array',
        'MISSING_AUTHORIZED_ROOTS',
        { authorizedRoots }
      );
    }

    const target = path.resolve(proposal.targetPath);

    if (proposal.mode === 'create_new_project') {
      let parent = target;
      while (parent !== path.dirname(parent) && !fs.existsSync(parent)) {
        parent = path.dirname(parent);
      }
      if (!fs.existsSync(parent)) {
        throw new AuthorizationDeniedError(
          `no existing parent directory for target: ${target}`,
          'TARGET_PARENT_NOT_FOUND',
          { target, parent }
        );
      }
      if (fs.existsSync(target)) {
        const scope = new ConfirmationScope({
          targetProjectPath: target,
          projectMode: 'create_new_project',
          allowedPaths: {},
          estimatedImpact: `target path already exists: ${target}`,
          operationSpecific: { existingPath: target, isDirectory: fs.statSync(target).isDirectory() },
        });
        throw new ConfirmationRequiredError(
          'create_new_project target already exists; cannot silently reuse',
          scope
        );
      }
    } else {
      if (!fs.existsSync(target)) {
        throw new ProjectStrategyError(
          `target_project_path does not exist: ${target}`,
          'TARGET_NOT_FOUND',
          'target_project_path'
        );
      }
      if (!fs.statSync(target).isDirectory()) {
        throw new ProjectStrategyError(
          `target_project_path is not a directory: ${target}`,
          'TARGET_NOT_DIRECTORY',
          'target_project_path'
        );
      }
    }

    const isTargetAuthorized = authorizedRoots.some(ar => isPathWithin(target, ar));
    if (!isTargetAuthorized) {
      throw new AuthorizationDeniedError(
        `target ${target} is not within any authorized_root`,
        'TARGET_NOT_AUTHORIZED',
        { target, authorizedRoots: authorizedRoots.map(String) }
      );
    }

    if (proposal.mode === 'modify_alphapilot') {
      const confirmed = this._findConfirmation(proposal, userConfirmations || []);
      if (!confirmed) {
        const scope = new ConfirmationScope({
          targetProjectPath: target,
          projectMode: proposal.mode,
          allowedPaths: {},
          estimatedImpact: 'modifying AlphaPilot source code',
          operationSpecific: {},
        });
        throw new ConfirmationRequiredError(
          `mode ${proposal.mode} requires user confirmation`,
          scope
        );
      }
    }

    const templateFunc = NEW_PROJECT_TEMPLATES[proposal.mode];
    if (!templateFunc) {
      throw new ProjectStrategyError(
        `unsupported project_mode: ${proposal.mode}`,
        'UNSUPPORTED_MODE',
        'project_mode'
      );
    }
    const allowedPaths = templateFunc(target, authorizedRoots);

    const contextHash = this._computeContextHash({
      workspaceRoots: authorizedRoots,
      authorizedRoots,
      allowedPaths,
      targetProjectPath: target,
      projectMode: proposal.mode,
      schemaVersion: '1.0',
    });

    return new AuthorizedStrategy(proposal, allowedPaths, contextHash);
  }

  _findConfirmation(proposal, confirmations) {
    for (const c of confirmations) {
      const scope = c.scope || c;
      const matchTarget = scope.targetProjectPath || scope.target_project_path;
      const matchMode = scope.projectMode || scope.project_mode;
      if (matchTarget === proposal.targetPath && matchMode === proposal.mode) {
        if (!this._isExpired(c)) {
          return c;
        }
      }
    }
    return null;
  }

  _isExpired(confirmation) {
    const expires = confirmation.expiresAt || confirmation.expires_at;
    if (!expires) return false;
    try {
      return new Date() > new Date(expires);
    } catch {
      return false;
    }
  }

  _computeContextHash(fields) {
    return computeContextHash({
      workspace_roots: fields.workspaceRoots || [],
      authorized_roots: fields.authorizedRoots || [],
      allowed_paths: fields.allowedPaths || { read: [], write: [], execute: [] },
      target_project_path: fields.targetProjectPath || '',
      project_mode: fields.projectMode || '',
      schema_version: fields.schemaVersion || '1.0',
    });
  }
}

module.exports = {
  VALID_MODES,
  ProjectStrategyError,
  AuthorizationDeniedError,
  ConfirmationRequiredError,
  StrategyProposal,
  ConfirmationScope,
  UserConfirmation,
  AuthorizedStrategy,
  ProjectStrategyResolver,
  ProjectStrategyAuthorizer,
  normalizePath,
  isPathWithin,
  NEW_PROJECT_TEMPLATES,
};