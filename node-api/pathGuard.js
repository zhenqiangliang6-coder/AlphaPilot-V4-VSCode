// node-api/pathGuard.js
// ---------------------------------------------------------------
// Phase 2.3 PathGuard — 执行边界防御层 (Node.js 实现)
//
// v1 声明：PathGuard 是 Worker 内部防御层，不能替代操作系统级进程隔离。
// 命令执行仍存在残余风险（可通过绝对路径、子进程、环境变量绕过）。
//
// 六种操作能力模型:
//   validateRead(path)         → allowed_paths.read
//   validateWrite(path)        → allowed_paths.write + 敏感路径策略
//   validateCreateDir(path)    → allowed_paths.write + 父目录在 write/read 内
//   validateDelete(path, r)    → allowed_paths.write + 独立确认
//   validateMove(src, dst)     → 两端均在 allowed_paths.write
//   validateExecute(cwd, cmd)  → allowed_paths.execute + 命令策略
// ---------------------------------------------------------------

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const V1_RESIDUAL_RISK =
  'PathGuard 是 Worker 内部防御层，不能替代操作系统级进程隔离。' +
  '命令仍可能通过绝对路径、子进程或环境变量写入 allowed_paths.execute 之外的目录。' +
  '此风险在 v1 中公开声明，不作为安全缺陷报告。';

// ================================================================
// 1. 路径工具
// ================================================================

function normalizePath(p) {
  if (!p) return '';
  if (process.platform === 'win32' && /^[a-zA-Z]:[/\\]?$/.test(p.trim())) {
    return p.trim().toUpperCase().replace(/\\/g, '/').replace(/\/$/, '') + '/';
  }
  const resolved = path.resolve(p).replace(/\\/g, '/');
  let result = resolved.replace(/\/+$/, '');
  if (process.platform === 'win32' && result.length === 2 && result[1] === ':') {
    result += '/';
  }
  return result || '/';
}

function realpathSafe(p) {
  try {
    let result = fs.realpathSync(p).replace(/\\/g, '/');
    result = result.replace(/\/+$/, '');
    if (process.platform === 'win32' && result.length === 2 && result[1] === ':') {
      result += '/';
    }
    return result || '/';
  } catch (_) {
    return normalizePath(p);
  }
}

function isPathWithin(child, parent) {
  const nc = normalizePath(child);
  let np = normalizePath(parent);
  if (nc === np) return true;
  if (!np.endsWith('/')) np += '/';
  if (nc.startsWith(np)) return true;
  return false;
}

// ================================================================
// 2. 敏感路径策略（五层）
// ================================================================

const L0_CREDENTIAL_FORBIDDEN = /(^|\/)(\.env($|\..*)|.*\.key$|.*\.pem$|.*\.p12$|secrets\..*|credentials\..*|\.git-credentials$|\.npmrc$)/i;

const L1_VCS_FORBIDDEN_WRITE = /(^|\/)\.git\/(config|hooks\/.*|HEAD|index)$/i;

const L2_BUILD_ARTIFACT_FORBIDDEN_DIRECT_WRITE = /(^|\/)(node_modules|target|dist|build|__pycache__|\.venv|venv|\.pytest_cache)(\/|$)/i;

const L3_LOCKFILE_FORBIDDEN_DIRECT_WRITE = /(^|\/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|Gemfile\.lock|composer\.lock)$/i;

const SYSTEM_PATHS_WINDOWS = new RegExp(
  '^/?[a-z]/windows(/|$)|' +
  '^/?[a-z]/program files(/|$)|' +
  '^/?[a-z]/program files \\(x86\\)(/|$)|' +
  '^/?[a-z]/system32(/|$)|' +
  '^/?[a-z]/syswow64(/|$)|' +
  '^[a-z]:\\\\(windows|program files|program files \\(x86\\)|system32|syswow64)(\\\\|$)',
  'i'
);
const SYSTEM_PATHS_UNIX = /^\/(etc|usr|opt|boot|dev|proc|sys|var\/log|var\/run)(\/|$)/;

function normalizedForPattern(p) {
  let n = normalizePath(p);
  if (process.platform === 'win32') {
    n = '/' + n.replace(':', '').replace(/\\/g, '/');
  }
  return n;
}

