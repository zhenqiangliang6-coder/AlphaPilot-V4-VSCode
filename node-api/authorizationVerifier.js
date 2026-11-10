// node-api/authorizationVerifier.js
// ---------------------------------------------------------
// R6 Minimum Security Contract — Authorization Verifier
// Node.js 执行端独立授权验证层
//
// 架构信条：
//   - Worker = 真相（只有 Worker 创建 auth:{task_id}）
//   - Node API = 透明管道（只读验证，不修改 auth 条目）
//   - 协议 = 宪法（授权必须绑定具体操作）
//
// 契约规则（冻结 v1.0）：
//   1. 授权必须绑定具体操作（类型匹配 + 对象匹配）
//   2. 执行端必须独立验证执行许可
//   3. 授权、执行结果、任务终态是三个不同的事实
// ---------------------------------------------------------

const { Redis } = require("@upstash/redis");

class AuthorizationVerifier {
    /**
     * @param {object} options
     * @param {object} options.primaryRedis - Upstash Redis 实例
     * @param {object} [options.localRedis] - 本地 Docker Redis 实例（可选）
     * @param {object} [options.tairRedis] - 阿里云 Tair Redis 实例（可选）
     */
    constructor(options = {}) {
        this.primaryRedis = options.primaryRedis || null;
        this.localRedis = options.localRedis || null;
        this.tairRedis = options.tairRedis || null;
    }

    /**
     * 从所有已配置的 Redis 实例中查找授权条目
     * @param {string} taskId
     * @returns {Promise<object|null>} 授权的 auth data 或 null
     */
    async _fetchAuthData(taskId) {
        const authKey = `auth:${taskId}`;
        const redisInstances = [
            { name: "upstash", client: this.primaryRedis },
            { name: "local", client: this.localRedis },
            { name: "tair", client: this.tairRedis },
        ].filter((r) => r.client !== null);

        for (const instance of redisInstances) {
            try {
                const raw = await instance.client.get(authKey);
                if (raw) {
                    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
                    console.log(
                        `   🔒 [AuthVerifier] 从 ${instance.name} 读取 auth:${taskId}`
                    );
                    return data;
                }
            } catch (err) {
                console.warn(
                    `   ⚠️ [AuthVerifier] ${instance.name} 读取 auth:${taskId} 失败:`,
                    err.message
                );
            }
        }

        return null;
    }

    /**
     * 验证操作类型是否在授权列表中
     * @param {string} opType - 操作类型 (create/modify/delete/test/doc/meta/depends)
     * @param {Array<object>} authorizations - 授权列表
     * @returns {{ valid: boolean, matchedAuth?: object, reason?: string }}
     */
    _verifyOpType(opType, authorizations) {
        const opAuthTypeMap = {
            create: "write",
            modify: "write",
            delete: "delete",
            test: "test",
            doc: "write",
            meta: "meta",
            depends: "depends",
        };

        const mappedType = opAuthTypeMap[opType] || opType;

        for (const auth of authorizations) {
            const authType = (auth.type || "").toLowerCase();
            if (authType === mappedType || authType === opType) {
                return { valid: true, matchedAuth: auth };
            }
        }

        return {
            valid: false,
            reason: `操作类型 "${opType}" (映射: ${mappedType}) 未在授权列表中`,
        };
    }

    /**
     * 验证路径是否在授权范围内
     * @param {string} opPath - 操作路径
     * @param {object} matchedAuth - 匹配的授权条目
     * @returns {{ valid: boolean, reason?: string }}
     */
    _verifyPath(opPath, matchedAuth) {
        if (!matchedAuth.paths || matchedAuth.paths.length === 0) {
            return { valid: true };
        }

        const normalizedOpPath = opPath.replace(/\\/g, "/");

        for (const authPath of matchedAuth.paths) {
            const normalizedAuthPath = authPath.replace(/\\/g, "/");
            if (
                normalizedOpPath === normalizedAuthPath ||
                normalizedOpPath.startsWith(normalizedAuthPath + "/") ||
                normalizedOpPath.endsWith("/" + normalizedAuthPath) ||
                normalizedOpPath.includes(normalizedAuthPath)
            ) {
                return { valid: true };
            }
        }

        return {
            valid: false,
            reason: `路径 "${opPath}" 不在授权范围内 (允许: ${matchedAuth.paths.join(", ")})`,
        };
    }

