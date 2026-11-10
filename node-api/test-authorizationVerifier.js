// node-api/test-authorizationVerifier.js
// R6 安全契约：授权验证器单元测试
// 使用 Node.js 内置 test runner (node --test)

const assert = require("node:assert/strict");
const test = require("node:test");
const { AuthorizationVerifier } = require("./authorizationVerifier");

class FakeRedis {
    constructor() {
        this.store = new Map();
    }

    async get(key) {
        return this.store.get(key) || null;
    }

    async set(key, value, opts) {
        this.store.set(key, value);
        return "OK";
    }

    async del(key) {
        this.store.delete(key);
        return 1;
    }
}

class BrokenRedis {
    async get() {
        throw new Error("Connection refused");
    }
}

function makeAuthData(taskId, overrides = {}) {
    const defaultAuth = { type: "write", paths: ["src/app.py", "src/utils.py"], status: "approved" };
    return {
        task_id: taskId,
        workspace_path: overrides.workspace_path || "/workspace",
        authorizations: overrides.authorizations || [defaultAuth],
        created_at: overrides.created_at || Date.now() / 1000 - 10,
        expires_at:
            overrides.expires_at || Date.now() / 1000 + 3600,
    };
}

test("AuthorizationVerifier: 无 task_id 时拒绝执行", async () => {
    const verifier = new AuthorizationVerifier({ primaryRedis: new FakeRedis() });
    const result = await verifier.verifyExecutionAuthorization("", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("task_id"));
});

test("AuthorizationVerifier: 空操作列表跳过验证，直接通过", async () => {
    const verifier = new AuthorizationVerifier({ primaryRedis: new FakeRedis() });
    const result = await verifier.verifyExecutionAuthorization("task-1", []);
    assert.equal(result.authorized, true);

    const result2 = await verifier.verifyExecutionAuthorization("task-1", null);
    assert.equal(result2.authorized, true);
});

test("AuthorizationVerifier: auth 条目不存在时拒绝", async () => {
    const verifier = new AuthorizationVerifier({ primaryRedis: new FakeRedis() });
    const result = await verifier.verifyExecutionAuthorization("task-unknown", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("未找到"));
});

test("AuthorizationVerifier: 类型匹配通过", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(makeAuthData("task-1"))
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
        { op: "modify", path: "src/utils.py" },
    ]);

    assert.equal(result.authorized, true);
});

test("AuthorizationVerifier: 类型不匹配拒绝", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [{ type: "write", paths: ["src/app.py"], status: "approved" }],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "delete", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("delete"));
});

test("AuthorizationVerifier: 路径不匹配拒绝", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [{ type: "write", paths: ["src/app.py"], status: "approved" }],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "secrets.env" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("secrets.env"));
});

test("AuthorizationVerifier: 授权过期拒绝", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                createdAt: Date.now() / 1000 - 7200,
                expiresAt: Date.now() / 1000 - 3600,
                created_at: Date.now() / 1000 - 7200,
                expires_at: Date.now() / 1000 - 3600,
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("过期"));
});

test("AuthorizationVerifier: meta/depends 操作跳过类型验证", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [{ type: "write", paths: ["src/app.py"], status: "approved" }],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "meta", data: { version: "1.0" } },
        { op: "depends", data: { deps: ["pandas"] } },
    ]);

    assert.equal(result.authorized, true);
});

test("AuthorizationVerifier: 混合操作中拒绝非授权类型", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [{ type: "write", paths: ["src/app.py"], status: "approved" }],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
        { op: "delete", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("delete"));
});

test("AuthorizationVerifier: Redis 故障不抛出，静默回退为授权拒绝", async () => {
    const verifier = new AuthorizationVerifier({
        primaryRedis: new BrokenRedis(),
    });

    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("未找到"));
});