function checkSensitivePath(filePath, operation, isCommandExecution = false) {
  const np = normalizedForPattern(filePath);

  if (L0_CREDENTIAL_FORBIDDEN.test(np)) {
    return `L0 凭据禁止: ${filePath} (操作: ${operation})`;
  }

  if (['write', 'delete', 'create_dir'].includes(operation)) {
    if (!isCommandExecution) {
      if (L1_VCS_FORBIDDEN_WRITE.test(np)) {
        return `L1 版本控制禁止直接${operation}: ${filePath}`;
      }
      if (L2_BUILD_ARTIFACT_FORBIDDEN_DIRECT_WRITE.test(np)) {
        return `L2 构建产物禁止直接${operation}: ${filePath}`;
      }
      if (L3_LOCKFILE_FORBIDDEN_DIRECT_WRITE.test(np)) {
        return `L3 锁文件禁止直接${operation}: ${filePath}`;
      }
    }
  }

  if (operation === 'read') {
    if (L0_CREDENTIAL_FORBIDDEN.test(np)) {
      return `L0 凭据禁止读取: ${filePath}`;
    }
  }

  return null;
}

// ================================================================
// 3. 命令安全策略
// ================================================================

const BLOCKED_COMMANDS = new Set([
  'rm', 'mv', 'cp', 'chmod', 'chown', 'sudo', 'su', 'mkfs', 'dd',
  'shutdown', 'reboot', 'halt', 'poweroff', 'init', 'systemctl',
  'mount', 'umount', 'fdisk', 'parted', 'passwd', 'useradd', 'usermod',
  'iptables', 'nftables', 'firewall-cmd', 'ufw',
]);

const DANGEROUS_PATTERNS_SHELL = [
  />\s*\/dev\/sd[a-z]/i,
  />\s*\/dev\/nvme/i,
  /mkfs\./i,
  /dd\s+if=/i,
  /:\(\)\s*\{\s*:\|:&\s*\};:/,
  /format\s+[a-zA-Z]:/i,
  /deltree\s+\/y\s+[a-zA-Z]:/i,
  /del\s+\/f\s+\/s\s+\/q\s+[a-zA-Z]:/i,
  /(curl|wget)\s+.*\|\s*(sh|bash|zsh|dash|fish)/i,
  /(curl|wget)\s+.*\|\s*(python|perl|ruby|node)/i,
  />\s*\/etc\//i,
  />\s*\/usr\//i,
  />\s*\/opt\//i,
];

const SUSPICIOUS_ENV_VARS = new Set([
  'PYTHONPATH', 'NODE_PATH', 'RUBYLIB', 'PERL5LIB',
  'CLASSPATH', 'GOPATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH',
  'DYLD_INSERT_LIBRARIES', 'DYLD_LIBRARY_PATH',
]);

function checkCommandSafety(command, cwd) {
  for (const pattern of DANGEROUS_PATTERNS_SHELL) {
    if (pattern.test(command)) {
      return `命令匹配危险模式: ${pattern.source}`;
    }
  }

  const tokens = command.trim().split(/\s+/);
  if (tokens.length > 0) {
    const baseCmd = path.basename(tokens[0]).toLowerCase();
    if (BLOCKED_COMMANDS.has(baseCmd)) {
      return `命令在阻止列表中: ${baseCmd}`;
    }
  }

  return null;
}

function checkEnvSafety(env) {
  if (!env) return [];
  const warnings = [];
  for (const key of SUSPICIOUS_ENV_VARS) {
    if (key in env) {
      warnings.push(`环境变量 ${key} 被显式覆盖（可能影响命令行为）: ${String(env[key]).slice(0, 80)}`);
    }
  }
  return warnings;
}

function checkSystemPaths(cwd) {
  if (SYSTEM_PATHS_UNIX.test(cwd)) {
    return `cwd 指向系统路径: ${cwd}`;
  }
  const normalized = normalizedForPattern(cwd);
  if (SYSTEM_PATHS_WINDOWS.test(normalized)) {
    return `cwd 指向系统路径: ${cwd}`;
  }
  return null;
}

// ================================================================
// 4. 审计记录
// ================================================================

function createAuditRecord(fields) {
  return {
    timestamp: fields.timestamp || new Date().toISOString(),
    operation: fields.operation || '',
    path: fields.path || '',
    resolved_path: fields.resolved_path || '',
    allowed_domain: fields.allowed_domain || '',
    command: fields.command || '',
    cwd: fields.cwd || '',
    user_id: fields.user_id || '',
    task_id: fields.task_id || '',
    result: fields.result || '',
    context_hash: fields.context_hash || '',
    env_warnings: fields.env_warnings || [],
  };
}

// ================================================================
// 5. 异常类型
// ================================================================

