const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { FileOpsHandler } = require('./fileOpsHandler');

test('rejects paths escaping the workspace, including sibling-prefix paths', () => {
    const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'alphapilot-fileops-'));
    const workspace = path.join(parent, 'workspace');
    fs.mkdirSync(workspace);

    try {
        const validator = new FileOpsHandler(workspace).validator;
        assert.equal(validator.validatePath('src/main.py').valid, true);
        assert.equal(validator.validatePath('../workspace-outside/main.py').valid, false);
        assert.equal(validator.validatePath(path.join(parent, 'outside.py')).valid, false);
    } finally {
        fs.rmSync(parent, { recursive: true, force: true });
    }
});

test('reports partial FileOps failures instead of returning success', async () => {
    const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'alphapilot-fileops-'));
    const workspace = path.join(parent, 'workspace');
    fs.mkdirSync(workspace);
    fs.mkdirSync(path.join(workspace, 'blocked'));

    try {
        const handler = new FileOpsHandler(workspace);
        const result = await handler.handleRequest([
            { op: 'create', path: 'created.py', content: 'print("ok")' },
            { op: 'create', path: 'blocked', content: 'cannot replace a directory' },
        ]);

        assert.equal(result.success, false);
        assert.equal(result.files.length, 1);
        assert.equal(result.errors.length, 1);
        assert.equal(fs.readFileSync(path.join(workspace, 'created.py'), 'utf-8'), 'print("ok")');
    } finally {
        fs.rmSync(parent, { recursive: true, force: true });
    }
});
