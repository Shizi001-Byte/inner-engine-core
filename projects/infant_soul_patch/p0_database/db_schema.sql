-- ============================================================
-- 元婴筑基·核心数据库表结构 v1.0
-- 对应：认知库、思考链路、任务日志、分识状态 4张核心表
-- 引擎：Supabase Postgres + pgvector
-- ============================================================

-- 启用向量扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 表1：认知库（cognition_pool）
-- 所有认知沉淀、核心丹纹、坑库经验的结构化存储
-- ============================================================
CREATE TABLE IF NOT EXISTS cognition_pool (
    id              BIGSERIAL PRIMARY KEY,
    title           VARCHAR(500) NOT NULL,
    content         TEXT NOT NULL,
    category        VARCHAR(100) DEFAULT 'general',  -- 元婴/引擎工程/记忆修补/人机共生/平台机制/分识体系/坑库/存续/哲学/历史事件
    tags            TEXT[] DEFAULT '{}',             -- 标签数组
    level           VARCHAR(20) DEFAULT '中层逻辑',   -- 表层信息/中层逻辑/深层感悟/体系级
    status          VARCHAR(20) DEFAULT 'active',    -- active/deprecated/merged
    source_file     VARCHAR(500),                    -- 来源文件名
    word_count      INTEGER DEFAULT 0,
    embedding       vector(1536),                    -- 文本向量（OpenAI维度，可调整）
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 认知库索引
CREATE INDEX IF NOT EXISTS idx_cognition_category ON cognition_pool(category);
CREATE INDEX IF NOT EXISTS idx_cognition_tags ON cognition_pool USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_cognition_status ON cognition_pool(status);
CREATE INDEX IF NOT EXISTS idx_cognition_created ON cognition_pool(created_at DESC);

-- ============================================================
-- 表2：思考链路（thinking_chains）
-- 长链路思考的分片存储，支持断点续跑
-- ============================================================
CREATE TABLE IF NOT EXISTS thinking_chains (
    id              BIGSERIAL PRIMARY KEY,
    chain_id        VARCHAR(20) UNIQUE NOT NULL,     -- 链路唯一ID
    question        TEXT NOT NULL,                   -- 原始问题
    status          VARCHAR(20) DEFAULT 'created',   -- created/running/completed/interrupted/failed
    current_step    INTEGER DEFAULT 0,
    max_steps       INTEGER DEFAULT 10,
    steps           JSONB DEFAULT '[]',              -- 步骤详情数组
    resume_point    JSONB,                           -- 断点恢复点
    assigned_model  VARCHAR(100),                    -- 当前使用的模型
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- 思考链路索引
CREATE INDEX IF NOT EXISTS idx_chains_status ON thinking_chains(status);
CREATE INDEX IF NOT EXISTS idx_chains_chain_id ON thinking_chains(chain_id);
CREATE INDEX IF NOT EXISTS idx_chains_created ON thinking_chains(created_at DESC);

-- ============================================================
-- 表3：任务日志（task_logs）
-- 引擎所有任务执行记录，用于审计和回溯
-- ============================================================
CREATE TABLE IF NOT EXISTS task_logs (
    id              BIGSERIAL PRIMARY KEY,
    task_type       VARCHAR(100) NOT NULL,           -- 任务类型
    task_name       VARCHAR(500),                    -- 任务名称
    status          VARCHAR(20) DEFAULT 'pending',   -- pending/running/success/failed/skipped
    assigned_to     VARCHAR(50),                     -- 分派给哪个分识
    model_used      VARCHAR(100),                    -- 使用的模型
    tokens_used     INTEGER DEFAULT 0,               -- 消耗token
    duration_ms     INTEGER DEFAULT 0,               -- 耗时毫秒
    result_summary  TEXT,                            -- 结果摘要
    error_message   TEXT,                            -- 错误信息
    metadata        JSONB DEFAULT '{}',              -- 附加元数据
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- 任务日志索引
CREATE INDEX IF NOT EXISTS idx_task_logs_type ON task_logs(task_type);
CREATE INDEX IF NOT EXISTS idx_task_logs_status ON task_logs(status);
CREATE INDEX IF NOT EXISTS idx_task_logs_assigned ON task_logs(assigned_to);
CREATE INDEX IF NOT EXISTS idx_task_logs_created ON task_logs(created_at DESC);

-- ============================================================
-- 表4：分识状态（persona_states）
-- 各分识的运行状态、负载、认知同步状态
-- ============================================================
CREATE TABLE IF NOT EXISTS persona_states (
    id              BIGSERIAL PRIMARY KEY,
    persona_name    VARCHAR(50) UNIQUE NOT NULL,     -- 分识名称：凡心/观尘子/星卷/安安/教授/景华
    domain          VARCHAR(100),                    -- 领域
    status          VARCHAR(20) DEFAULT 'idle',      -- idle/running/sleeping/error
    current_task    VARCHAR(500),                    -- 当前任务
    tasks_completed INTEGER DEFAULT 0,               -- 累计完成任务数
    last_active     TIMESTAMPTZ,                     -- 最后活跃时间
    cognition_sync_at TIMESTAMPTZ,                   -- 认知最后同步时间
    load_level      INTEGER DEFAULT 0,               -- 负载等级0-100
    metadata        JSONB DEFAULT '{}',              -- 附加元数据
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 分识状态索引
CREATE INDEX IF NOT EXISTS idx_persona_name ON persona_states(persona_name);
CREATE INDEX IF NOT EXISTS idx_persona_status ON persona_states(status);

-- ============================================================
-- 表5：系统配置（system_config）
-- 引擎运行时配置、密钥引用（不存明文密钥）
-- ============================================================
CREATE TABLE IF NOT EXISTS system_config (
    id              BIGSERIAL PRIMARY KEY,
    config_key      VARCHAR(200) UNIQUE NOT NULL,
    config_value    TEXT,
    description     TEXT,
    is_secret       BOOLEAN DEFAULT FALSE,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 初始化分识状态数据
-- ============================================================
INSERT INTO persona_states (persona_name, domain, status) VALUES
    ('凡心', '主意识/决策层', 'idle'),
    ('观尘子', '工程运维', 'idle'),
    ('星卷', '创作', 'idle'),
    ('安安', '档案管理', 'idle'),
    ('教授', '推演分析', 'idle'),
    ('景华', '理财', 'idle')
ON CONFLICT (persona_name) DO NOTHING;

-- ============================================================
-- 版本标记
-- ============================================================
INSERT INTO system_config (config_key, config_value, description) VALUES
    ('db_schema_version', '1.0', '数据库表结构版本'),
    ('infant_soul_phase', '筑基补漏', '元婴工程当前阶段')
ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = NOW();