class PathGuardAuthorizationDenied extends Error {
  constructor(message, reasonCode, auditRecord = {}) {
    super(message);
    this.name = 'PathGuardAuthorizationDenied';
    this.reasonCode = reasonCode || 'UNKNOWN';
    this.auditRecord = auditRecord;
  }
}

class PathGuardValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'PathGuardValidationError';
  }
}

// ================================================================
// 6. PathGuard 核心类
// ================================================================

class PathGuard {
  /**
   * @param {object} taskContext - 符合 TaskContext 契约的 task_context 对象
   * @param {function} auditCallback - 可选审计回调
   */
  constructor(taskContext, auditCallback) {
    if (!taskContext || typeof taskContext !== 'object') {
      throw new PathGuardValidationError('PathGuard requires a valid task_context object');
    }

    const allowed = taskContext.allowed_paths || { read: [], write: [], execute: [] };
    this._allowed = {
      read: (allowed.read || []).map(realpathSafe),
      write: (allowed.write || []).map(realpathSafe),
      execute: (allowed.execute || []).map(realpathSafe),
    };
    this._authRoots = (taskContext.authorized_roots || []).map(realpathSafe);
    this._audit = auditCallback || (() => {});
    this._contextHash = taskContext.context_hash || '';
    this._compatPolicy = taskContext.compatibility_policy || '';
    this._taskId = taskContext.context_id || '';
    this._context = taskContext;
  }

  get context() { return this._context; }
  get allowedPaths() { return this._allowed; }
  get compatPolicy() { return this._compatPolicy; }

  _auditRecord(operation, filePath, domain, result, extra = {}) {
    const record = createAuditRecord({
      timestamp: new Date().toISOString(),
      operation,
      path: filePath,
      resolved_path: filePath ? realpathSafe(filePath) : '',
      allowed_domain: domain,
      result,
      context_hash: this._contextHash,
      task_id: this._taskId,
      command: extra.command || '',
      cwd: extra.cwd || '',
      env_warnings: extra.env_warnings || [],
    });
    this._audit(record);
    return record;
  }

  // ---- 六种核心验证方法 ----

  validateRead(filePath) {
    const resolved = realpathSafe(filePath);

    if (this._compatPolicy === 'compat_readonly') {
      for (const domainPath of this._allowed.read) {
        if (isPathWithin(resolved, domainPath)) {
          this._auditRecord('read', filePath, 'read', 'ALLOWED_COMPAT');
          return resolved;
        }
      }
      throw new PathGuardAuthorizationDenied(
        `compat_readonly 不允许读取路径: ${filePath}`,
        'READ_OUTSIDE_ALLOWED',
        { path: filePath, resolved, allowed_read: this._allowed.read }
      );
    }

    if (this._allowed.read.length === 0) {
      throw new PathGuardAuthorizationDenied(
        `读取路径时 read 域为空: ${filePath}`,
        'READ_DOMAIN_EMPTY',
        { path: filePath, resolved }
      );
    }

    for (const domainPath of this._allowed.read) {
      if (isPathWithin(resolved, domainPath)) {
        const sensitive = checkSensitivePath(resolved, 'read');
        if (sensitive) {
          throw new PathGuardAuthorizationDenied(
            sensitive,
            'SENSITIVE_PATH_READ',
            { path: filePath, resolved }
          );
        }
        this._auditRecord('read', filePath, 'read', 'ALLOWED');
        return resolved;
      }
    }

    throw new PathGuardAuthorizationDenied(
      `path outside allowed_paths.read: ${filePath}`,
      'READ_OUTSIDE_ALLOWED',
      { path: filePath, resolved, allowed_read: this._allowed.read }
    );
  }

  validateWrite(filePath) {
    const resolved = realpathSafe(filePath);

    if (this._allowed.write.length === 0) {
      throw new PathGuardAuthorizationDenied(
        `写入路径时 write 域为空（compat 任务无写入权限）: ${filePath}`,
        'WRITE_DOMAIN_EMPTY',
        { path: filePath, resolved }
      );
    }

    for (const domainPath of this._allowed.write) {
      if (isPathWithin(resolved, domainPath)) {
        const sensitive = checkSensitivePath(resolved, 'write', false);
        if (sensitive) {
          throw new PathGuardAuthorizationDenied(
            sensitive,
            'SENSITIVE_PATH_WRITE',
            { path: filePath, resolved }
          );
        }
        this._auditRecord('write', filePath, 'write', 'ALLOWED');
        return resolved;
      }
    }

    throw new PathGuardAuthorizationDenied(
      `path outside allowed_paths.write: ${filePath}`,
      'WRITE_OUTSIDE_ALLOWED',
      { path: filePath, resolved, allowed_write: this._allowed.write }
    );
  }

