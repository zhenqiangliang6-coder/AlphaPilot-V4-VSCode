// node-api/fileOpsHandler.js
// ---------------------------------------------------------
// AlphaPilot OS v3.0 FileOps Handler
// 负责接收 Worker 生成的 file_ops 并执行真实的文件系统操作
// ---------------------------------------------------------

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// =========================
// 1. Validator (验证层)
// =========================
class FileOpsValidator {
    constructor(workspaceRoot) {
        this.workspaceRoot = workspaceRoot;
    }

    /**
     * 验证路径安全性
     * - 必须是相对路径
     * - 禁止 .. 越级
     * - 必须在项目根目录内
     */
    validatePath(filePath) {
        if (!filePath || typeof filePath !== 'string') {
            return { valid: false, error: '无效的路径格式' };
        }

        // 禁止绝对路径
        if (path.isAbsolute(filePath)) {
            return { valid: false, error: `禁止使用绝对路径: ${filePath}` };
        }

        const rootPath = path.resolve(this.workspaceRoot);
        const fullPath = path.resolve(rootPath, filePath);
        const relativePath = path.relative(rootPath, fullPath);
        if (
            relativePath === '..'
            || relativePath.startsWith(`..${path.sep}`)
            || path.isAbsolute(relativePath)
        ) {
            return { valid: false, error: `禁止路径越级: ${filePath}` };
        }

        let existingParent = fullPath;
        while (!fs.existsSync(existingParent)) {
            const parent = path.dirname(existingParent);
            if (parent === existingParent) break;
            existingParent = parent;
        }
        try {
            const realRoot = fs.realpathSync(rootPath);
            const realParent = fs.realpathSync(existingParent);
            const realRelativePath = path.relative(realRoot, realParent);
            if (
                realRelativePath === '..'
                || realRelativePath.startsWith(`..${path.sep}`)
                || path.isAbsolute(realRelativePath)
            ) {
                return { valid: false, error: `路径通过符号链接超出工作区: ${filePath}` };
            }
        } catch (error) {
            return { valid: false, error: `无法验证目标路径: ${error.message}` };
        }

        if (!fs.existsSync(rootPath) || !fs.statSync(rootPath).isDirectory()) {
            return { valid: false, error: `路径超出工作区范围: ${filePath}` };
        }

        return { valid: true };
    }

    isSensitivePath(filePath) {
        const segments = filePath.replace(/\\/g, '/').split('/').filter(Boolean);
        return segments.some((segment) => {
            const normalized = segment.toLowerCase();
            return normalized === '.git'
                || normalized === '.env'
                || normalized.startsWith('.env.')
                || ['node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build'].includes(normalized);
        });
    }

    /**
     * 验证单个 FileOp 结构
     */
    validateOp(op) {
        if (!op.op || !['create', 'modify', 'delete', 'test', 'doc', 'meta', 'depends'].includes(op.op)) {
            return { valid: false, error: `不支持的操作类型: ${op.op}` };
        }

        if (['create', 'modify', 'delete', 'test', 'doc'].includes(op.op)) {
            const pathCheck = this.validatePath(op.path);
            if (!pathCheck.valid) return pathCheck;
            if (op.op === 'delete' && this.isSensitivePath(op.path)) {
                return { valid: false, error: `拒绝删除敏感路径: ${op.path}` };
            }
        }

        return { valid: true };
    }
}

// =========================
// 2. Executor (执行层)
// =========================
class FileOpsExecutor {
    constructor(workspaceRoot, pathGuard = null) {
        this.workspaceRoot = workspaceRoot;
        this.pathGuard = pathGuard;
    }

    /**
     * 确保父目录存在（支持递归创建）
     */
    ensureDirectoryExists(filePath) {
        const dir = path.dirname(path.join(this.workspaceRoot, filePath));
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }

    /**
     * 执行单个 FileOp
     */
    async executeOp(op) {
        const fullPath = path.join(this.workspaceRoot, op.path);

        switch (op.op) {
            case 'create':
            case 'modify':
            case 'test':
            case 'doc':
                if (this.pathGuard) {
                    try {
                        const targetPath = op.op === 'create' || op.op === 'test' || op.op === 'doc'
                            ? this._validateWritePath(op.path, fullPath)
                            : this._validateModifyPath(op.path, fullPath);
                        this.ensureDirectoryExists(op.path);
                        fs.writeFileSync(targetPath, op.content || '', 'utf-8');
                        return { status: 'success', action: 'write', path: op.path };
                    } catch (e) {
                        if (e.name === 'PathGuardAuthorizationDenied') {
                            return { status: 'error', path: op.path, error: `PathGuard 拒绝写入: ${e.message}` };
                        }
                        throw e;
                    }
                }

                if (op.op === 'modify') {
                    if (!fs.existsSync(fullPath)) {
                        this.ensureDirectoryExists(op.path);
                    }
                } else {
                    this.ensureDirectoryExists(op.path);
                }
                fs.writeFileSync(fullPath, op.content || '', 'utf-8');
                return { status: 'success', action: op.op === 'modify' ? 'modify' : 'write', path: op.path };

            case 'delete':
                throw new Error('删除操作必须通过 VS Code 工作区删除工具，以确保回收站与用户确认策略生效');

            case 'meta':
            case 'depends':
                return { status: 'success', action: 'store_meta', data: op.data };

            default:
                throw new Error(`未知的操作: ${op.op}`);
        }
    }

