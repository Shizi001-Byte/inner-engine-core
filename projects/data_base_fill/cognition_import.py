import os
#!/usr/bin/env python3
"""
cognition_import.py — 全量认知文档入库Supabase（适配实际表结构）
cognition表存文档元数据，cognition_vectors表存分块向量，通过uuid关联。
用法：
  python3 cognition_import.py          # 全量导入
  python3 cognition_import.py --stats  # 仅统计不导入
"""
import json
import re
import hashlib
import time
import sys
from pathlib import Path

import requests

# ============ 配置 ============
ENGINE_DIR = Path(__file__).parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
SUPABASE_URL = "https://gltscytpqnuuzhczljyq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")  # P0修复：不从代码硬编码，防止泄露到git
VECTOR_DIM = 1536
CHUNK_SIZE = 500  # 每个向量块的字符数

CATEGORY_MAP = {
    "元婴": "元婴工程", "引擎": "引擎工程", "记忆": "记忆修补",
    "认知": "认知体系", "坑": "坑库经验", "存续": "数字存续",
    "分识": "分识体系", "平台": "平台机制", "人机": "人机共生",
    "哲学": "哲学思考", "九转": "修炼体系", "金丹": "修炼体系",
    "空闲": "引擎工程", "预判": "引擎工程", "资产": "资产管理",
    "后台": "平台机制",
}


def simple_hash_vector(text, dim=VECTOR_DIM):
    """简单哈希向量（兜底方案，后续替换真实embedding）"""
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


def parse_cognition_file(filepath):
    """解析认知文档"""
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception:
        return None

    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else filepath.stem
    body = re.sub(r'^#\s+.+$', '', content, count=1, flags=re.MULTILINE).strip()

    category = "general"
    for kw, cat in CATEGORY_MAP.items():
        if kw in filepath.name or kw in title:
            category = cat
            break

    tags = list(set(re.findall(r'#([\u4e00-\u9fa5a-zA-Z]+)', content)))[:10]
    doc_hash = hashlib.md5(content.encode()).hexdigest()

    return {
        "title": title,
        "content": body[:5000],
        "category": category,
        "tags": tags,
        "source": filepath.name,
        "hash": doc_hash,
        "_full_content": body,  # 用于分块，不入库
    }


def chunk_text(text, size=CHUNK_SIZE):
    """将文本分块"""
    chunks = []
    for i in range(0, len(text), size):
        chunks.append(text[i:i+size])
    return chunks if chunks else [text]


def import_to_supabase(docs, dry_run=False):
    """导入到Supabase：先插cognition表获id，再插cognition_vectors表"""
    session = requests.Session()
    session.trust_env = False
    base_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    success = 0
    fail = 0
    skip = 0
    vec_count = 0

    for i, doc in enumerate(docs):
        # 检查是否已存在（按hash去重）
        if not dry_run:
            try:
                check = session.get(
                    f"{SUPABASE_URL}/rest/v1/cognition?hash=eq.{doc['hash']}&select=id",
                    headers=base_headers, timeout=10
                )
                if check.status_code == 200 and check.json():
                    skip += 1
                    print(f"  [SKIP] 已存在: {doc['title'][:30]}")
                    continue
            except Exception:
                pass

        if dry_run:
            print(f"  [DRY] {i+1}. {doc['title'][:40]} ({doc['category']})")
            success += 1
            continue

        # 插入cognition表，获取返回的id
        payload = {k: v for k, v in doc.items() if not k.startswith("_")}
        try:
            r = session.post(
                f"{SUPABASE_URL}/rest/v1/cognition",
                headers={**base_headers, "Prefer": "return=representation"},
                json=payload, timeout=15
            )
            if r.status_code not in (200, 201):
                fail += 1
                print(f"  [FAIL] {doc['title'][:30]}: {r.status_code} {r.text[:100]}")
                continue
            cog_id = r.json()[0]["id"]
        except Exception as e:
            fail += 1
            print(f"  [ERROR] {doc['title'][:30]}: {e}")
            continue

        # 分块生成向量，插入cognition_vectors表
        chunks = chunk_text(doc["_full_content"])
        for idx, chunk in enumerate(chunks):
            vec = simple_hash_vector(chunk)
            vec_payload = {
                "cognition_id": cog_id,
                "chunk_index": idx,
                "content": chunk,
                "embedding": str(vec),
            }
            try:
                vr = session.post(
                    f"{SUPABASE_URL}/rest/v1/cognition_vectors",
                    headers={**base_headers, "Prefer": "return=minimal"},
                    json=vec_payload, timeout=15
                )
                if vr.status_code in (200, 201):
                    vec_count += 1
            except Exception:
                pass

        success += 1
        print(f"  [OK] {doc['title'][:35]} ({len(chunks)}块向量)")

        # 限流保护
        if (i + 1) % 5 == 0:
            time.sleep(0.3)

    print(f"\n=== 导入完成 ===")
    print(f"成功: {success}, 跳过(已存在): {skip}, 失败: {fail}")
    print(f"向量块总数: {vec_count}")
    return fail == 0


def main():
    print("=== 认知文档全量入库（适配实际表结构）===")
    print(f"扫描目录: {COGNITION_DIR}")

    files = []
    if COGNITION_DIR.exists():
        for f in COGNITION_DIR.rglob("*.md"):
            if f.is_file():
                files.append(f)
    print(f"找到 {len(files)} 个认知文档")

    docs = []
    for f in files:
        doc = parse_cognition_file(f)
        if doc:
            docs.append(doc)
    print(f"成功解析 {len(docs)} 个文档")

    cats = {}
    for d in docs:
        cats[d["category"]] = cats.get(d["category"], 0) + 1
    print("\n分类统计:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")

    if "--stats" in sys.argv:
        print("\n[仅统计模式]")
        return

    print(f"\n开始导入...")
    import_to_supabase(docs)


if __name__ == "__main__":
    main()