    /**
     * 验证授权有效期
     * @param {object} authData - 授权数据
     * @returns {{ valid: boolean, reason?: string }}
     */
    _verifyExpiry(authData) {
        const now = Date.now() / 1000;
        const expiresAt = authData.expires_at || (authData.created_at || 0) + 3600;

        if (now > expiresAt) {
            return {
                valid: false,
                reason: `授权已过期 (expires_at: ${new Date(expiresAt * 1000).toISOString()})`,
            };
        }

        return { valid: true };
    }

    /**
     * 验证授权条目的审批状态
     * @param {object} matchedAuth - 匹配的授权条目
     * @returns {{ valid: boolean, reason?: string }}
     */
    _verifyApprovalStatus(matchedAuth) {
        const status = (matchedAuth.status || "").toLowerCase();

        if (status === "approved") {
            return { valid: true };
        }

        if (status === "awaiting_host_policy") {
            return {
                valid: false,
                reason: `授权类型 "${matchedAuth.type}" 尚未通过用户审批 (status: awaiting_host_policy)`,
            };
        }

        return {
            valid: false,
            reason: `授权类型 "${matchedAuth.type}" 状态异常: ${status || "unknown"}`,
        };
    }

    /**
     * 写入授权数据回 Redis（用于审批端点更新状态）
     * @param {string} taskId
     * @param {object} authData
     * @param {number} ttlSeconds
     */
    async _writeAuthData(taskId, authData, ttlSeconds) {
        const authKey = `auth:${taskId}`;
        const redisInstances = [
            { name: "upstash", client: this.primaryRedis },
            { name: "local", client: this.localRedis },
            { name: "tair", client: this.tairRedis },
        ].filter((r) => r.client !== null);

        const payload = JSON.stringify(authData);

        for (const instance of redisInstances) {
            try {
                const existing = await instance.client.get(authKey);
                if (existing) {
                    await instance.client.set(authKey, payload, { ex: ttlSeconds });
                    console.log(
                        `   ✍️ [AuthVerifier] 已更新 ${instance.name} auth:${taskId}`
                    );
                    return { success: true, redisInstance: instance.name };
                }
            } catch (err) {
                console.warn(
                    `   ⚠️ [AuthVerifier] ${instance.name} 写入 auth:${taskId} 失败:`,
                    err.message
                );
            }
        }

        return { success: false, reason: "未在任何 Redis 实例中找到授权条目" };
    }

    /**
     * 处理用户审批：将授权状态从 awaiting_host_policy 更新为 approved
     * 这是 Node.js 端唯一可以修改 auth 条目的入口
     *
     * @param {string} taskId - 任务 ID
     * @returns {Promise<{ success: boolean, approvedCount?: number, reason?: string }>}
     */
    async approveAuthorization(taskId) {
        if (!taskId) {
            return { success: false, reason: "缺少 task_id" };
        }

        console.log(`   🔓 [AuthVerifier] 处理审批: task_id=${taskId}`);

        const authData = await this._fetchAuthData(taskId);

        if (!authData) {
            return {
                success: false,
                reason: `未找到任务 ${taskId} 的授权记录`,
            };
        }

        if (!authData.authorizations || !Array.isArray(authData.authorizations)) {
            return {
                success: false,
                reason: "授权记录中无 authorizations 字段",
            };
        }

        let approvedCount = 0;
        let alreadyApproved = 0;

        for (const auth of authData.authorizations) {
            const status = (auth.status || "").toLowerCase();
            if (status === "awaiting_host_policy") {
                auth.status = "approved";
                approvedCount++;
            } else if (status === "approved") {
                alreadyApproved++;
            }
        }

        if (approvedCount === 0 && alreadyApproved > 0) {
            return {
                success: true,
                approvedCount: 0,
                reason: `所有 ${alreadyApproved} 项授权已经审批通过`,
            };
        }

        if (approvedCount === 0) {
            return {
                success: false,
                reason: "没有待审批的授权项",
            };
        }

        const ttlSeconds = 3600;
        const writeResult = await this._writeAuthData(taskId, authData, ttlSeconds);

        if (!writeResult.success) {
            return {
                success: false,
                reason: `Redis 写入失败: ${writeResult.reason}`,
            };
        }

        console.log(
            `   ✅ [AuthVerifier] 审批完成: ${approvedCount} 项已审批` +
            (alreadyApproved > 0 ? `, ${alreadyApproved} 项已此前通过` : "")
        );

        return { success: true, approvedCount };
    }

