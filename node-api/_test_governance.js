// node-api/_test_governance.js
// ---------------------------------------------------------
// G1/G2/G4 生产层故障注入测试（Node.js FileOpsHandler）
// 验证：写盘前自动快照(SHA256) -> 写盘 -> 失败回滚 -> 基线不变
// 不依赖测试框架，直接 `node _test_governance.js` 运行。
// ---------------------------------------------------------

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const assert = require('assert');
const { FileOpsHandler } = require('./fileOpsHandler');

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'alphapilot_gov_'));
const ws = path.join(tmpRoot, 'ws');
fs.mkdirSync(path.join(ws, 'backend'), { recursive: true });

const ORIGINAL = '# backend/service.py\ndef add(a, b):\n    return a + b\n';
const BROKEN = '# backend/service.py (injected bug)\ndef add(a, b):\n    return a - b\n';
fs.writeFileSync(path.join(ws, 'backend', 'service.py'), ORIGINAL, 'utf-8');

const handler = new FileOpsHandler(ws);
let passed = 0;

async function check(name, fn) {
    await fn();
    passed += 1;
    console.log(`  PASS  ${name}`);
}

(async () => {
    console.log('AlphaPilot Node.js 治理故障注入测试\n');

    // T1: 写盘前自动快照，含 SHA256 且识别原始内容
    await check('G1 快照生成 + SHA256 基线识别', async () => {
        const result = await handler.handleRequest(
            [{ op: 'modify', path: 'backend/service.py', content: BROKEN }],
            'task_inject_1'
        );
        assert.strictEqual(result.success, true, '写盘应成功');
        assert.ok(result.governance, '应返回 governance 元数据');
        assert.strictEqual(result.governance.task_id, 'task_inject_1');

        const snap = handler.getSnapshot('task_inject_1');
        assert.ok(snap, '快照应存在');
        assert.strictEqual(snap.files['backend/service.py'].existed, true);
        assert.strictEqual(snap.files['backend/service.py'].content, ORIGINAL);
        assert.strictEqual(
            snap.files['backend/service.py'].sha256,
            crypto.createHash('sha256').update(ORIGINAL, 'utf-8').digest('hex')
        );
        assert.strictEqual(
            fs.readFileSync(path.join(ws, 'backend', 'service.py'), 'utf-8'),
            BROKEN,
            '写盘后内容应为破坏版'
        );
    });

    // T2: 失败回滚恢复基线
    await check('G4 回滚恢复基线内容', () => {
        const r = handler.rollback('task_inject_1');
        assert.strictEqual(r.success, true);
        assert.ok(r.restored.includes('backend/service.py'));
        assert.strictEqual(
            fs.readFileSync(path.join(ws, 'backend', 'service.py'), 'utf-8'),
            ORIGINAL,
            '回滚后内容应恢复为原始基线'
        );
    });

    // T3: 新增文件在回滚时被删除
    await check('G4 回滚删除新增文件', async () => {
        await handler.handleRequest(
            [{ op: 'create', path: 'backend/extra.py', content: 'x = 1\n' }],
            'task_inject_2'
        );
        assert.ok(fs.existsSync(path.join(ws, 'backend', 'extra.py')), '新增文件应已写入');
        const snap = handler.getSnapshot('task_inject_2');
        assert.strictEqual(snap.files['backend/extra.py'].existed, false, '快照应标记为新增');

        const r = handler.rollback('task_inject_2');
        assert.ok(r.deleted.includes('backend/extra.py'), '新增文件应被删除');
        assert.ok(!fs.existsSync(path.join(ws, 'backend', 'extra.py')), '新增文件应不存在');
    });

    // T4: 无快照回滚应报错
    await check('G4 无快照回滚被拒绝', () => {
        const r = handler.rollback('task_never_existed');
        assert.strictEqual(r.success, false);
        assert.ok(r.error.includes('快照不存在'), '应提示快照不存在');
    });

    // T5: 路径校验仍生效（敏感路径拒绝）
    await check('安全校验不受治理影响', () => {
        const r0 = handler.validator.validateOp({ op: 'delete', path: '.git/config' });
        assert.strictEqual(r0.valid, false, '敏感路径应被拒绝');
    });

    console.log(`\n  ${passed}/5 通过 ✅`);
    fs.rmSync(tmpRoot, { recursive: true, force: true });
    console.log('  临时工作区已清理');
})().catch((e) => {
    console.error('\n  ❌ 测试失败:', e);
    fs.rmSync(tmpRoot, { recursive: true, force: true });
    process.exit(1);
});