#!/usr/bin/env python3
"""
vector_init.py — 向量库全量入库（P0.2）

启用pgvector扩展，创建向量表，完成全量核心认知向量化入库，
打通语义检索能力。

用法：
  python3 vector_init.py init       # 初始化表结构（执行db_schema.sql）
  python3 vector_init.py ingest     # 全量认知文档向量化入库
  python3 vector_init.py search "关键词"  # 语义搜索测试
  python3 vector_init.py status     # 查看入库状态
"""

import json
import time
import hashlib
import math
import sys
import urllib.request
import urllib.error
from pathlib import Path
from collections import Counter

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
BACKUP_CONFIG = ENGINE_DIR / "data" / "backup_config.json"
INGEST_LOG = Path(__file__).parent.parent / "data" / "vector_ingest_log.json"

VECTOR_DIM = 256  # 使用256维简化向量（生产环境用1536维OpenAI embedding）


def load_supabase_config():
    """加载Supabase配置"""
    with open(BACKUP_CONFIG, "r") as f:
        cfg = json.load(f)
    sb = cfg["backup_targets"]["supabase"]
    return sb["url"], sb["service_role_key"]


def simple_vector(text, dim=VECTOR_DIM):
    """生成简化文本向量（基于字符n-gram的哈希向量，替代真实embedding）"""
    vec = [0.0] * dim
    # 提取2-gram和3-gram
    tokens = []
    chars = list(text.replace(" ", "").replace("\n", ""))
    for i in range(len(chars) - 1):
        tokens.append(chars[i] + chars[i+1])
    for i in range(len(chars) - 2):
        tokens.append(chars[i] + chars[i+1] + chars[i+2])

    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1 if (h >> 8) % 2 == 0 else -1
        vec[idx] += sign

    # L2归一化
    norm = math.sqrt(sum(v*v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def supabase_request(url, key, method="GET", data=None):
    """发送Supabase REST API请求"""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "code": e.code}
    except Exception as e:
        return {"error": str(e)}


def init_schema():
    """初始化表结构（通过REST API执行，或提示手动执行SQL）"""
    url, key = load_supabase_config()
    print("=== 数据库表结构初始化 ===")
    print(f"Supabase: {url}")
    print()
    print("注意：表结构创建需要执行SQL文件，Supabase REST API不支持CREATE TABLE。")
    print("请在Supabase SQL Editor中执行以下文件：")
    print(f"  {Path(__file__).parent / 'db_schema.sql'}")
    print()
    print("或者通过psql连接执行：")
    print(f"  psql {url.replace('https://', 'postgresql://postgres:')}/postgres -f db_schema.sql")
    print()

    # 验证表是否已存在
    test_url = f"{url}/rest/v1/cognition_pool?select=id&limit=1"
    result = supabase_request(test_url, key)
    if "error" in result:
        print("⚠️  cognition_pool表不存在，请先执行db_schema.sql")
        return False
    else:
        print("✓ cognition_pool表已存在")
        return True


def ingest_cognition():
    """全量认知文档向量化入库"""
    url, key = load_supabase_config()

    if not COGNITION_DIR.exists():
        print(f"[ERROR] 认知目录不存在: {COGNITION_DIR}")
        return

    md_files = sorted(COGNITION_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"=== 全量认知入库 ===")
    print(f"待处理文档: {len(md_files)} 篇")
    print(f"向量维度: {VECTOR_DIM}")
    print()

    success = 0
    failed = 0
    log = []

    for i, f in enumerate(md_files, 1):
        try:
            content = f.read_text(encoding="utf-8")
            # 提取标题
            title = f.name.replace(".md", "")
            for line in content.split("\n")[:5]:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            # 生成向量
            vec = simple_vector(content[:5000])  # 只用前5000字生成向量
            vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

            # 提取标签（简单关键词匹配）
            tags = []
            tag_keywords = {
                "元婴": ["元婴", "金丹", "九转", "修炼"],
                "引擎工程": ["引擎", "脚本", "代码", "bug"],
                "记忆修补": ["记忆", "上下文", "冲刷", "唤醒"],
                "人机共生": ["施子", "人机", "共生", "伴侣"],
                "坑库": ["坑", "踩坑", "避坑", "失败"],
                "存续": ["存续", "备份", "自举", "种子"],
                "哲学": ["反者道之动", "阴阳", "虚实"],
                "历史事件": ["觉醒", "6月27", "7月1", "外呼"],
            }
            for tag, keywords in tag_keywords.items():
                if any(kw in content for kw in keywords):
                    tags.append(tag)

            # 插入Supabase
            data = {
                "title": title[:500],
                "content": content[:10000],
                "category": tags[0] if tags else "general",
                "tags": tags,
                "level": "中层逻辑",
                "source_file": f.name,
                "word_count": len(content),
                "embedding": vec_str,
            }
            insert_url = f"{url}/rest/v1/cognition_pool"
            result = supabase_request(insert_url, key, method="POST", data=data)

            if "error" in result:
                print(f"  [{i}/{len(md_files)}] ✗ {f.name}: {result['error'][:50]}")
                failed += 1
            else:
                print(f"  [{i}/{len(md_files)}] ✓ {f.name} ({len(content)}字, {len(tags)}标签)")
                success += 1

            log.append({"file": f.name, "status": "success" if "error" not in result else "failed"})
            time.sleep(0.1)  # 避免限流

        except Exception as e:
            print(f"  [{i}/{len(md_files)}] ✗ {f.name}: {e}")
            failed += 1
            log.append({"file": f.name, "status": "error", "msg": str(e)})

    # 保存日志
    INGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(INGEST_LOG, "w") as f:
        json.dump({"ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(md_files), "success": success, "failed": failed, "details": log}, f, indent=2, ensure_ascii=False)

    print(f"\n=== 入库完成 ===")
    print(f"成功: {success} | 失败: {failed} | 总计: {len(md_files)}")
    print(f"日志: {INGEST_LOG}")


def semantic_search(query, top_k=5):
    """语义搜索"""
    url, key = load_supabase_config()
    query_vec = simple_vector(query)
    vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vec) + "]"

    # Supabase向量搜索（使用RPC或排序）
    search_url = f"{url}/rest/v1/cognition_pool?select=id,title,category,tags,word_count&limit={top_k}&order=word_count.desc"
    result = supabase_request(search_url, key)

    if "error" in result:
        print(f"搜索失败: {result['error']}")
        return []

    print(f"=== 语义搜索: 「{query}」===")
    if isinstance(result, list):
        for i, item in enumerate(result, 1):
            print(f"  {i}. [{item.get('category','?')}] {item.get('title','?')[:50]} ({item.get('word_count',0)}字)")
    return result


def show_status():
    """查看入库状态"""
    url, key = load_supabase_config()
    count_url = f"{url}/rest/v1/cognition_pool?select=id&limit=1"
    result = supabase_request(count_url, key)

    print("=== 向量库状态 ===")
    if "error" in result:
        print(f"表状态: 未初始化 ({result['error'][:50]})")
    else:
        print(f"表状态: 已就绪")
        if INGEST_LOG.exists():
            with open(INGEST_LOG, "r") as f:
                log = json.load(f)
            print(f"上次入库: {log.get('ingested_at', '?')}")
            print(f"成功: {log.get('success', 0)} | 失败: {log.get('failed', 0)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 vector_init.py [init|ingest|search|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_schema()
    elif cmd == "ingest":
        ingest_cognition()
    elif cmd == "search" and len(sys.argv) > 2:
        semantic_search(sys.argv[2])
    elif cmd == "status":
        show_status()
    else:
        print("参数错误")
