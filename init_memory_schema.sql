-- ============================================================
-- AlphaPilot 记忆中枢 - 数据库初始化脚本
-- 架构：海马体-新皮层协作模式
-- 版本：v2.1.0 — 本地 BGE-small-zh (512维) + 三层租户隔离
-- ============================================================

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector 向量扩展
CREATE EXTENSION IF NOT EXISTS pgcrypto;        -- 加密扩展（用于 gen_random_uuid）

-- ============================================================
-- 1. 用户画像与偏好表（确定性知识，精确查询）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    global_preferences JSONB NOT NULL DEFAULT '{}',
    domain_expertise JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE user_profiles IS '用户画像与偏好表 - 系统必须严格遵守的硬规则';

-- ============================================================
-- 2. 记忆条目主表（带生命周期与价值评估 + 三层隔离）
-- ============================================================
DO $$
DECLARE
    vec_dim INT := 512;  -- BGE-small-zh (24MB, 512维, 零 API 成本)
    table_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'memory_items'
    ) INTO table_exists;

    IF table_exists THEN
        RAISE NOTICE 'memory_items 表已存在, 执行增量迁移...';
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'memory_items' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE memory_items ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
            RAISE NOTICE '  已添加 tenant_id 列';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'memory_items' AND column_name = 'session_id'
        ) THEN
            ALTER TABLE memory_items ADD COLUMN session_id UUID;
            RAISE NOTICE '  已添加 session_id 列';
        END IF;

    ELSE
        RAISE NOTICE '创建 memory_items 表 (vector 维度: %)...', vec_dim;
        
        EXECUTE format('
            CREATE TABLE memory_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT ''default'',
                session_id UUID,

                content TEXT NOT NULL,
                summary TEXT,
                embedding vector(%s),

                memory_type TEXT NOT NULL,
                domain_tags TEXT[],

                importance_score FLOAT DEFAULT 0.5,
                activation_score FLOAT DEFAULT 1.0,
                access_count INT DEFAULT 0,
                last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),

                status TEXT DEFAULT ''active'',
                merged_into UUID
            )', vec_dim);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_memory_per_user
    ON memory_items(user_id, memory_type, md5(content));

CREATE INDEX IF NOT EXISTS idx_mem_tenant_project ON memory_items(tenant_id, user_id, status);
CREATE INDEX IF NOT EXISTS idx_mem_tenant_session ON memory_items(tenant_id, session_id);

DROP INDEX IF EXISTS idx_mem_user_type;

CREATE INDEX IF NOT EXISTS idx_mem_activation ON memory_items(user_id, activation_score DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_mem_importance ON memory_items(user_id, importance_score DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_mem_created ON memory_items(user_id, created_at DESC)
    WHERE status = 'active';

-- HNSW 向量索引（高性能近似最近邻搜索）
CREATE INDEX IF NOT EXISTS idx_mem_embedding ON memory_items
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMENT ON TABLE memory_items IS '记忆条目主表 - 每条记忆都有生命值的记忆系统核心';

-- ============================================================
-- 3. 记忆关联图谱（让记忆产生"联想"）
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_edges (
    source_id UUID REFERENCES memory_items(id) ON DELETE CASCADE,
    target_id UUID REFERENCES memory_items(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    strength FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (source_id, target_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_edge_source ON memory_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edge_target ON memory_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edge_relation ON memory_edges(relation_type);

COMMENT ON TABLE memory_edges IS '记忆关联图谱 - 让记忆产生联想的知识图谱';

-- ============================================================
-- 4. 记忆审计日志（完全可追溯）
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    memory_id UUID,
    action TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON memory_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_memory ON memory_audit_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON memory_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_time ON memory_audit_log(created_at DESC);

COMMENT ON TABLE memory_audit_log IS '记忆审计日志 - 所有记忆的创建、访问、修改、删除都记录审计日志';

-- ============================================================
-- 5. 辅助函数：更新 updated_at 时间戳
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE
    ON user_profiles FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 6. 辅助函数：激活度提升（访问即激活）
-- ============================================================
CREATE OR REPLACE FUNCTION bump_memory_activation(memory_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE memory_items
    SET 
        activation_score = LEAST(1.0, activation_score + 0.1),
        access_count = access_count + 1,
        last_accessed_at = NOW()
    WHERE id = memory_uuid AND status = 'active';
END;
$$ language 'plpgsql';

COMMENT ON FUNCTION bump_memory_activation IS '激活度提升函数 - 访问即激活，模拟人类记忆的强化机制';

-- ============================================================
-- 7. 辅助函数：向量相似度搜索 (v2 — 三层租户隔离 + 本地 BGE 512维)
-- ============================================================
CREATE OR REPLACE FUNCTION search_similar_memories_v2(
    query_embedding vector,
    target_tenant_id TEXT,
    target_user_id TEXT,
    top_k INT DEFAULT 5,
    min_activation FLOAT DEFAULT 0.3
)
RETURNS TABLE(
    id UUID,
    content TEXT,
    summary TEXT,
    memory_type TEXT,
    importance_score FLOAT,
    activation_score FLOAT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.content,
        m.summary,
        m.memory_type,
        m.importance_score,
        m.activation_score,
        1 - (m.embedding <=> query_embedding) AS similarity
    FROM memory_items m
    WHERE
        m.tenant_id = target_tenant_id
        AND m.user_id = target_user_id
        AND m.status = 'active'
        AND m.activation_score >= min_activation
        AND m.embedding IS NOT NULL
    ORDER BY m.embedding <=> query_embedding
    LIMIT top_k;
END;
$$ language 'plpgsql';

COMMENT ON FUNCTION search_similar_memories_v2 IS '三层租户隔离向量相似度搜索 (本地 BGE 512维)';