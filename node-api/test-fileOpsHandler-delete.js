const test = require('node:test');
const assert = require('node:assert/strict');
const { FileOpsHandler } = require('./fileOpsHandler');

test('FileOpsHandler refuses sensitive delete targets', () => {
    const handler = new FileOpsHandler(process.cwd());
    const result = handler.validator.validateOp({ op: 'delete', path: '.env.local' });
    assert.equal(result.valid, false);
    assert.match(result.error, /敏感路径/);
});

test('FileOpsHandler never permanently deletes files through the API executor', async () => {
    const executor = new FileOpsHandler(process.cwd()).executor;
    await assert.rejects(
        executor.executeOp({ op: 'delete', path: 'not-created-by-this-test.txt' }),
        /VS Code 工作区删除工具/,
    );
});
