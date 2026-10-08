const express = require('express');
const { spawn } = require('child_process');

const fileOpsHandler = require('../fileOpsHandler');
const memoryService = require('../services/memoryService');

// export a factory so index.js can pass the Socket.IO `io` instance
module.exports = function(io) {
    const router = express.Router();

    async function runNpmInstall(workspace, packages) {
        return new Promise((resolve) => {
            const args = ['install', '--no-save', ...packages];
            const proc = spawn('npm', args, { cwd: workspace, shell: false });
            let out = '';
            let err = '';
            proc.stdout.on('data', d => out += d.toString());
            proc.stderr.on('data', d => err += d.toString());
            proc.on('close', code => resolve({ code, out, err }));
        });
    }

    async function runPipInstall(packages) {
        return new Promise((resolve) => {
            const args = ['-m', 'pip', 'install', '--user', ...packages];
            const proc = spawn(process.execPath, args, { shell: false });
            let out = '';
            let err = '';
            proc.stdout.on('data', d => out += d.toString());
            proc.stderr.on('data', d => err += d.toString());
            proc.on('close', code => resolve({ code, out, err }));
        });
    }

/**
 * V4 notify 接口：接收 Worker V4 的多阶段结果
 * 支持处理：file_ops, test_ops, install_ops, fix_ops, run_ops
 */
    router.post('/notify/:task_id', async (req, res) => {
        const { task_id } = req.params;
        const payload = req.body;

        console.log(`\n[V4 Router] 收到 V4 notify: ${task_id}`);
        console.log(JSON.stringify(payload, null, 2));

    // 更新 Memory（尽量降级容错）
    try {
        const status = payload.status || 'done';
        const summary = payload.summary || '';
        await memoryService.updateTaskStatus(task_id, status, summary);
    } catch (err) {
        console.error('[V4 Router] 更新 Memory 失败:', err.message);
    }

    // 处理 context 中的 ops
        const ops = payload.context?.ops || [];
        for (const op of ops) {
            try {
                if (op.type === 'file_ops' && Array.isArray(op.actions)) {
                    console.log('[V4 Router] 执行 file_ops -> 转交 FileOpsHandler');
                    // 过滤内部元数据再执行
                    const filtered = (op.actions || []).filter(a => !a._internal);
                    await fileOpsHandler.handleRequest(filtered);
                } else if (op.type === 'test_ops') {
                    console.log('[V4 Router] 收到 test_ops，广播给前端并记录');
                    if (io) io.emit('v4_test_ops', { task_id, ops: op.actions || [] });
                } else if (op.type === 'install_ops') {
                    console.log('[V4 Router] 收到 install_ops，开始自动执行（受限于 workspace）');
                    // actions 格式支持 { manager: 'npm'|'pip', packages: [] }
                    const actions = op.actions || [];
                    for (const a of actions) {
                        try {
                            if (a.manager === 'npm' && Array.isArray(a.packages)) {
                                const workspace = fileOpsHandler.workspaceRoot || process.cwd();
                                if (io) io.emit('v4_install_start', { task_id, manager: 'npm', packages: a.packages });
                                const result = await runNpmInstall(workspace, a.packages);
                                console.log('[V4 Router] npm install 结果:', result.code);
                                if (io) io.emit('v4_install_result', { task_id, manager: 'npm', packages: a.packages, result });
                            } else if (a.manager === 'pip' && Array.isArray(a.packages)) {
                                if (io) io.emit('v4_install_start', { task_id, manager: 'pip', packages: a.packages });
                                const result = await runPipInstall(a.packages);
                                console.log('[V4 Router] pip install 结果:', result.code);
                                if (io) io.emit('v4_install_result', { task_id, manager: 'pip', packages: a.packages, result });
                            } else {
                                console.log('[V4 Router] install_ops 中包含无法识别的 action，跳过', a);
                                if (io) io.emit('v4_install_skipped', { task_id, action: a });
                            }
                        } catch (innerErr) {
                            console.error('[V4 Router] 执行 install action 失败:', innerErr.message);
                            if (io) io.emit('v4_install_error', { task_id, error: innerErr.message });
                        }
                    }
                } else if (op.type === 'fix_ops') {
                    console.log('[V4 Router] 收到 fix_ops（记录并广播）');
                    if (io) io.emit('v4_fix_ops', { task_id, ops: op.actions || [] });
                } else if (op.type === 'run_ops') {
                    console.log('[V4 Router] 收到 run_ops（需要人工确认，已广播）');
                    // run_ops 需要人工确认 — 广播给前端并等待人工批准
                    if (io) io.emit('v4_run_ops_request', { task_id, ops: op.actions || [] });
                } else {
                    console.log('[V4 Router] 未知 op.type:', op.type);
                }
            } catch (err) {
                console.error('[V4 Router] 处理 op 失败:', err.message);
            }
        }

        // 兼容性：返回同 /task/notify 的格式
        res.json({ status: 'notified_v4' });
    });

    return router;
};
