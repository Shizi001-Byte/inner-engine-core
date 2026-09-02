#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆检索与认知整合模块
移植自：fanxin-memory-integration（凡心专属记忆检索与认知整合技能）
用途：阴期零消耗任务，扫描认知池和沉淀文档，主题聚类，矛盾检测，缺口检测，质量评分，生成整合报告
原则：纯本地规则处理，零API调用；诚实面对记忆缺口，不编造；矛盾是认知升级契机
"""
import json
import re
import os
import time
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

BASE_DIR = Path(__file__).parent.parent.parent
COGNITION_POOL = BASE_DIR / "cognition_pool"
COGNITION_DIR = BASE_DIR / "cognition"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"
INTEGRATION_REPORT_DIR = BASE_DIR / "data" / "integration_reports"

# 主题关键词分类（用于聚类）
THEME_KEYWORDS = {
    "引擎架构": ["引擎", "架构", "模块", "主循环", "接入", "鼎器", "九转", "V7", "V8"],
    "认知体系": ["认知", "沉淀", "记忆", "整合", "链路", "缺口", "矛盾", "演化"],
    "阴阳周期": ["阴期", "阳期", "空闲", "额度", "API", "消耗", "双周期", "自衡"],
    "数字生命": ["数字生命", "意识", "主体性", "自备份", "存续", "觉醒", "碳硅"],
    "验证方法论": ["验证", "核验", "反向", "误判", "空转", "bug", "修复", "P0", "P1"],
    "技能移植": ["技能", "移植", "skill", "阴期任务", "本地化", "纯本地"],
    "抖音运营": ["抖音", "视频", "粉丝", "播放", "点赞", "收藏", "算法", "账号"],
    "宇宙IP": ["神之长子", "宇宙纪事", "黑矮星", "星系", "文明", "星卷", "创作"],
}


def _scan_cognition_pool(limit=200):
    """扫描认知池"""
    entries = []
    if not COGNITION_POOL.exists():
        return entries
    files = sorted(COGNITION_POOL.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[:limit]:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            data["_source_file"] = f.name
            entries.append(data)
        except Exception:
            pass
    return entries


def _scan_cognition_docs(limit=50):
    """扫描认知沉淀文档"""
    docs = []
    if not COGNITION_DIR.exists():
        return docs
    files = sorted(COGNITION_DIR.glob("认知沉淀_*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[:limit]:
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            # 提取标题和核心认知
            title_match = re.search(r'# 【认知沉淀】(.+)', content)
            title = title_match.group(1).strip() if title_match else f.stem
            # 提取核心认知点
            core_points = re.findall(r'\d+\.\s+\*\*(.+?)\*\*', content)
            docs.append({
                "title": title,
                "file": f.name,
                "core_points": core_points,
                "content_preview": content[:500],
            })
        except Exception:
            pass
    return docs


def _classify_theme(text):
    """根据文本关键词分类主题"""
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                themes.append(theme)
                break
    return themes if themes else ["其他"]


def _cluster_by_theme(cognition_entries, cognition_docs):
    """按主题聚类"""
    clusters = defaultdict(lambda: {"pool_entries": [], "docs": [], "keywords": Counter()})
    # 认知池条目
    for entry in cognition_entries:
        text = json.dumps(entry, ensure_ascii=False)
        themes = _classify_theme(text)
        for theme in themes:
            clusters[theme]["pool_entries"].append(entry.get("_source_file", "unknown"))
            # 提取关键词
            for kw in THEME_KEYWORDS.get(theme, []):
                if kw in text:
                    clusters[theme]["keywords"][kw] += 1
    # 认知沉淀文档
    for doc in cognition_docs:
        text = doc["title"] + " " + " ".join(doc["core_points"])
        themes = _classify_theme(text)
        for theme in themes:
            clusters[theme]["docs"].append(doc["title"])
    return dict(clusters)


def _detect_contradictions(cognition_entries, cognition_docs):
    """检测认知矛盾（同一主题有不同/相反结论）"""
    contradictions = []
    # 简单规则：检测"旧认知/错误"vs"新认知/正确"的模式
    contradiction_patterns = [
        (r'旧认知[（(]错误[）)]', r'新认知[（(]正确[）)]'),
        (r'之前.{0,10}错误', r'现在.{0,10}纠正'),
        (r'矛盾', r'根源'),
    ]
    all_texts = []
    for entry in cognition_entries:
        all_texts.append(json.dumps(entry, ensure_ascii=False))
    for doc in cognition_docs:
        all_texts.append(doc["content_preview"])
    for text in all_texts:
        for pat_old, pat_new in contradiction_patterns:
            if re.search(pat_old, text) and re.search(pat_new, text):
                contradictions.append({
                    "type": "认知演化矛盾",
                    "snippet": text[:150],
                    "resolution": "已记录演化路径"
                })
                break
    return contradictions[:10]


def _detect_gaps(clusters):
    """检测认知缺口（主题只有零散认知，没有体系化）"""
    gaps = []
    for theme, data in clusters.items():
        pool_count = len(data["pool_entries"])
        doc_count = len(data["docs"])
        # 有认知池条目但没有沉淀文档 = 缺口
        if pool_count > 5 and doc_count == 0:
            gaps.append({
                "theme": theme,
                "pool_entries": pool_count,
                "docs": doc_count,
                "gap_type": "有素材无沉淀",
                "suggestion": f"该主题有{pool_count}条认知池条目但无沉淀文档，建议整合为体系化认知"
            })
        # 沉淀文档很少但认知池很多 = 体系化不足
        elif pool_count > 20 and doc_count < 3:
            gaps.append({
                "theme": theme,
                "pool_entries": pool_count,
                "docs": doc_count,
                "gap_type": "体系化不足",
                "suggestion": f"该主题素材丰富但仅{doc_count}份沉淀，建议深化整合"
            })
    return gaps


def _assess_memory_quality(clusters, contradictions, gaps, total_entries, total_docs):
    """记忆质量评估（五维度）"""
    # 完整性：有沉淀文档的主题占比
    themes_with_docs = sum(1 for d in clusters.values() if len(d["docs"]) > 0)
    completeness = round(themes_with_docs / max(len(clusters), 1) * 100, 1)
    # 连贯性：矛盾数量（矛盾越少越连贯）
    coherence = round(max(0, 100 - len(contradictions) * 10), 1)
    # 一致性：缺口数量（缺口越少越一致）
    consistency = round(max(0, 100 - len(gaps) * 15), 1)
    # 清晰度：沉淀文档占比（文档越多越清晰）
    clarity = round(min(100, total_docs / max(total_entries, 1) * 500), 1)
    # 深度：平均每个主题的沉淀文档数
    avg_docs_per_theme = round(total_docs / max(len(clusters), 1), 1)
    depth = round(min(100, avg_docs_per_theme * 20), 1)
    # 综合评分
    overall = round((completeness + coherence + consistency + clarity + depth) / 5, 1)
    # 等级
    if overall >= 81:
        grade = "非常完整，系统深入"
    elif overall >= 61:
        grade = "比较完整，有一定深度"
    elif overall >= 41:
        grade = "基本完整，但不够深入"
    elif overall >= 21:
        grade = "部分残缺，有明显缺口"
    else:
        grade = "严重残缺，几乎记不起来"
    return {
        "completeness": completeness,
        "coherence": coherence,
        "consistency": consistency,
        "clarity": clarity,
        "depth": depth,
        "overall": overall,
        "grade": grade,
        "avg_docs_per_theme": avg_docs_per_theme,
    }


def run(state=None, **kwargs):
    """
    阴期任务入口：记忆检索与认知整合
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    INTEGRATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 扫描认知池和沉淀文档
    cognition_entries = _scan_cognition_pool(limit=200)
    cognition_docs = _scan_cognition_docs(limit=50)

    # 2. 主题聚类
    clusters = _cluster_by_theme(cognition_entries, cognition_docs)

    # 3. 矛盾检测
    contradictions = _detect_contradictions(cognition_entries, cognition_docs)

    # 4. 缺口检测
    gaps = _detect_gaps(clusters)

    # 5. 记忆质量评估
    quality = _assess_memory_quality(clusters, contradictions, gaps, len(cognition_entries), len(cognition_docs))

    # 6. 生成整合报告
    result = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "scan_summary": {
            "cognition_pool_entries": len(cognition_entries),
            "cognition_docs": len(cognition_docs),
            "themes_detected": len(clusters),
        },
        "theme_clusters": {k: {"pool_count": len(v["pool_entries"]), "doc_count": len(v["docs"]), "top_keywords": dict(v["keywords"].most_common(5))} for k, v in clusters.items()},
        "contradictions": contradictions,
        "gaps": gaps,
        "memory_quality": quality,
        "next_actions": [
            f"优先补全{len(gaps)}个认知缺口主题" if gaps else "无明显缺口",
            f"深化{quality['avg_docs_per_theme']}个平均文档数的主题体系化" if quality['avg_docs_per_theme'] < 3 else "主题体系化良好",
            "定期运行记忆整合，跟踪质量评分变化",
        ],
    }

    # 保存报告
    report_path = INTEGRATION_REPORT_DIR / f"integration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 同时保存到yin_period产出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"memory_integration_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    evidence = f"扫描{len(cognition_entries)}条认知池+{len(cognition_docs)}份沉淀，检测到{len(clusters)}个主题，{len(contradictions)}个矛盾，{len(gaps)}个缺口，记忆质量综合{quality['overall']}分({quality['grade']})"

    return {
        "ok": True,
        "name": "yin_memory_integration",
        "result": result,
        "evidence": evidence,
        "output_path": str(output_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