test("AuthorizationVerifier: 多 Redis 实例 fallback", async () => {
    const brokenPrimary = new BrokenRedis();
    const localRedis = new FakeRedis();
    localRedis.store.set(
        "auth:task-1",
        JSON.stringify(makeAuthData("task-1"))
    );

    const verifier = new AuthorizationVerifier({
        primaryRedis: brokenPrimary,
        localRedis: localRedis,
    });

    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, true);
});

test("AuthorizationVerifier: test 操作需要 test 类型授权", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [
                    { type: "write", paths: ["src/tests/test_app.py"], status: "approved" },
                    { type: "test", command: "pytest tests/", status: "approved" },
                ],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "test", command: "pytest tests/" },
    ]);

    assert.equal(result.authorized, true);
});

test("AuthorizationVerifier: 无 paths 限制时跳过路径验证", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [{ type: "write", status: "approved" }],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "any/path/file.py" },
    ]);

    assert.equal(result.authorized, true);
});

test("AuthorizationVerifier: 路径子目录匹配通过", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [{ type: "write", paths: ["src/"], status: "approved" }],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/subdir/deep/file.py" },
    ]);

    assert.equal(result.authorized, true);
});

// ═══════════════════════════════════════════════════════════
// R6 第③步：审批状态验证 + approveAuthorization 方法
// ═══════════════════════════════════════════════════════════

test("AuthorizationVerifier: awaiting_host_policy 状态拒绝执行", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [
                    { type: "write", paths: ["src/app.py"], status: "awaiting_host_policy" },
                ],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
    assert.ok(result.reason.includes("尚未通过用户审批"));
});

test("AuthorizationVerifier: 无 status 字段的授权视为未审批拒绝", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [
                    { type: "write", paths: ["src/app.py"] },
                ],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
    ]);

    assert.equal(result.authorized, false);
});

test("approveAuthorization: 将 awaiting_host_policy 更新为 approved", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [
                    { type: "write", paths: ["src/app.py"], status: "awaiting_host_policy" },
                    { type: "test", command: "pytest", status: "awaiting_host_policy" },
                ],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.approveAuthorization("task-1");

    assert.equal(result.success, true);
    assert.equal(result.approvedCount, 2);

    const updatedRaw = await fakeRedis.get("auth:task-1");
    const updated = JSON.parse(updatedRaw);
    assert.equal(updated.authorizations[0].status, "approved");
    assert.equal(updated.authorizations[1].status, "approved");
});

test("approveAuthorization: 审批后验证通过", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [
                    { type: "write", paths: ["src/app.py"], status: "awaiting_host_policy" },
                ],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });

    const approveResult = await verifier.approveAuthorization("task-1");
    assert.equal(approveResult.success, true);

    const verifyResult = await verifier.verifyExecutionAuthorization("task-1", [
        { op: "create", path: "src/app.py" },
    ]);
    assert.equal(verifyResult.authorized, true);
});

test("approveAuthorization: 无 task_id 返回失败", async () => {
    const verifier = new AuthorizationVerifier({ primaryRedis: new FakeRedis() });
    const result = await verifier.approveAuthorization("");
    assert.equal(result.success, false);
    assert.ok(result.reason.includes("task_id"));
});

test("approveAuthorization: auth 条目不存在返回失败", async () => {
    const verifier = new AuthorizationVerifier({ primaryRedis: new FakeRedis() });
    const result = await verifier.approveAuthorization("task-unknown");
    assert.equal(result.success, false);
    assert.ok(result.reason.includes("未找到"));
});

test("approveAuthorization: 重复审批幂等", async () => {
    const fakeRedis = new FakeRedis();
    fakeRedis.store.set(
        "auth:task-1",
        JSON.stringify(
            makeAuthData("task-1", {
                authorizations: [
                    { type: "write", paths: ["src/app.py"], status: "approved" },
                ],
            })
        )
    );

    const verifier = new AuthorizationVerifier({ primaryRedis: fakeRedis });
    const result = await verifier.approveAuthorization("task-1");

    assert.equal(result.success, true);
    assert.equal(result.approvedCount, 0);
    assert.ok(result.reason.includes("已经审批通过"));
});