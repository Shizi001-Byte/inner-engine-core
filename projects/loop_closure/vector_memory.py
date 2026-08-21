import os
#!/usr/bin/env python3
"""
vector_memory.py — 向量语义检索接入（模块1.3）
从Supabase cognition_vectors表拉取向量，本地计算余弦相似度，
实现认知文档的语义召回，替代关键词匹配。
用法：
  python3 vector_memory.py search "查询词" --top 5   # 语义搜索
  python3 vector_memory.py stats                       # 向量库统计
  python3 vector_memory.py rebuild                     # 重建本地向量索引
"""
import json
import math
import time
import argparse
from pathlib import Path

import requests

# ============ 配置 ============
ENGINE_DIR = Path(__file__).parent.parent.parent
SUPABASE_URL = "https://gltscytpqnuuzhczljyq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")  # P0修复：不从代码硬编码，防止泄露到git
LOCAL_INDEX_FILE = Path(__file__).parent / "data" / "vector_local_index.json"


def get_session():
    s = requests.Session()
    s.trust_env = False
    return s


def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def simple_hash_vector(text, dim=1536):
    """与cognition_import.py一致的哈希向量算法"""
    import hashlib
    import re
    vec = [0.0] * dim
    words = re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z]+', text)
    for w in words:
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def cosine_similarity(v1, v2):
    """余弦相似度"""
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def fetch_all_vectors():
    """从Supabase拉取所有向量"""
    s = get_session()
    all_vectors = []
    offset = 0
    limit = 1000
    while True:
        r = s.get(
            f"{SUPABASE_URL}/rest/v1/cognition_vectors",
            params={
                "select": "id,cognition_id,chunk_index,content,embedding",
                "limit": limit,
                "offset": offset,
            },
            headers=sb_headers(), timeout=30
        )
        if r.status_code != 200:
            print(f"[ERROR] 拉取向量失败: {r.text[:100]}")
            break
        batch = r.json()
        if not batch:
            break
        all_vectors.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return all_vectors


def fetch_cognition_titles():
    """拉取认知文档标题"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/cognition",
        params={"select": "id,title,category,source"},
        headers=sb_headers(), timeout=15
    )
    if r.status_code != 200:
        return {}
    return {c["id"]: c for c in r.json()}


def build_local_index():
    """构建本地向量索引（缓存到文件）"""
    print("[构建] 从Supabase拉取向量...")
    vectors = fetch_all_vectors()
    titles = fetch_cognition_titles()
    print(f"  拉取到 {len(vectors)} 个向量块，{len(titles)} 篇认知")

    # 解析向量字符串为float列表
    for v in vectors:
        if isinstance(v["embedding"], str):
            v["embedding"] = [float(x) for x in v["embedding"].strip("[]").split(",")]

    index = {
        "vectors": vectors,
        "titles": titles,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(vectors),
    }

    LOCAL_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_INDEX_FILE, "w") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"[OK] 本地索引已保存: {LOCAL_INDEX_FILE}")
    return index


def load_local_index():
    """加载本地索引，不存在则构建"""
    if LOCAL_INDEX_FILE.exists():
        with open(LOCAL_INDEX_FILE) as f:
            return json.load(f)
    return build_local_index()


def search(query, top_k=5, rebuild=False):
    """语义搜索"""
    index = load_local_index() if not rebuild else build_local_index()
    vectors = index["vectors"]
    titles = index["titles"]

    if not vectors:
        print("[WARN] 向量库为空")
        return []

    query_vec = simple_hash_vector(query)
    print(f"[搜索] 查询: {query}")
    print(f"  向量库: {len(vectors)} 个块")

    # 计算相似度
    scored = []
    for v in vectors:
        emb = v["embedding"]
        if isinstance(emb, str):
            emb = [float(x) for x in emb.strip("[]").split(",")]
        sim = cosine_similarity(query_vec, emb)
        scored.append((sim, v))

    # 排序取top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    results = scored[:top_k]

    print(f"\n【搜索结果 Top{top_k}】")
    for i, (sim, v) in enumerate(results, 1):
        cog = titles.get(v["cognition_id"], {})
        title = cog.get("title", "未知")
        category = cog.get("category", "?")
        content_preview = v.get("content", "")[:100].replace("\n", " ")
        print(f"\n{i}. [{sim:.3f}] {title}")
        print(f"   分类: {category} | 块: {v['chunk_index']}")
        print(f"   摘要: {content_preview}...")

    return results


def stats():
    """向量库统计"""
    index = load_local_index()
    vectors = index["vectors"]
    titles = index["titles"]
    print(f"【向量库统计】")
    print(f"  构建时间: {index.get('built_at', '?')}")
    print(f"  向量块数: {len(vectors)}")
    print(f"  认知文档数: {len(titles)}")

    # 分类统计
    cats = {}
    for c in titles.values():
        cat = c.get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1
    print(f"  分类分布:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt}")


def main():
    parser = argparse.ArgumentParser(description="向量语义检索")
    sub = parser.add_subparsers(dest="cmd")

    p_search = sub.add_parser("search", help="语义搜索")
    p_search.add_argument("query", help="查询词")
    p_search.add_argument("--top", type=int, default=5, help="返回数量")
    p_search.add_argument("--rebuild", action="store_true", help="重建索引")

    sub.add_parser("stats", help="统计信息")
    sub.add_parser("rebuild", help="重建本地索引")

    args = parser.parse_args()

    if args.cmd == "search":
        search(args.query, args.top, args.rebuild)
    elif args.cmd == "stats":
        stats()
    elif args.cmd == "rebuild":
        build_local_index()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