    /**
     * 独立验证执行许可
     *
     * @param {string} taskId - 任务 ID
     * @param {Array<object>} fileOps - 待执行的文件操作列表
     * @returns {Promise<{ authorized: boolean, reason?: string, authSource?: string }>}
     */
    async verifyExecutionAuthorization(taskId, fileOps) {
        if (!taskId) {
            return {
                authorized: false,
                reason: "缺少 task_id，无法验证执行授权",
            };
        }

        if (!fileOps || !Array.isArray(fileOps) || fileOps.length === 0) {
            return { authorized: true };
        }

        console.log(
            `   🔒 [AuthVerifier] 验证 task_id=${taskId} 的 ${fileOps.length} 个操作授权`
        );

        const authData = await this._fetchAuthData(taskId);

        if (!authData) {
            return {
                authorized: false,
                reason: `未找到任务 ${taskId} 的授权记录 (auth:${taskId} 不存在或已过期)`,
            };
        }

        if (!authData.authorizations || !Array.isArray(authData.authorizations)) {
            return {
                authorized: false,
                reason: `任务 ${taskId} 的授权记录中无 authorizations 字段`,
            };
        }

        const expiryCheck = this._verifyExpiry(authData);
        if (!expiryCheck.valid) {
            return {
                authorized: false,
                reason: expiryCheck.reason,
                authSource: authData.workspace_path || "unknown",
            };
        }

        for (let i = 0; i < fileOps.length; i++) {
            const op = fileOps[i];
            const opType = op.op;

            if (!opType) {
                return {
                    authorized: false,
                    reason: `FileOp[${i}] 缺少 op 字段`,
                };
            }

            if (["meta", "depends"].includes(opType)) {
                continue;
            }

            const typeCheck = this._verifyOpType(opType, authData.authorizations);
            if (!typeCheck.valid) {
                return {
                    authorized: false,
                    reason: `FileOp[${i}] ${typeCheck.reason}`,
                    authSource: authData.workspace_path || "unknown",
                };
            }

            const approvalCheck = this._verifyApprovalStatus(typeCheck.matchedAuth);
            if (!approvalCheck.valid) {
                return {
                    authorized: false,
                    reason: `FileOp[${i}] ${approvalCheck.reason}`,
                    authSource: authData.workspace_path || "unknown",
                };
            }

            if (op.path && typeCheck.matchedAuth) {
                const pathCheck = this._verifyPath(op.path, typeCheck.matchedAuth);
                if (!pathCheck.valid) {
                    return {
                        authorized: false,
                        reason: `FileOp[${i}] ${pathCheck.reason}`,
                        authSource: authData.workspace_path || "unknown",
                    };
                }
            }
        }

        console.log(
            `   ✅ [AuthVerifier] task_id=${taskId} 授权验证通过 (${fileOps.length} 个操作)`
        );

        return {
            authorized: true,
            authSource: authData.workspace_path || "unknown",
        };
    }
}

module.exports = { AuthorizationVerifier };