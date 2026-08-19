-- ============================================================
-- 向量语义搜索函数（在Supabase SQL Editor执行一次即可）
-- 用法：SELECT * FROM search_cognition('搜索关键词', 5);
-- ============================================================

-- 启用pgvector（如果还没启用）
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建相似度搜索函数
CREATE OR REPLACE FUNCTION search_cognition(
    query_text TEXT,
    result_count INT DEFAULT 5
)
RETURNS TABLE (
    cognition_id UUID,
    title TEXT,
    category TEXT,
    chunk_content TEXT,
    similarity FLOAT
) AS $$
DECLARE
    query_vec vector(1536);
BEGIN
    -- 简单哈希向量（与cognition_import.py的算法一致）
    -- 注意：生产环境应替换为真实embedding API调用
    WITH words AS (
        SELECT regexp_matches(query_text, '[\u4e00-\u9fa5]{2,}|[a-zA-Z]+', 'g') AS w
    ),
    vec_calc AS (
        SELECT
            array_agg(
                COALESCE(
                    (SELECT SUM(
                        CASE WHEN (get_byte(md5(w.w[1])::bytea, 0) % 2 = 0) THEN 1.0 ELSE -1.0 END
                    ) FROM words w WHERE (get_byte(md5(w.w[1])::bytea, 0) % 1536) = i)
                , 0.0)
            ORDER BY i
        ) AS vec
        FROM generate_series(0, 1535) AS i
    )
    SELECT vec_calc.vec::vector INTO query_vec FROM vec_calc;

    -- 归一化（简化处理，实际应在应用层做）
    RETURN QUERY
    SELECT
        c.id AS cognition_id,
        c.title,
        c.category,
        cv.content AS chunk_content,
        1 - (cv.embedding <=> query_vec) AS similarity
    FROM cognition_vectors cv
    JOIN cognition c ON c.id = cv.cognition_id
    ORDER BY cv.embedding <=> query_vec
    LIMIT result_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 入站消息表（公网回调入口，替代公网IP方案）
-- QStash/飞书等外部回调直接POST到这个表的REST API
-- 引擎定时轮询处理新消息
-- ============================================================
CREATE TABLE IF NOT EXISTS incoming_messages (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,        -- qstash / lark / manual
    message_type VARCHAR(100),          -- 消息类型
    payload JSONB NOT NULL,             -- 原始消息体
    status VARCHAR(20) DEFAULT 'pending', -- pending/processing/done/failed
    result TEXT,                        -- 处理结果
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incoming_status ON incoming_messages(status);
CREATE INDEX IF NOT EXISTS idx_incoming_created ON incoming_messages(created_at DESC);

-- 允许匿名插入（回调端用anon key即可写入）
-- DROP POLICY IF EXISTS "Allow anonymous insert" ON incoming_messages;
-- CREATE POLICY "Allow anonymous insert" ON incoming_messages FOR INSERT WITH CHECK (true);
-- ALTER TABLE incoming_messages ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 版本标记
-- ============================================================
INSERT INTO system_config (config_key, config_value, description) VALUES
    ('vector_search_version', '1.0-hash', '向量搜索版本（哈希兜底，待升级embedding）'),
    ('public_gateway_mode', 'supabase_polling', '公网入口模式：Supabase表轮询')
ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = NOW();
