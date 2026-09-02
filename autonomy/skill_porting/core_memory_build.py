#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心记忆体构建器 Core Memory Builder
第一层核心记忆闭环 - 阴期零消耗任务
功能：从坑库/认知池/认知沉淀/技能清单中提取元数据，构建统一索引+权重+关键词倒排
原则：不复制原始内容，只存元数据+路径+权重；四大类结构化；可快速检索
"""
import json
import re
import os
import time
import hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

BASE_DIR = Path(__file__).parent.parent.parent
PIT_LIBRARY = BASE_DIR / "data" / "pit_library"
COGNITION_POOL = BASE_DIR / "cognition_pool"
COGNITION_DIR = BASE_DIR / "cognition"
SKILL_PORTING = BASE_DIR / "autonomy" / "skill_porting"
CORE_MEMORY_FILE = BASE_DIR / "data" / "core_memory.json"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# 中文停用词（不建索引）
STOP_WORDS = set("的了是在我有和就不人都一上也很到说要去你会着没有看好自己这那与及或但如果因为所以虽然然后可以这个那个什么怎么为什么".split())

# 权重规则
WEIGHT_RULES = {
    "cognition": {
        "level": {"体系级": 1.0, "深层感悟": 0.8, "中层逻辑": 0.6, "表层信息": 0.4},
        "status": {"核心锚定": 1.0, "已验证": 0.8, "待验证": 0.5, "已归档": 0.3},
        "grade": {"S": 1.0, "A": 0.8, "B": 0.6, "C": 0.3},
    },
    "pits": {
        "level": {"L1": 1.0, "L2": 0.7, "L3": 0.5},
        "status": {"已修复": 0.6, "待修复": 0.9, "复现中": 1.0, "已规避": 0.5},
    }
}


def _extract_keywords(text, max_keywords=15):
    """从文本中提取关键词（简单分词+频率统计）"""
    if not text:
        return []
    # 提取中文词（2-4字）和英文词
    words = re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z_]{3,}', text)
    # 过滤停用词和单字
    words = [w for w in words if w not in STOP_WORDS and len(w) >= 2]
    counter = Counter(words)
    return [w for w, _ in counter.most_common(max_keywords)]


def _calc_weight(category, entry):
    """计算记忆权重"""
    rules = WEIGHT_RULES.get(category, {})
    weights = []
    for field, field_rules in rules.items():
        value = entry.get(field, "")
        if value in field_rules:
            weights.append(field_rules[value])
    if not weights:
        return 0.5
    return round(sum(weights) / len(weights), 3)


def _scan_pits():
    """扫描坑库"""
    entries = {}
    by_level = defaultdict(list)
    by_status = defaultdict(list)
    if not PIT_LIBRARY.exists():
        return entries, by_level, by_status
    for f in PIT_LIBRARY.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "pit_id" not in data:
                continue  # 跳过非坑库文件
            pit_id = data.get("pit_id", f.stem)
            level = data.get("level", "L2")
            status = data.get("status", "待修复")
            # 提取关键词
            text = " ".join([
                str(data.get("name", "")),
                str(data.get("title", "")),
                str(data.get("phenomenon", "")),
                str(data.get("root_cause", "")),
                str(data.get("lesson", "")),
            ])
            keywords = _extract_keywords(text)
            weight = _calc_weight("pits", {"level": level, "status": status})
            entries[pit_id] = {
                "id": pit_id,
                "name": data.get("name", "")[:80],
                "level": level,
                "status": status,
                "keywords": keywords,
                "weight": weight,
                "path": str(f.relative_to(BASE_DIR)),
                "updated_at": data.get("updated_at", data.get("created_at", "")),
            }
            by_level[level].append(pit_id)
            by_status[status].append(pit_id)
        except Exception:
            pass
    return entries, by_level, by_status


def _scan_cognition():
    """扫描认知池"""
    entries = {}
    by_level = defaultdict(list)
    by_status = defaultdict(list)
    if not COGNITION_POOL.exists():
        return entries, by_level, by_status
    for f in COGNITION_POOL.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            cog_id = data.get("id", f.stem)
            level = data.get("level", "中层逻辑")
            status = data.get("status", "待验证")
            density = data.get("density", {})
            grade = density.get("grade", "B") if isinstance(density, dict) else "B"
            # 提取关键词
            text = " ".join([
                str(data.get("core_statement", "")),
                " ".join(data.get("key_points", []) if isinstance(data.get("key_points"), list) else []),
                " ".join(data.get("related_concepts", []) if isinstance(data.get("related_concepts"), list) else []),
            ])
            keywords = _extract_keywords(text)
            weight = _calc_weight("cognition", {"level": level, "status": status, "grade": grade})
            entries[cog_id] = {
                "id": cog_id,
                "core_statement": str(data.get("core_statement", ""))[:120],
                "level": level,
                "status": status,
                "grade": grade,
                "keywords": keywords,
                "weight": weight,
                "path": str(f.relative_to(BASE_DIR)),
                "created_at": data.get("created_at", ""),
            }
            by_level[level].append(cog_id)
            by_status[status].append(cog_id)
        except Exception:
            pass
    return entries, by_level, by_status


def _scan_skills():
    """扫描已移植技能"""
    entries = {}
    if not SKILL_PORTING.exists():
        return entries
    for f in SKILL_PORTING.glob("*.py"):
        if f.name.startswith("__"):
            continue
        skill_name = f.stem
        entries[skill_name] = {
            "id": skill_name,
            "name": skill_name,
            "type": "阴期移植技能",
            "status": "active",
            "path": str(f.relative_to(BASE_DIR)),
            "weight": 0.7,
        }
    return entries


def _scan_cognition_docs():
    """扫描认知沉淀文档（作为设定类记忆）"""
    entries = {}
    if not COGNITION_DIR.exists():
        return entries
    for f in COGNITION_DIR.glob("认知沉淀_*.md"):
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            # 提取标题
            title_match = re.search(r'# 【认知沉淀】(.+)', content)
            title = title_match.group(1).strip() if title_match else f.stem
            # 提取核心认知点
            core_points = re.findall(r'\d+\.\s+\*\*(.+?)\*\*', content)
            text = title + " " + " ".join(core_points)
            keywords = _extract_keywords(text)
            doc_id = hashlib.md5(f.name.encode()).hexdigest()[:12]
            entries[doc_id] = {
                "id": doc_id,
                "title": title[:80],
                "core_points_count": len(core_points),
                "keywords": keywords,
                "weight": 0.6,
                "path": str(f.relative_to(BASE_DIR)),
            }
        except Exception:
            pass
    return entries


def _build_search_index(categories):
    """构建关键词倒排索引"""
    index = defaultdict(list)
    for cat_name, cat_data in categories.items():
        entries = cat_data.get("entries", {})
        for entry_id, entry in entries.items():
            for kw in entry.get("keywords", []):
                index[kw].append({
                    "category": cat_name,
                    "id": entry_id,
                    "weight": entry.get("weight", 0.5),
                })
    # 按权重排序
    for kw in index:
        index[kw].sort(key=lambda x: x["weight"], reverse=True)
    return dict(index)


def build_core_memory():
    """构建核心记忆体"""
    start = time.time()

    # 扫描四大类
    pit_entries, pit_by_level, pit_by_status = _scan_pits()
    cog_entries, cog_by_level, cog_by_status = _scan_cognition()
    skill_entries = _scan_skills()
    setting_entries = _scan_cognition_docs()

    categories = {
        "cognition": {
            "count": len(cog_entries),
            "entries": cog_entries,
            "by_level": dict(cog_by_level),
            "by_status": dict(cog_by_status),
        },
        "pits": {
            "count": len(pit_entries),
            "entries": pit_entries,
            "by_level": dict(pit_by_level),
            "by_status": dict(pit_by_status),
        },
        "skills": {
            "count": len(skill_entries),
            "entries": skill_entries,
        },
        "settings": {
            "count": len(setting_entries),
            "entries": setting_entries,
        },
    }

    # 构建搜索索引
    search_index = _build_search_index(categories)

    # 统计
    total = sum(cat["count"] for cat in categories.values())
    high_weight = sum(
        1 for cat in categories.values()
        for e in cat.get("entries", {}).values()
        if e.get("weight", 0) >= 0.8
    )

    core_memory = {
        "version": "1.0",
        "built_at": datetime.now().isoformat(),
        "categories": categories,
        "search_index": search_index,
        "stats": {
            "total_entries": total,
            "high_weight_entries": high_weight,
            "search_keywords": len(search_index),
            "build_duration_seconds": round(time.time() - start, 2),
        },
        "fusion_log": [],
    }

    # 保存核心记忆体
    with open(CORE_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(core_memory, f, ensure_ascii=False, indent=2)

    return core_memory


def _inject_to_state(core_memory):
    """回灌核心记忆体摘要到engine_state"""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        # 只存摘要，不存完整索引（避免state过大）
        state["core_memory"] = {
            "version": core_memory["version"],
            "built_at": core_memory["built_at"],
            "stats": core_memory["stats"],
            "category_counts": {k: v["count"] for k, v in core_memory["categories"].items()},
            "top_keywords": list(core_memory["search_index"].keys())[:50],
            "path": str(CORE_MEMORY_FILE.relative_to(BASE_DIR)),
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        return str(e)


def run(state=None, **kwargs):
    """阴期任务入口：核心记忆体构建"""
    core_memory = build_core_memory()
    inject_result = _inject_to_state(core_memory)

    stats = core_memory["stats"]
    evidence = f"核心记忆体构建完成：{stats['total_entries']}条记忆（认知{core_memory['categories']['cognition']['count']}/坑{core_memory['categories']['pits']['count']}/技能{core_memory['categories']['skills']['count']}/设定{core_memory['categories']['settings']['count']}），高权重{stats['high_weight_entries']}条，搜索关键词{stats['search_keywords']}个，回灌state={'成功' if inject_result is True else inject_result}"

    # 保存产出报告
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"core_memory_build_{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "evidence": evidence}, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "name": "yin_core_memory_build",
        "result": {"stats": stats, "inject_result": inject_result},
        "evidence": evidence,
        "output_path": str(report_path),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
