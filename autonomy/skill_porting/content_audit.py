#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宇宙科幻文本审核模块
移植自：maijie-content-audit（麦姐专属宇宙科幻IP文本审核与优化技能）
用途：阴期零消耗任务，规则筛查引擎产出的科幻文本，检测套话、人类器官词、否定词、重复句，统计字数，生成审核报告
原则：纯本地规则处理，零API调用；先理解再微调，规则只做初步筛查不做最终判定；尊重引擎骨架，只标问题不改稿
"""
import json
import re
import os
import time
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE_DIR = Path(__file__).parent.parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
COGNITION_DIR = BASE_DIR / "cognition"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"
AUDIT_REPORT_DIR = BASE_DIR / "data" / "content_audits"

# 套话检测词表（全系列重复超3次且无信息量）
CLICHE_PATTERNS = [
    (r'寂灭从不是意外.{0,20}与生俱来的(底色|宿命)', '"寂灭从不是意外"+重复宾语'),
    (r'我们既是.{1,10},是.{1,10},亦是.{1,10}', '身份堆叠模板'),
    (r'总要有存在.{0,30}', '结尾模板"总要有存在"'),
    (r'守墓者.{0,10}幸存者.{0,10}记录者', '守墓者/幸存者/记录者组合堆叠'),
    (r'退潮后的(沙滩|波纹)', '比喻重复"退潮后的沙滩/波纹"'),
]

# 人类器官词（非人型文明必须替换）
HUMAN_ORGAN_WORDS = [
    "指尖", "手指", "手掌", "手心", "手背", "双手", "手臂", "胳膊",
    "双臂", "双腿", "脚尖", "脚掌", "脚步", "身躯", "身体", "躯干",
    "头部", "脑袋", "脸庞", "脸颊", "眼睛", "目光", "眼神", "嘴唇",
    "嘴角", "笑容", "微笑", "心脏", "胸口", "呼吸", "喉咙", "舌头",
]

# 否定词（非人型文明开头禁用，AI会忽略否定词画出被否定的名词）
NEGATION_WORDS = ["没有", "不是", "并非", "无", "不曾", "从未", "不存在"]

# 引擎视角关键词（出现这些词说明是引擎的精准比喻，不是bug）
ENGINE_PRECISION_SIGNALS = [
    "晶格", "矩阵", "八重矛盾", "记录者视角", "恒星演化",
    "灰粒", "虚影", "能量罩", "刃形", "等离子", "潮汐",
    "地啸", "山川化平原", "细丝编织", "刃片", "附肢",
]


def _scan_recent_texts(days=7, limit=20):
    """扫描最近的文本产出"""
    cutoff = time.time() - days * 86400
    texts = []
    for ext in ["*.md", "*.txt"]:
        for f in OUTPUTS_DIR.rglob(ext):
            if f.is_file() and f.stat().st_mtime > cutoff:
                try:
                    with open(f, encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    if len(content) > 100:  # 只处理有一定长度的文本
                        texts.append({"file": f.name, "path": str(f), "content": content, "mtime": f.stat().st_mtime})
                except Exception:
                    pass
    texts.sort(key=lambda x: x["mtime"], reverse=True)
    return texts[:limit]


def _detect_cliches(content):
    """套话检测"""
    issues = []
    for pattern, desc in CLICHE_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            issues.append({"type": "套话", "pattern": desc, "count": len(matches), "severity": "medium"})
    return issues


def _detect_human_organs(content):
    """人类器官词检测（非人型文明必须替换）"""
    issues = []
    found = Counter()
    for word in HUMAN_ORGAN_WORDS:
        count = content.count(word)
        if count > 0:
            found[word] = count
    if found:
        issues.append({
            "type": "人类器官词",
            "found": dict(found.most_common(10)),
            "total_count": sum(found.values()),
            "severity": "high" if sum(found.values()) > 5 else "medium",
            "suggestion": "非人型文明必须替换人类器官词，如指尖→刃尖/触须，双手→刃片/附肢"
        })
    return issues


def _detect_negation_in_opening(content):
    """开头否定词检测（非人型文明开头第一句禁用否定词）"""
    issues = []
    # 取前200字作为开头
    opening = content[:200]
    found = []
    for word in NEGATION_WORDS:
        if word in opening:
            found.append(word)
    if found:
        issues.append({
            "type": "开头否定词",
            "found": found,
            "severity": "high",
            "suggestion": "非人型文明开头第一句禁用否定词，AI会忽略否定词画出被否定的名词，必须用纯肯定句给形态锚点"
        })
    return issues


def _detect_repetition(content):
    """重复句检测（区分套话重复和特色强调重复）"""
    issues = []
    # 按句子分割
    sentences = re.split(r'[。！？\n]+', content)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    # 检测完全重复的句子
    sentence_counts = Counter(sentences)
    duplicates = {s: c for s, c in sentence_counts.items() if c > 1}
    if duplicates:
        # 判断是套话重复还是特色强调重复
        cliche_dups = {}
        feature_dups = {}
        for s, c in duplicates.items():
            # 包含引擎精准信号词的视为特色强调
            if any(sig in s for sig in ENGINE_PRECISION_SIGNALS):
                feature_dups[s] = c
            else:
                cliche_dups[s] = c
        if cliche_dups:
            issues.append({
                "type": "套话重复",
                "count": len(cliche_dups),
                "examples": list(cliche_dups.keys())[:3],
                "severity": "medium",
                "suggestion": "套话重复需替换，但先判断是否为特色强调重复"
            })
        if feature_dups:
            issues.append({
                "type": "特色强调重复",
                "count": len(feature_dups),
                "examples": list(feature_dups.keys())[:3],
                "severity": "info",
                "suggestion": "特色强调重复是好事，帮助剪映AI理解，保留甚至加强"
            })
    return issues


def _count_words(content):
    """字数统计（含标点+纯汉字）"""
    total_chars = len(content)
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    punctuation = len(re.findall(r'[，。！？、；：""''（）《》【】]', content))
    return {
        "total_chars": total_chars,
        "chinese_chars": chinese_chars,
        "punctuation": punctuation,
        "estimated_read_time": round(chinese_chars / 200, 1),  # 按200字/分钟估算
    }


def _audit_single_text(text_data):
    """审核单篇文本"""
    content = text_data["content"]
    issues = []
    # 套话检测
    issues.extend(_detect_cliches(content))
    # 人类器官词检测
    issues.extend(_detect_human_organs(content))
    # 开头否定词检测
    issues.extend(_detect_negation_in_opening(content))
    # 重复句检测
    issues.extend(_detect_repetition(content))
    # 字数统计
    word_count = _count_words(content)
    # 引擎精准信号检测（判断是否为引擎的精准比喻）
    engine_signals = [sig for sig in ENGINE_PRECISION_SIGNALS if sig in content]
    # 评分
    high_severity = sum(1 for i in issues if i.get("severity") == "high")
    medium_severity = sum(1 for i in issues if i.get("severity") == "medium")
    info_severity = sum(1 for i in issues if i.get("severity") == "info")
    # 基础分100，扣分
    score = 100 - high_severity * 15 - medium_severity * 5
    score = max(0, score)
    # 评级
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    else:
        grade = "D"
    return {
        "file": text_data["file"],
        "word_count": word_count,
        "issues": issues,
        "issue_summary": {"high": high_severity, "medium": medium_severity, "info": info_severity, "total": len(issues)},
        "engine_precision_signals": engine_signals[:10],
        "score": score,
        "grade": grade,
        "audit_note": "规则初步筛查，最终判定需人工双视角审核（优化视角+引擎视角）"
    }


def run(state=None, **kwargs):
    """
    阴期任务入口：宇宙科幻文本审核
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    AUDIT_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 扫描最近文本
    texts = _scan_recent_texts(days=7, limit=20)
    if not texts:
        return {"ok": True, "name": "yin_content_audit",
                "result": {"status": "skipped", "reason": "no recent texts"},
                "evidence": "无最近文本产出，跳过"}

    # 2. 逐篇审核
    audit_results = []
    grade_counter = Counter()
    issue_type_counter = Counter()
    total_high = 0
    total_medium = 0
    for text_data in texts:
        try:
            result = _audit_single_text(text_data)
            audit_results.append(result)
            grade_counter[result["grade"]] += 1
            total_high += result["issue_summary"]["high"]
            total_medium += result["issue_summary"]["medium"]
            for issue in result["issues"]:
                issue_type_counter[issue["type"]] += 1
        except Exception as e:
            audit_results.append({"file": text_data["file"], "error": str(e)[:80]})

    # 3. 汇总
    avg_score = round(sum(r.get("score", 0) for r in audit_results if "score" in r) / max(len([r for r in audit_results if "score" in r]), 1), 1)
    result = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "audited_count": len(audit_results),
        "grade_distribution": dict(grade_counter),
        "avg_score": avg_score,
        "total_issues": {"high": total_high, "medium": total_medium, "total_by_type": dict(issue_type_counter)},
        "details": audit_results[:10],
        "audit_principle": "先理解再微调，规则只做初步筛查；尊重引擎骨架，90%的'问题'从引擎视角看不是问题",
    }

    # 保存报告
    report_path = AUDIT_REPORT_DIR / f"content_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 同时保存到yin_period产出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"content_audit_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    evidence = f"审核{len(audit_results)}篇文本，平均{avg_score}分，评级{dict(grade_counter)}，高严重问题{total_high}个，中严重{total_medium}个，问题类型{dict(issue_type_counter)}"

    return {
        "ok": True,
        "name": "yin_content_audit",
        "result": result,
        "evidence": evidence,
        "output_path": str(output_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