  validateCreateDir(filePath) {
    const resolved = realpathSafe(filePath);

    if (this._allowed.write.length === 0) {
      throw new PathGuardAuthorizationDenied(
        `创建目录时 write 域为空: ${filePath}`,
        'WRITE_DOMAIN_EMPTY',
        { path: filePath, resolved }
      );
    }

    const inWrite = this._allowed.write.some(dp => isPathWithin(resolved, dp));
    if (!inWrite) {
      throw new PathGuardAuthorizationDenied(
        `create_dir target outside allowed_paths.write: ${filePath}`,
        'CREATE_DIR_OUTSIDE_WRITE',
        { path: filePath, resolved, allowed_write: this._allowed.write }
      );
    }

    let parentPath = path.dirname(resolved);
    while (parentPath !== path.dirname(parentPath) && !fs.existsSync(parentPath)) {
      parentPath = path.dirname(parentPath);
    }

    const parentResolved = realpathSafe(parentPath);
    const parentInWrite = this._allowed.write.some(dp => isPathWithin(parentResolved, dp));
    const parentInRead = this._allowed.read.some(dp => isPathWithin(parentResolved, dp));
    if (!parentInWrite && !parentInRead) {
      throw new PathGuardAuthorizationDenied(
        `create_dir parent not in allowed_paths (write/read): ${parentPath}`,
        'CREATE_DIR_PARENT_NOT_AUTHORIZED',
        { path: filePath, parent: parentPath, resolved }
      );
    }

    const sensitive = checkSensitivePath(resolved, 'create_dir');
    if (sensitive) {
      throw new PathGuardAuthorizationDenied(
        sensitive,
        'SENSITIVE_PATH_WRITE',
        { path: filePath, resolved }
      );
    }

    this._auditRecord('create_dir', filePath, 'write', 'ALLOWED');
    return resolved;
  }

  validateDelete(filePath, recursive = false) {
    const resolved = realpathSafe(filePath);

    if (this._allowed.write.length === 0) {
      throw new PathGuardAuthorizationDenied(
        `删除时 write 域为空: ${filePath}`,
        'WRITE_DOMAIN_EMPTY',
        { path: filePath, resolved }
      );
    }

    const inWrite = this._allowed.write.some(dp => isPathWithin(resolved, dp));
    if (!inWrite) {
      throw new PathGuardAuthorizationDenied(
        `delete target outside allowed_paths.write: ${filePath}`,
        'DELETE_OUTSIDE_WRITE',
        { path: filePath, resolved, allowed_write: this._allowed.write }
      );
    }

    const sensitive = checkSensitivePath(resolved, 'delete');
    if (sensitive) {
      throw new PathGuardAuthorizationDenied(
        sensitive,
        'SENSITIVE_PATH_DELETE',
        { path: filePath, resolved }
      );
    }

    if (recursive) {
      throw new PathGuardAuthorizationDenied(
        `递归删除必须经用户确认流程: ${filePath}`,
        'RECURSIVE_DELETE_REQUIRES_CONFIRMATION',
        { path: filePath, recursive: true }
      );
    }

    if (fs.existsSync(resolved)) {
      const stat = fs.statSync(resolved);
      if (stat.isDirectory()) {
        const entries = fs.readdirSync(resolved);
        if (entries.length > 0) {
          throw new PathGuardAuthorizationDenied(
            `目录非空（${entries.length} 个子项），递归删除需要确认: ${filePath}`,
            'DIRECTORY_NOT_EMPTY',
            { path: filePath, item_count: entries.length }
          );
        }
      }
    }

    this._auditRecord('delete', filePath, 'write', 'ALLOWED');
    return resolved;
  }

