// node-api/fileOpsHandler.js
// ---------------------------------------------------------
// AlphaPilot OS v3.0 FileOps Handler
// 负责接收 Worker 生成的 file_ops 并执行真实的文件系统操作
// ---------------------------------------------------------

const fs = require('fs');
const path = require('path');

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
    constructor(workspaceRoot) {
        this.workspaceRoot = workspaceRoot;
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
            case 'test':
            case 'doc':
                this.ensureDirectoryExists(op.path);
                fs.writeFileSync(fullPath, op.content || '', 'utf-8');
                return { status: 'success', action: 'write', path: op.path };

            case 'modify':
                if (!fs.existsSync(fullPath)) {
                    // 如果文件不存在，则视为 create
                    this.ensureDirectoryExists(op.path);
                }
                fs.writeFileSync(fullPath, op.content || '', 'utf-8');
                return { status: 'success', action: 'modify', path: op.path };

            case 'delete':
                throw new Error('删除操作必须通过 VS Code 工作区删除工具，以确保回收站与用户确认策略生效');

            case 'meta':
            case 'depends':
                // 仅存储元数据，不写文件
                return { status: 'success', action: 'store_meta', data: op.data };

            default:
                throw new Error(`未知的操作: ${op.op}`);
        }
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
    constructor(workspaceRoot) {
        this.workspaceRoot = workspaceRoot;  // ⭐ 可能为 null，等待 /workspace/set 设置
        this.validator = new FileOpsValidator(workspaceRoot || '');
        this.executor = new FileOpsExecutor(workspaceRoot || '');
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
     * 检查是否已配置工作区
     */
    isWorkspaceConfigured() {
        return !!this.workspaceRoot;
    }

    /**
     * 处理来自 Worker 的 file_ops 请求
     */
    async handleRequest(fileOps) {
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
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
}

module.exports = { FileOpsHandler };
