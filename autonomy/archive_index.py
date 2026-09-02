#!/usr/bin/env python3
"""
凡心归档索引系统（AIS）
对应星卷「千份文档归档危机」建议的工程化适配
核心：五维标签自动提取 + 全局索引原子更新 + 文档级去重
"""
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path

ARCHIVE_ROOT = Path(__file__).parent.parent / "archive"
INDEX_FILE = ARCHIVE_ROOT / "archive_index.json"

# 五维标签：主题域/产出类型/质量等级/状态/来源溯源
TOPIC_KEYWORDS = {
    "引擎架构": ["架构", "流水线", "模块", "schema", "并发", "调度"],
    "九维修炼": ["九转", "九维", "筑基", "炼精", "结丹", "养气", "反哺", "育神", "通神", "阳神", "还虚", "合道"],
    "容灾设计": ["容灾", "熔断", "B副", "降级", "回滚", "超时", "异常"],
    "认知系统": ["认知", "蒸馏", "记忆", "标签", "归档", "沉淀", "整合"],
    "算力优化": ["算力", "token", "额度", "并发", "效能", "方舟", "API"],
    "成品转化": ["L4", "成品", "SOP", "检查清单", "可执行", "落地"],
}

TYPE_MAP = {
    "deep": "推演稿", "eng": "工程设计稿", "cog": "认知总结",
    "exp": "跨界分析", "l4": "成品交付物",
}


def extract_tags(content: str, title: str, task_type: str, zhuan: int) -> dict:
    """自动提取五维标签"""
    doc_type = TYPE_MAP.get(task_type, "其他")
    word_count = len(content)
    # 质量等级
    if word_count > 3000 and "##" in content and ("风险" in content or "回滚" in content):
        quality = "S"
    elif word_count > 2000 and "##" in content:
        quality = "A"
    elif word_count > 1000:
        quality = "B"
    else:
        quality = "C"
    # 主题域
    topic = "通用"
    for t, keywords in TOPIC_KEYWORDS.items():
        if any(k in content or k in title for k in keywords):
            topic = t
            break
    return {
        "topic": topic,
        "type": doc_type,
        "quality": quality,
        "status": "待验证",
        "source": f"第{zhuan}转·{task_type}任务",
    }


def load_index() -> dict:
    default_idx = {"index_version": "1.0", "total_docs": 0, "docs": [], "tag_stats": {}}
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                idx = json.load(f)
            # P1修复：兼容性检查——旧格式文件没有docs字段，重新初始化
            if not isinstance(idx, dict) or "docs" not in idx:
                return default_idx
            return idx
        except Exception:
            return default_idx
    return default_idx


def save_index(index: dict):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_FILE)


def update_index(doc_entry: dict) -> bool:
    """原子更新全局索引，去重基于content_hash"""
    index = load_index()
    content_hash = doc_entry["content_hash"]
    if any(d.get("content_hash") == content_hash for d in index["docs"]):
        return False
    index["docs"].append(doc_entry)
    index["total_docs"] = len(index["docs"])
    index["last_updated"] = datetime.now().isoformat()
    # 更新标签统计
    stats = index.setdefault("tag_stats", {})
    q = doc_entry["tags"]["quality"]
    stats["quality"] = stats.get("quality", {})
    stats["quality"][q] = stats["quality"].get(q, 0) + 1
    t = doc_entry["tags"]["topic"]
    stats["topic"] = stats.get("topic", {})
    stats["topic"][t] = stats["topic"].get(t, 0) + 1
    save_index(index)
    return True


def archive_document(content: str, title: str, task_type: str, zhuan: int,
                     output_path: str, cognition_ids: list = None) -> dict:
    """归档文档：打标签+入索引+返回条目"""
    tags = extract_tags(content, title, task_type, zhuan)
    doc_entry = {
        "doc_id": f"doc_{int(datetime.now().timestamp() * 1000)}",
        "file_path": output_path,
        "file_size": len(content),
        "created_at": datetime.now().isoformat(),
        "tags": tags,
        "title": title[:100],
        "content_hash": hashlib.md5(content.encode()).hexdigest(),
        "related_cognition_ids": cognition_ids or [],
    }
    added = update_index(doc_entry)
    doc_entry["indexed"] = added
    return doc_entry


def search_index(topic: str = None, quality: str = None,
                 doc_type: str = None, keyword: str = None) -> list:
    """多标签组合检索"""
    index = load_index()
    results = index["docs"]
    if topic:
        results = [d for d in results if d["tags"]["topic"] == topic]
    if quality:
        results = [d for d in results if d["tags"]["quality"] == quality]
    if doc_type:
        results = [d for d in results if d["tags"]["type"] == doc_type]
    if keyword:
        results = [d for d in results if keyword in d["title"] or keyword in d["tags"]["topic"]]
    return results


def get_stats() -> dict:
    index = load_index()
    return {
        "total": index["total_docs"],
        "by_quality": index.get("tag_stats", {}).get("quality", {}),
        "by_topic": index.get("tag_stats", {}).get("topic", {}),
        "last_updated": index.get("last_updated", ""),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(get_stats(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        kwargs = {}
        for arg in sys.argv[2:]:
            k, v = arg.split("=", 1)
            kwargs[k] = v
        results = search_index(**kwargs)
        for r in results[:20]:
            print(f"[{r['tags']['quality']}] {r['title'][:60]} | {r['tags']['topic']} | {r['file_path']}")
        print(f"\n共{len(results)}条结果")
    else:
        print("用法: python archive_index.py stats | search topic=九维修炼 quality=S")