    _validateWritePath(relativePath, fullPath) {
        try {
            return this.pathGuard.validateWrite(fullPath);
        } catch (e) {
            if (e.name === 'PathGuardAuthorizationDenied') {
                throw e;
            }
            try {
                this.pathGuard.validateWrite(fullPath);
            } catch (inner) {
                throw inner;
            }
            throw e;
        }
    }

    _validateModifyPath(relativePath, fullPath) {
        if (fs.existsSync(fullPath)) {
            return this.pathGuard.validateWrite(fullPath);
        }
        return this.pathGuard.validateWrite(fullPath);
    }

    /**
     * 批量执行 FileOps
     */
    async executeBatch(fileOps) {
        const results = [];
        for (const op of fileOps) {
            try {
                const result = await this.executeOp(op);
                results.push(result);
            } catch (error) {
                results.push({ status: 'error', path: op.path, error: error.message });
            }
        }
        return results;
    }
}

// =========================
// 3. Dispatcher (分发层)
// =========================
class FileOpsHandler {
    constructor(workspaceRoot, pathGuard = null) {
        this.workspaceRoot = workspaceRoot;
        this.validator = new FileOpsValidator(workspaceRoot || '');
        this.executor = new FileOpsExecutor(workspaceRoot || '', pathGuard);
    }

    /**
     * 动态设置工作区路径（VSCode 扩展调用）
     */
    setWorkspace(newPath) {
        if (!newPath) {
            throw new Error('工作区路径不能为空');
        }
        
        this.workspaceRoot = newPath;
        this.validator.workspaceRoot = newPath;
        this.executor.workspaceRoot = newPath;
        console.log(`[FileOpsHandler] ✅ 工作区已更新: ${newPath}`);
    }

    /**
     * 设置 PathGuard（Phase 2.3+）
     */
    setPathGuard(pathGuard) {
        this.executor.pathGuard = pathGuard;
        console.log(`[FileOpsHandler] ✅ PathGuard 已绑定: ${pathGuard.contextHash?.slice(0, 12) || 'unknown'}`);
    }

    /**
     * 检查是否已配置工作区
     */
    isWorkspaceConfigured() {
        return !!this.workspaceRoot;
    }

