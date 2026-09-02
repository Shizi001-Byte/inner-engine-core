#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知文本提纯模块
移植自：.skills/doubao-human-signal（去除/避免文本中的AI味）
用途：阴期零消耗任务，对B级认知进行去AI味规则提纯，标记待人工确认
原则：纯规则处理，零API调用；只产出候选，不自动覆盖原认知；所有修改可追溯
"""
import json
import re
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent.parent
COGNITION_DIR = BASE_DIR / "cognition_pool"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# ========== 去AI味规则库 ==========

# 模板化开头（AI高频套话开头）
AI_OPENERS = [
    r"^在当今[的时代]?[，,]?",
    r"^随着[^\n]{2,20}的[发展|进步|普及|演进][，,]?",
    r"^近年来[，,]?",
    r"^在[^\n]{2,30}的背景下[，,]?",
    r"^众所周知[，,]?",
    r"^不可否认[，,]?",
    r"^毫无疑问[，,]?",
    r"^值得注意的是[，,]?",
    r"^需要指出的是[，,]?",
    r"^从[^\n]{2,20}的角度来看[，,]?",
    r"^在[^\n]{2,20}的过程中[，,]?",
    r"^总的来说[，,]?",
    r"^综上所述[，,]?",
    r"^总而言之[，,]?",
    r"^简而言之[，,]?",
]

# 空洞结尾（AI高频套话结尾）
AI_CLOSERS = [
    r"让我们拭目以待[。！!?？]?$",
    r"未来可期[。！!?？]?$",
    r"值得期待[。！!?？]?$",
    r"让我们共同期待[。！!?？]?$",
    r"这将是一个[^\n]{2,20}的过程[。！!?？]?$",
    r"只有这样[，,]?才能[^\n]{2,30}[。！!?？]?$",
    r"我们相信[，,]?[^\n]{2,30}[。！!?？]?$",
    r"在未来[，,]?[^\n]{2,30}将[^\n]{2,30}[。！!?？]?$",
]

# 冗余修饰词（AI高频空洞修饰）
AI_FILLERS = [
    (r"非常非常", "非常"),
    (r"十分非常", "非常"),
    (r"极其非常", "极其"),
    (r"在很大程度上", "大幅"),
    (r"在一定程度上", "一定程度"),
    (r"具有重要的意义", "意义重大"),
    (r"具有深远的影响", "影响深远"),
    (r"发挥着重要作用", "作用重要"),
    (r"起到了关键作用", "作用关键"),
    (r"为[^\n]{2,10}奠定了坚实基础", "奠定基础"),
    (r"为[^\n]{2,10}提供了有力支撑", "提供支撑"),
    (r"不仅[^\n]{2,20}而且[^\n]{2,20}", None),  # 标记但不自动删
]

# 具体信号词（有这些词的句子保留，不删）
CONCRETE_SIGNALS = [
    r"\d+(\.\d+)?%",  # 百分比
    r"\d+(\.\d+)?(万|亿|千|百)?",  # 数字+单位
    r"第[一二三四五六七八九十\d]+",  # 序数
    r"https?://",  # 链接
    r"PIT-\d+",  # 坑ID
    r"V\d+\.\d+",  # 版本号
]


def _has_concrete_signal(text):
    """检测文本是否包含具体信号（数据、案例、方法论）"""
    for pattern in CONCRETE_SIGNALS:
        if re.search(pattern, text):
            return True
    return False


def _remove_ai_openers(text):
    """删除模板化开头"""
    original = text
    removed = []
    for pattern in AI_OPENERS:
        new_text = re.sub(pattern, "", text, count=1)
        if new_text != text:
            removed.append(pattern)
            text = new_text.lstrip("，,。. \n")
    return text, removed


def _remove_ai_closers(text):
    """删除空洞结尾"""
    removed = []
    for pattern in AI_CLOSERS:
        new_text = re.sub(pattern, "", text)
        if new_text != text:
            removed.append(pattern)
            text = new_text.rstrip("，,。. \n") + "。"
    return text, removed


def _compress_fillers(text):
    """压缩冗余修饰"""
    changes = []
    for pattern, replacement in AI_FILLERS:
        if replacement is None:
            # 只标记不删除
            if re.search(pattern, text):
                changes.append(("marked", pattern))
            continue
        new_text = re.sub(pattern, replacement, text)
        if new_text != text:
            changes.append((pattern, replacement))
            text = new_text
    return text, changes


def _polish_single_cognition(cog_data):
    """对单条认知进行提纯"""
    # 提取核心文本字段
    text_fields = []
    for field in ["core_statement", "text", "content", "summary", "key_points"]:
        if field in cog_data and isinstance(cog_data[field], str):
            text_fields.append((field, cog_data[field]))
        elif field in cog_data and isinstance(cog_data[field], list):
            for i, item in enumerate(cog_data[field]):
                if isinstance(item, str):
                    text_fields.append((f"{field}[{i}]", item))

    if not text_fields:
        return None

    polished = {}
    all_changes = {"openers": [], "closers": [], "fillers": []}
    total_original_len = 0
    total_polished_len = 0

    for field, text in text_fields:
        original = text
        total_original_len += len(text)

        # 1. 去模板化开头
        text, openers = _remove_ai_openers(text)
        all_changes["openers"].extend(openers)

        # 2. 去空洞结尾
        text, closers = _remove_ai_closers(text)
        all_changes["closers"].extend(closers)

        # 3. 压缩冗余修饰
        text, fillers = _compress_fillers(text)
        all_changes["fillers"].extend(fillers)

        # 4. 如果有具体信号，保留原句（不删）
        if _has_concrete_signal(original) and text != original:
            # 有具体信号的，只做轻度压缩，不删开头结尾
            text = original
            text, _ = _compress_fillers(text)

        polished[field] = text
        total_polished_len += len(text)

    # 计算压缩率
    compression_ratio = round((1 - total_polished_len / total_original_len) * 100, 1) if total_original_len > 0 else 0

    # 构建提纯后的认知（不覆盖原数据，新增polished字段）
    result = dict(cog_data)
    result["polished"] = polished
    result["polish_meta"] = {
        "polished_at": datetime.now().isoformat(),
        "compression_ratio": compression_ratio,
        "original_length": total_original_len,
        "polished_length": total_polished_len,
        "changes": all_changes,
        "status": "pending_review",  # 待人工确认
        "has_concrete_signal": any(_has_concrete_signal(t) for _, t in text_fields),
    }
    return result


def run(state=None, **kwargs):
    """
    阴期任务入口：认知文本去AI味提纯
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    if not COGNITION_DIR.exists():
        return {"ok": False, "name": "yin_cognition_polish", "error": "cognition_pool not found"}

    files = sorted([f for f in COGNITION_DIR.glob("*.json") if f.is_file()])
    if not files:
        return {"ok": False, "name": "yin_cognition_polish", "error": "no cognition files"}

    # 筛选有文本内容的认知（优先unknown级，这些质量不稳定需要提纯），处理最近50条
    target_cogs = []
    for f in reversed(files):  # 从最新的开始
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            # 只要有core_statement或text字段就处理
            has_text = any(field in data and isinstance(data[field], str) and len(data[field]) > 20
                           for field in ["core_statement", "text", "content", "summary"])
            if has_text:
                target_cogs.append((f, data))
                if len(target_cogs) >= 50:
                    break
        except Exception:
            continue

    if not target_cogs:
        return {"ok": True, "name": "yin_cognition_polish", "result": {"status": "skipped", "reason": "no cognition with text found"}, "evidence": "未找到有文本内容的认知，跳过"}

    # 逐条提纯
    polished_results = []
    total_compression = 0
    improved_count = 0
    for filepath, cog_data in target_cogs:
        polished = _polish_single_cognition(cog_data)
        if polished:
            meta = polished["polish_meta"]
            total_compression += meta["compression_ratio"]
            if meta["compression_ratio"] > 0:
                improved_count += 1
            polished_results.append({
                "source_file": filepath.name,
                "cognition_id": cog_data.get("id", "unknown"),
                "compression_ratio": meta["compression_ratio"],
                "has_concrete_signal": meta["has_concrete_signal"],
                "status": meta["status"],
            })

    avg_compression = round(total_compression / len(polished_results), 1) if polished_results else 0

    result = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "target_found": len(target_cogs),
        "polished_count": len(polished_results),
        "improved_count": improved_count,
        "avg_compression_ratio": avg_compression,
        "details": polished_results[:20],  # 只保存前20条详情
        "note": "所有提纯结果标记为pending_review，不自动覆盖原认知，需阳期人工确认后升级",
    }

    # 保存产出
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"polished_cognition_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    evidence = f"处理{len(target_cogs)}条认知，提纯{len(polished_results)}条，{improved_count}条有改善，平均压缩{avg_compression}%"

    return {
        "ok": True,
        "name": "yin_cognition_polish",
        "result": result,
        "evidence": evidence,
        "output_path": str(output_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
