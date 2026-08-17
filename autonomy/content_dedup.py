#!/usr/bin/env python3
"""
内容去重与增量评分模块
解决引擎低效空转：同质化套话、无认知增量
核心：相似度≥70%判定重复，增量分<30判定低效转
"""
import re
import math
from collections import Counter
from pathlib import Path

# 停用词（中文常见无意义词）
STOP_WORDS = set("的了是在我有和就不人都一上也很到说要去你会着没有看好自己这那他她它们什么怎么这样那样因为所以如果但是然后可以这个那个一个一些".split())


def tokenize(text: str) -> list:
    """简单中文分词（按字+2-gram）"""
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
    tokens = []
    # 单字
    for ch in text:
        if ch not in STOP_WORDS:
            tokens.append(ch)
    # 2-gram
    for i in range(len(text) - 1):
        bigram = text[i:i+2]
        tokens.append(bigram)
    return tokens


def cosine_similarity(text1: str, text2: str) -> float:
    """余弦相似度"""
    if not text1 or not text2:
        return 0.0
    vec1 = Counter(tokenize(text1))
    vec2 = Counter(tokenize(text2))
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(v * v for v in vec1.values())
    sum2 = sum(v * v for v in vec2.values())
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    return numerator / denominator if denominator else 0.0


def check_duplicate(new_content: str, recent_contents: list, threshold: float = 0.7) -> dict:
    """检查新内容是否与最近内容重复
    返回: {is_duplicate: bool, max_similarity: float, matched_index: int}
    """
    max_sim = 0.0
    matched_idx = -1
    for i, old in enumerate(recent_contents):
        sim = cosine_similarity(new_content, old)
        if sim > max_sim:
            max_sim = sim
            matched_idx = i
    return {
        "is_duplicate": max_sim >= threshold,
        "max_similarity": round(max_sim, 3),
        "matched_index": matched_idx,
    }


def calculate_increment_score(new_content: str, existing_cognitions: list,
                              memory_gaps: list = None, trace_links: list = None) -> dict:
    """计算认知增量评分（0-100）
    三维度：记忆补全度40% + 认知深化度35% + 链路打通度25%
    """
    score = 0.0
    details = {}

    # 1. 记忆补全度（40分）：是否涉及记忆缺口、断点、缺失日期
    memory_keywords = ["记忆", "断点", "缺失", "补全", "溯源", "原始对话", "历史", "归档", "索引", "资产"]
    memory_hit = sum(1 for kw in memory_keywords if kw in new_content)
    memory_score = min(40, memory_hit * 8)
    if memory_gaps:
        # 如果内容匹配已知记忆缺口，加分
        for gap in memory_gaps:
            if gap in new_content:
                memory_score = min(40, memory_score + 10)
    details["memory_completion"] = memory_score
    score += memory_score

    # 2. 认知深化度（35分）：与已有认知的差异度+结构完整度
    if existing_cognitions:
        avg_sim = sum(cosine_similarity(new_content, c) for c in existing_cognitions[:10]) / min(10, len(existing_cognitions))
        # 相似度越低，增量越大
        depth_score = (1 - avg_sim) * 35
    else:
        depth_score = 20  # 无历史认知，给基础分
    # 结构完整度：有标题、有分段、有结论
    structure_score = 0
    if "#" in new_content or "##" in new_content:
        structure_score += 5
    if "结论" in new_content or "总结" in new_content or "核心" in new_content:
        structure_score += 5
    if len(new_content) > 500:
        structure_score += 5
    depth_score = min(35, depth_score + structure_score)
    details["cognition_depth"] = round(depth_score, 1)
    score += depth_score

    # 3. 链路打通度（25分）：是否关联溯源链、资产、其他体系
    link_keywords = ["溯源", "关联", "链路", "资产", "Gitee", "Supabase", "飞书", "技能", "组合", "闭环"]
    link_hit = sum(1 for kw in link_keywords if kw in new_content)
    link_score = min(25, link_hit * 5)
    if trace_links:
        for link in trace_links:
            if link in new_content:
                link_score = min(25, link_score + 5)
    details["link_connection"] = link_score
    score += link_score

    # 套话惩罚：如果全是高频玄幻套话，扣分
    cliche_keywords = ["算力代谢", "赛博朋克", "东方玄幻", "数字宗门", "九转玄功", "维度跃迁", "本体论", "概率云"]
    cliche_hit = sum(1 for kw in cliche_keywords if kw in new_content)
    if cliche_hit >= 3:
        score = max(0, score - 15)
        details["cliche_penalty"] = -15

    return {
        "total": round(score, 1),
        "is_effective": score >= 30,
        "details": details,
    }


def load_recent_contents(cognition_dir: str, limit: int = 20) -> list:
    """加载最近的认知内容用于去重对比"""
    contents = []
    path = Path(cognition_dir)
    if not path.exists():
        return contents
    files = sorted(path.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    for f in files:
        try:
            contents.append(f.read_text(encoding="utf-8", errors="ignore")[:2000])
        except:
            pass
    return contents


if __name__ == "__main__":
    # 测试
    test1 = "基于核心认知锚点与道家哲学命题，生命是基于信息网络的算力代谢"
    test2 = "基于核心认知锚定，生命是信息网络的算力代谢，赛博朋克与东方玄幻交织"
    test3 = "今天修复了engine_zhuan1.py中dim变量未定义的bug，新增了内容去重模块"

    print(f"测试1 vs 测试2 相似度: {cosine_similarity(test1, test2):.3f}")
    print(f"测试1 vs 测试3 相似度: {cosine_similarity(test1, test3):.3f}")

    result = check_duplicate(test2, [test1])
    print(f"重复检测: {result}")

    score = calculate_increment_score(test3, [test1, test2])
    print(f"增量评分: {score}")
