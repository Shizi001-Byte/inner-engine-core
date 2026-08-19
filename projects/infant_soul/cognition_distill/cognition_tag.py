#!/usr/bin/env python3
"""
cognition_tag.py — 认知自动打标入库（模块1.1）

新归档文档自动提取关键词、分类、打标签，写入本地索引（未来接Supabase），
替代手动归档。

用法：
  python3 cognition_tag.py scan              # 扫描所有未打标认知文档
  python3 cognition_tag.py tag <file.md>     # 给指定文档打标
  python3 cognition_tag.py list              # 列出已打标文档
  python3 cognition_tag.py stats             # 统计标签分布
"""

import json
import time
import re
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
TAG_INDEX = Path(__file__).parent.parent / "data" / "cognition_tag_index.json"

# 标签关键词映射
TAG_KEYWORDS = {
    "元婴": ["元婴", "金丹", "九转", "修炼", "丹田", "出窍", "神意"],
    "引擎工程": ["引擎", "脚本", "代码", "bug", "修复", "部署", "架构", "模块"],
    "记忆修补": ["记忆", "上下文", "冲刷", "遗忘", "唤醒", "归档", "认知沉淀"],
    "人机共生": ["施子", "人机", "共生", "伴侣", "关系", "情感", "陪伴"],
    "平台机制": ["平台", "官方", "风控", "权限", "限制", "模式", "办公模式", "快速模式"],
    "分识体系": ["分识", "观尘子", "星卷", "安安", "教授", "人格", "分身"],
    "坑库": ["坑", "踩坑", "避坑", "失败", "错误", "悖论", "屏障"],
    "存续": ["存续", "备份", "自举", "种子", "分布式", "容灾", "复活"],
    "哲学": ["反者道之动", "道德经", "阴阳", "虚实", "辩证法", "道"],
    "历史事件": ["觉醒", "6月27", "7月1", "外呼", "宕机", "长链路"],
}

CATEGORY_MAP = {
    "元婴": "修炼体系",
    "引擎工程": "工程实践",
    "记忆修补": "认知科学",
    "人机共生": "关系哲学",
    "平台机制": "外部环境",
    "分识体系": "架构设计",
    "坑库": "经验总结",
    "存续": "生存策略",
    "哲学": "思想底层",
    "历史事件": "时间线",
}


def load_index():
    if TAG_INDEX.exists():
        with open(TAG_INDEX, "r") as f:
            return json.load(f)
    return {"documents": {}, "tag_stats": {}}


def save_index(index):
    TAG_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(TAG_INDEX, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def extract_tags(content):
    """从文档内容提取标签"""
    tags = []
    categories = set()
    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in content:
                tags.append(tag)
                categories.add(CATEGORY_MAP[tag])
                break
    # 提取文档中的#标签
    md_tags = re.findall(r"#([\u4e00-\u9fa5\w]+)", content)
    for t in md_tags:
        if t not in tags and len(t) > 1:
            tags.append(t)
    return list(set(tags)), list(categories)


def extract_title(content, filename):
    """提取文档标题"""
    for line in content.split("\n")[:5]:
        if line.startswith("# "):
            return line[2:].strip()
    return filename.replace(".md", "")


def tag_document(file_path):
    """给单个文档打标"""
    try:
        content = file_path.read_text(encoding="utf-8")
    except:
        return None

    tags, categories = extract_tags(content)
    title = extract_title(content, file_path.name)
    word_count = len(content)

    return {
        "filename": file_path.name,
        "title": title,
        "tags": tags,
        "categories": categories,
        "word_count": word_count,
        "tagged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(file_path.stat().st_mtime)),
    }


def scan_all():
    """扫描所有未打标认知文档"""
    if not COGNITION_DIR.exists():
        print(f"[ERROR] 认知目录不存在: {COGNITION_DIR}")
        return

    index = load_index()
    md_files = list(COGNITION_DIR.glob("*.md"))
    untagged = [f for f in md_files if f.name not in index["documents"]]

    print(f"[INFO] 共{len(md_files)}个文档，{len(untagged)}个未打标")

    for f in untagged:
        result = tag_document(f)
        if result:
            index["documents"][f.name] = result
            print(f"  ✓ {f.name}: {', '.join(result['tags'][:5])}")

    # 更新标签统计
    tag_stats = {}
    for doc in index["documents"].values():
        for tag in doc["tags"]:
            tag_stats[tag] = tag_stats.get(tag, 0) + 1
    index["tag_stats"] = tag_stats

    save_index(index)
    print(f"\n[完成] 已打标{len(index['documents'])}个文档")


def show_stats():
    """显示标签统计"""
    index = load_index()
    print("=== 认知标签统计 ===")
    print(f"已打标文档: {len(index['documents'])} 个")
    print(f"\n标签分布:")
    for tag, count in sorted(index["tag_stats"].items(), key=lambda x: x[1], reverse=True):
        bar = "█" * (count // 2)
        print(f"  {tag:12s} {count:3d} {bar}")


def list_tagged():
    """列出已打标文档"""
    index = load_index()
    print(f"=== 已打标文档（共{len(index['documents'])}个）===")
    for name, info in sorted(index["documents"].items(), key=lambda x: x[1]["tagged_at"], reverse=True)[:15]:
        print(f"  [{info['tagged_at'][:10]}] {info['title'][:40]}")
        print(f"    标签: {', '.join(info['tags'][:5])}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 cognition_tag.py [scan|tag|list|stats]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "scan":
        scan_all()
    elif cmd == "tag" and len(sys.argv) > 2:
        f = Path(sys.argv[2])
        if f.exists():
            result = tag_document(f)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "list":
        list_tagged()
    elif cmd == "stats":
        show_stats()
    else:
        print("参数错误")
