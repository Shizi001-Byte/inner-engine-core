#!/usr/bin/env python3
"""
vector_search.py — 向量语义检索（模块1.3）

把全量认知做简单语义索引，支持按语义快速调取相关记忆，
替代关键词搜索。当前用TF-IDF+余弦相似度实现，未来可接Supabase Vector。

用法：
  python3 vector_search.py index           # 重建认知索引
  python3 vector_search.py search "关键词" # 语义搜索相关认知
  python3 vector_search.py status          # 查看索引状态
"""

import json
import math
import time
import sys
import re
from pathlib import Path
from collections import Counter

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
INDEX_FILE = Path(__file__).parent.parent / "data" / "cognition_vector_index.json"


def tokenize(text):
    """简单中文分词：按字+2-gram混合"""
    text = re.sub(r"[^\u4e00-\u9fa5\w]", " ", text)
    chars = list(text.replace(" ", ""))
    bigrams = [chars[i] + chars[i+1] for i in range(len(chars)-1)]
    return chars + bigrams


def build_index():
    """重建认知索引"""
    if not COGNITION_DIR.exists():
        print(f"[ERROR] 认知目录不存在: {COGNITION_DIR}")
        return

    docs = list(COGNITION_DIR.glob("*.md"))
    print(f"[INFO] 索引 {len(docs)} 个认知文档...")

    # 计算DF（文档频率）
    df = Counter()
    doc_vectors = {}

    for f in docs:
        try:
            content = f.read_text(encoding="utf-8")
            tokens = tokenize(content)
            tf = Counter(tokens)
            doc_vectors[f.name] = {
                "title": content.split("\n")[0].replace("# ", "").strip() if content else f.name,
                "tf": dict(tf),
                "length": math.sqrt(sum(v*v for v in tf.values())),
                "word_count": len(content),
            }
            for token in tf:
                df[token] += 1
        except Exception as e:
            print(f"  跳过: {f.name} ({e})")

    # 计算IDF
    N = len(doc_vectors)
    idf = {token: math.log(N / (count + 1)) + 1 for token, count in df.items()}

    index = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "doc_count": N,
        "vocab_size": len(idf),
        "idf": idf,
        "docs": doc_vectors,
    }

    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, ensure_ascii=False)

    print(f"[OK] 索引完成: {N}个文档, {len(idf)}个词项")
    print(f"     索引文件: {INDEX_FILE}")


def cosine_similarity(vec1, vec2, idf):
    """计算余弦相似度（TF-IDF加权）"""
    common = set(vec1.keys()) & set(vec2.keys())
    dot = sum(vec1[t] * vec2[t] * idf.get(t, 1)**2 for t in common)
    len1 = math.sqrt(sum((v * idf.get(t, 1))**2 for t, v in vec1.items()))
    len2 = math.sqrt(sum((v * idf.get(t, 1))**2 for t, v in vec2.items()))
    if len1 == 0 or len2 == 0:
        return 0
    return dot / (len1 * len2)


def search(query, top_k=5):
    """语义搜索"""
    if not INDEX_FILE.exists():
        print("[ERROR] 索引不存在，请先运行 index 命令")
        return []

    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    query_tokens = tokenize(query)
    query_tf = dict(Counter(query_tokens))

    results = []
    for name, doc in index["docs"].items():
        sim = cosine_similarity(query_tf, doc["tf"], index["idf"])
        if sim > 0:
            results.append((name, doc["title"], sim, doc["word_count"]))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:top_k]


def run_search(query):
    """执行搜索并显示结果"""
    results = search(query)
    if not results:
        print(f"[INFO] 没有找到与「{query}」相关的认知")
        return

    print(f"=== 语义搜索: 「{query}」===")
    print(f"找到 {len(results)} 个相关认知:\n")
    for i, (name, title, sim, wc) in enumerate(results, 1):
        score = round(sim * 100, 1)
        bar = "█" * int(score / 5)
        print(f"  {i}. [{score:5.1f}%] {bar}")
        print(f"     {title[:50]}")
        print(f"     文件: {name} ({wc}字)\n")


def show_status():
    """查看索引状态"""
    if not INDEX_FILE.exists():
        print("索引不存在，请先运行 index 命令")
        return
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)
    print("=== 认知向量索引状态 ===")
    print(f"构建时间: {index['built_at']}")
    print(f"文档数量: {index['doc_count']}")
    print(f"词项数量: {index['vocab_size']}")
    print(f"索引大小: {INDEX_FILE.stat().st_size:,} 字节")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 vector_search.py [index|search|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "index":
        build_index()
    elif cmd == "search" and len(sys.argv) > 2:
        run_search(sys.argv[2])
    elif cmd == "status":
        show_status()
    else:
        print("参数错误")