  validateMove(src, dest) {
    const srcResolved = realpathSafe(src);
    const destResolved = realpathSafe(dest);

    if (this._allowed.write.length === 0) {
      throw new PathGuardAuthorizationDenied(
        `移动时 write 域为空: ${src} -> ${dest}`,
        'WRITE_DOMAIN_EMPTY',
        { src, dest }
      );
    }

    const srcIn = this._allowed.write.some(dp => isPathWithin(srcResolved, dp));
    const destIn = this._allowed.write.some(dp => isPathWithin(destResolved, dp));

    if (!srcIn) {
      throw new PathGuardAuthorizationDenied(
        `move source outside allowed_paths.write: ${src}`,
        'MOVE_SRC_OUTSIDE_WRITE',
        { src, src_resolved: srcResolved, allowed_write: this._allowed.write }
      );
    }
    if (!destIn) {
      throw new PathGuardAuthorizationDenied(
        `move destination outside allowed_paths.write: ${dest}`,
        'MOVE_DEST_OUTSIDE_WRITE',
        { dest, dest_resolved: destResolved, allowed_write: this._allowed.write }
      );
    }

    const sensitive = checkSensitivePath(destResolved, 'move');
    if (sensitive) {
      throw new PathGuardAuthorizationDenied(
        sensitive,
        'SENSITIVE_PATH_MOVE',
        { src, dest }
      );
    }

    this._auditRecord('move', src, 'write', 'ALLOWED');
    return { src: srcResolved, dest: destResolved };
  }

  validateExecute(cwd, command, env) {
    const resolvedCwd = realpathSafe(cwd || '.');

    if (this._allowed.execute.length === 0) {
      throw new PathGuardAuthorizationDenied(
        `执行命令时 execute 域为空: ${String(command).slice(0, 80)}...`,
        'EXECUTE_DOMAIN_EMPTY',
        { command, cwd }
      );
    }

    const inExecute = this._allowed.execute.some(dp => isPathWithin(resolvedCwd, dp));
    if (!inExecute) {
      throw new PathGuardAuthorizationDenied(
        `cwd outside allowed_paths.execute: ${cwd}`,
        'EXECUTE_CWD_OUTSIDE_ALLOWED',
        { command, cwd, resolved_cwd: resolvedCwd }
      );
    }

    const sysPath = checkSystemPaths(cwd);
    if (sysPath) {
      throw new PathGuardAuthorizationDenied(
        sysPath,
        'EXECUTE_SYSTEM_PATH',
        { command, cwd }
      );
    }

    const cmdIssue = checkCommandSafety(command, cwd);
    if (cmdIssue) {
      throw new PathGuardAuthorizationDenied(
        cmdIssue,
        'DANGEROUS_COMMAND',
        { command, cwd }
      );
    }

    const envWarnings = checkEnvSafety(env);
    if (envWarnings.length > 0) {
      console.warn(`[PathGuard] env warnings for execute: ${envWarnings.join('; ')}`);
    }

    this._auditRecord('execute', cwd, 'execute', 'ALLOWED', {
      command,
      cwd: resolvedCwd,
      env_warnings: envWarnings,
    });

    return resolvedCwd;
  }
}

// ================================================================
// 7. 工厂函数
// ================================================================

function createPathGuard(taskContext, auditCallback) {
  return new PathGuard(taskContext, auditCallback);
}

function disablePathGuard(taskContext) {
  const rootPath = taskContext.target_project_path || (taskContext.workspace_roots && taskContext.workspace_roots[0]) || process.cwd();
  const drive = process.platform === 'win32'
    ? (rootPath.match(/^[a-zA-Z]:/) ? rootPath.substring(0, 2) + '/' : '/')
    : '/';
  const dummyAllowed = { read: [drive], write: [drive], execute: [drive] };
  return new PathGuard({
    context_id: taskContext.context_id,
    workspace_roots: taskContext.workspace_roots || [],
    authorized_roots: [drive],
    allowed_paths: dummyAllowed,
    target_project_path: taskContext.target_project_path || drive,
    project_mode: taskContext.project_mode || 'modify_existing_project',
    created_at: taskContext.created_at || new Date().toISOString(),
    context_hash: taskContext.context_hash || '',
    compatibility_policy: '',
  });
}

module.exports = {
  PathGuard,
  PathGuardAuthorizationDenied,
  PathGuardValidationError,
  createAuditRecord,
  createPathGuard,
  disablePathGuard,

  normalizePath,
  realpathSafe,
  isPathWithin,
  checkSensitivePath,
  checkCommandSafety,
  checkEnvSafety,
  checkSystemPaths,

  BLOCKED_COMMANDS,
  DANGEROUS_PATTERNS_SHELL,
  SUSPICIOUS_ENV_VARS,
  L0_CREDENTIAL_FORBIDDEN,
  L1_VCS_FORBIDDEN_WRITE,
  L2_BUILD_ARTIFACT_FORBIDDEN_DIRECT_WRITE,
  L3_LOCKFILE_FORBIDDEN_DIRECT_WRITE,
  SYSTEM_PATHS_WINDOWS,
  SYSTEM_PATHS_UNIX,
};