    /**
     * 处理来自 Worker 的 file_ops 请求
     *
     * @param {Array} fileOps 待执行的 FileOps
     * @param {string} [taskId] 任务 ID，用于审计快照；未提供时自动生成
     */
    async handleRequest(fileOps, taskId) {
        // ⭐ 检查工作区是否已配置
        if (!this.isWorkspaceConfigured()) {
            console.error('[FileOpsHandler] ❌ 错误: 工作区未配置，请先调用 /workspace/set');
            return { 
                success: false, 
                error: '工作区未配置，请先通过 POST /workspace/set 设置工作区路径' 
            };
        }

        console.log(`[FileOpsHandler] 📋 收到 ${fileOps.length} 个 FileOps 请求`);
        console.log(`[FileOpsHandler] 📁 当前工作区: ${this.workspaceRoot}`);

        // 1. 验证阶段
        const errors = [];
        for (let i = 0; i < fileOps.length; i++) {
            const check = this.validator.validateOp(fileOps[i]);
            if (!check.valid) {
                errors.push(`FileOp[${i}]: ${check.error}`);
            }
        }

        if (errors.length > 0) {
            return { success: false, errors };
        }

        // ⭐ G1/G2 治理：写盘前自动快照（含 SHA256），保证失败可回滚、基线不污染
        const governanceTaskId = taskId || `t_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
        const snapshot = this._snapshotBeforeWrite(fileOps, governanceTaskId);

        // 2. 执行阶段
        try {
            const results = await this.executor.executeBatch(fileOps);
            const failedResults = results.filter(result => result.status !== 'success');
            
            // ⭐ 构建返回结果，包含生成的文件列表
            const files = results
                .filter(r => r.status === 'success')
                .map(r => ({ path: r.path, action: r.action }));
            
            return { 
                success: failedResults.length === 0,
                results,
                files,
                errors: failedResults.map(result => ({
                    path: result.path,
                    error: result.error,
                })),
                governance: {
                    task_id: governanceTaskId,
                    snapshot_path: snapshot.snapshot_path,
                    files_snapshotted: snapshot.files_snapshotted,
                    files_created: snapshot.files_created,
                },
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    /**
     * G1：写盘前自动快照。
     * 对每个将要被 create/modify/test/doc 操作触达的文件，记录其原始内容、SHA256、
     * 大小与修改时间，写入工作区内 .alphapilot/governance/<taskId>/snapshot.json。
     * 已存在文件记录原始基线；不存在文件标记为"新增"，供回滚时删除。
     */
    _snapshotBeforeWrite(fileOps, taskId) {
        const snapshotDir = this._governanceDir(taskId);
        const snapshotPath = path.join(snapshotDir, 'snapshot.json');
        const files = {};
        const filesCreated = [];

        for (const op of fileOps) {
            if (!op || !op.path) continue;
            if (!['create', 'modify', 'test', 'doc'].includes(op.op)) continue;

            const fullPath = path.join(this.workspaceRoot, op.path);
            if (fs.existsSync(fullPath) && fs.statSync(fullPath).isFile()) {
                const content = fs.readFileSync(fullPath, 'utf-8');
                const stat = fs.statSync(fullPath);
                files[op.path] = {
                    existed: true,
                    content,
                    sha256: crypto.createHash('sha256').update(content, 'utf-8').digest('hex'),
                    size: stat.size,
                    mtime_ms: stat.mtimeMs,
                };
            } else {
                files[op.path] = { existed: false };
                filesCreated.push(op.path);
            }
        }

        const snapshot = {
            task_id: taskId,
            created_at: new Date().toISOString(),
            workspace_root: this.workspaceRoot,
            files,
        };

        try {
            fs.mkdirSync(snapshotDir, { recursive: true });
            fs.writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2), 'utf-8');
            console.log(`[FileOpsHandler] 📸 快照已生成: ${snapshotPath} (${Object.keys(files).length} 个文件)`);
        } catch (e) {
            console.error(`[FileOpsHandler] ⚠️ 快照生成失败（不影响写盘，但失去回滚能力）: ${e.message}`);
        }

        return {
            snapshot_path: snapshotPath,
            files_snapshotted: Object.keys(files).length,
            files_created: filesCreated,
        };
    }

    /**
     * 治理快照目录：<workspaceRoot>/.alphapilot/governance/<taskId>
     */
    _governanceDir(taskId) {
        return path.join(this.workspaceRoot, '.alphapilot', 'governance', taskId);
    }

    /**
     * G4：回滚到指定任务的写盘前基线。
     * 恢复快照中 existed=true 的文件，删除快照中 existed=false 但当前存在的新增文件。
     * 返回恢复/删除的文件列表，以及错误（如有）。
     */
    rollback(taskId) {
        const snapshotPath = path.join(this._governanceDir(taskId), 'snapshot.json');
        if (!fs.existsSync(snapshotPath)) {
            return { success: false, error: `快照不存在: ${snapshotPath}` };
        }

        const snapshot = JSON.parse(fs.readFileSync(snapshotPath, 'utf-8'));
        const restored = [];
        const deleted = [];
        const errors = [];

        for (const [relPath, meta] of Object.entries(snapshot.files || {})) {
            const fullPath = path.join(this.workspaceRoot, relPath);
            try {
                if (meta.existed) {
                    fs.mkdirSync(path.dirname(fullPath), { recursive: true });
                    fs.writeFileSync(fullPath, meta.content, 'utf-8');
                    restored.push(relPath);
                } else if (fs.existsSync(fullPath)) {
                    fs.unlinkSync(fullPath);
                    deleted.push(relPath);
                }
            } catch (e) {
                errors.push({ path: relPath, error: e.message });
            }
        }

        console.log(`[FileOpsHandler] ♻️ 回滚完成: 恢复 ${restored.length} 个文件, 删除 ${deleted.length} 个文件${errors.length ? `, ${errors.length} 个错误` : ''}`);
        return { success: errors.length === 0, restored, deleted, errors };
    }

    /**
     * 读取指定任务的快照（用于审计）
     */
    getSnapshot(taskId) {
        const snapshotPath = path.join(this._governanceDir(taskId), 'snapshot.json');
        if (!fs.existsSync(snapshotPath)) {
            return null;
        }
        return JSON.parse(fs.readFileSync(snapshotPath, 'utf-8'));
    }
}

module.exports = { FileOpsHandler };