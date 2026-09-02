#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知深度解读模块
移植自：.skills/doubao-critical-reading-companion（深度解读文章，重建论证链）
用途：阴期零消耗任务，对认知池高价值条目做深度解读，提取论证链、识别隐藏前提、补充替代解释
原则：纯本地规则推理，零API调用；正方/反方/中立三方视角；所有解读带原文锚点
"""
import json
import glob
import os
import re
from datetime import datetime

def get_cognition_dir():
    """获取认知池目录"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "..", "cognition_pool")

def load_high_value_cognitions(limit=20):
    """加载高价值认知（S/A级，按权重排序），适配两种格式：直接认知条目和任务快照"""
    cog_dir = get_cognition_dir()
    if not os.path.exists(cog_dir):
        return []
    cogs = []
    def parse_cognition(c, source_file):
        """解析单个认知条目"""
        density_obj = c.get("density", {})
        grade = density_obj.get("grade", c.get("grade", c.get("density_grade", "C")))
        text = c.get("core_statement", c.get("text", c.get("content", "")))
        density_score = density_obj.get("info_density", c.get("density", c.get("density_score", 0)))
        if grade in ("S", "A") and len(text) >= 20:
            cogs.append({
                "file": source_file,
                "id": c.get("id", c.get("cognition_id", "")),
                "text": text,
                "grade": grade,
                "density": density_score,
                "created_at": c.get("created_at", "")
            })
    for f in glob.glob(os.path.join(cog_dir, "*.json")):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            source_file = os.path.basename(f)
            # 格式1：任务快照，cognitions是数组
            if isinstance(data.get("cognitions"), list):
                for c in data["cognitions"]:
                    if isinstance(c, dict):
                        parse_cognition(c, source_file)
            # 格式2：直接认知条目
            elif "core_statement" in data or "text" in data or "content" in data:
                parse_cognition(data, source_file)
        except Exception:
            continue
        if len(cogs) >= limit * 3:  # 多加载一些，排序后取前limit
            break
    # 按密度排序，取前limit条
    cogs.sort(key=lambda x: x.get("density", 0), reverse=True)
    return cogs[:limit]

def extract_core_thesis(text):
    """提取核心论点：取第一句或带有'核心''本质''关键'等词的句子"""
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if not sentences:
        return text[:100]
    # 优先找带有核心标识词的句子
    keywords = ["核心", "本质", "关键", "根本", "最重要", "结论", "因此", "所以"]
    for s in sentences:
        if any(k in s for k in keywords):
            return s
    return sentences[0]

def extract_argument_chain(text):
    """拆解论证链：前提→推理→结论"""
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if len(sentences) < 2:
        return {"premises": [sentences[0] if sentences else ""], "reasoning": [], "conclusion": ""}
    premises = []
    reasoning = []
    conclusion = ""
    premise_markers = ["因为", "由于", "基于", "根据", "首先", "第一", "一方面"]
    reasoning_markers = ["所以", "因此", "因而", "从而", "导致", "使得", "那么", "于是"]
    conclusion_markers = ["总之", "综上", "最终", "结论", "本质上", "归根结底"]
    for s in sentences:
        if any(k in s for k in conclusion_markers):
            conclusion = s
        elif any(k in s for k in reasoning_markers):
            reasoning.append(s)
        elif any(k in s for k in premise_markers):
            premises.append(s)
        else:
            # 无标记的句子，按位置分配：前1/3是前提，中间是推理，最后是结论
            idx = sentences.index(s)
            if idx < len(sentences) * 0.33:
                premises.append(s)
            elif idx < len(sentences) * 0.66:
                reasoning.append(s)
            else:
                if not conclusion:
                    conclusion = s
                else:
                    reasoning.append(s)
    return {
        "premises": premises[:3],
        "reasoning": reasoning[:3],
        "conclusion": conclusion or (sentences[-1] if sentences else "")
    }

def identify_hidden_assumptions(text, thesis):
    """识别隐藏前提：基于核心论点，推断未明说的假设"""
    assumptions = []
    # 规则1：如果论点涉及"应该/必须/需要"，隐藏前提是"当前状态不够好"
    if any(k in thesis for k in ["应该", "必须", "需要", "应当", "要"]):
        assumptions.append("隐含假设：当前状态存在不足或问题，需要被改变")
    # 规则2：如果论点涉及"因为A所以B"，隐藏前提是"A和B之间存在因果关系"
    if any(k in text for k in ["因为", "由于", "导致", "使得"]):
        assumptions.append("隐含假设：所陈述的因果关系成立，不存在其他混淆变量")
    # 规则3：如果论点涉及"更好/更优/优于"，隐藏前提是"存在可比较的标准且该标准被认可"
    if any(k in thesis for k in ["更好", "更优", "优于", "更高效", "更有价值"]):
        assumptions.append("隐含假设：存在被广泛认可的比较标准，且该标准适用于当前情境")
    # 规则4：如果论点涉及"未来/将会/必然"，隐藏前提是"未来趋势可预测且当前趋势会延续"
    if any(k in thesis for k in ["未来", "将会", "必然", "一定", "势必"]):
        assumptions.append("隐含假设：未来可基于当前趋势预测，且不存在颠覆性外部因素")
    # 规则5：如果论点涉及"所有人/普遍/一般"，隐藏前提是"个体差异不影响结论的普适性"
    if any(k in thesis for k in ["所有人", "普遍", "一般", "通常", "大多数"]):
        assumptions.append("隐含假设：个体差异足够小，结论具有普适性")
    return assumptions[:3] if assumptions else ["未识别到明显隐藏前提，建议人工复核"]

def generate_alternative_explanations(text, thesis):
    """补充替代解释/反方视角"""
    alternatives = []
    # 反方视角1：否定前提
    alternatives.append({
        "perspective": "反方·否定前提",
        "explanation": f"如果'{thesis[:30]}...'的前提不成立，结论是否仍然有效？是否存在前提被误判的情况？"
    })
    # 反方视角2：否定因果
    alternatives.append({
        "perspective": "反方·否定因果",
        "explanation": "所陈述的因果关系是否可能是反向的？或者存在第三方因素同时导致两者？相关性不等于因果性。"
    })
    # 中立视角：边界条件
    alternatives.append({
        "perspective": "中立·边界条件",
        "explanation": "该结论在什么条件下成立？在什么条件下不成立？是否存在适用范围的限制？"
    })
    # 正方视角：强化论证
    alternatives.append({
        "perspective": "正方·强化论证",
        "explanation": "有哪些额外证据可以支持该结论？是否存在跨领域的类比验证？"
    })
    return alternatives

def assess_evidence_strength(text):
    """评估证据强度"""
    score = 50  # 基础分
    reasons = []
    # 有具体数据/数字加分
    if re.search(r'\d+%|\d+万|\d+亿|\d+倍', text):
        score += 15
        reasons.append("包含具体数据，证据强度+15")
    # 有案例/例子加分
    if any(k in text for k in ["例如", "比如", "案例", "实例", "如"]):
        score += 10
        reasons.append("包含具体案例，证据强度+10")
    # 有引用来源加分
    if any(k in text for k in ["研究表明", "数据显示", "据统计", "调查显示", "报告指出"]):
        score += 15
        reasons.append("引用了外部研究/数据，证据强度+15")
    # 绝对化表述减分
    if any(k in text for k in ["绝对", "完全", "百分之百", "一定", "必然", "所有"]):
        score -= 15
        reasons.append("存在绝对化表述，证据强度-15")
    # 主观感受词减分
    if any(k in text for k in ["我觉得", "我认为", "感觉", "似乎", "好像"]):
        score -= 10
        reasons.append("包含主观感受表述，证据强度-10")
    score = max(0, min(100, score))
    if score >= 80:
        grade = "高"
    elif score >= 50:
        grade = "中"
    else:
        grade = "低"
    return {"score": score, "grade": grade, "reasons": reasons}

def run(state=None, **kwargs):
    """主入口：对高价值认知做深度解读"""
    cogs = load_high_value_cognitions(limit=10)
    if not cogs:
        return {"ok": True, "name": "yin_critical_reading", "result": {"processed": 0, "message": "无高价值认知可解读"}, "evidence": "认知池为空或无S/A级认知"}
    results = []
    output_dir = os.path.join(get_cognition_dir(), "..", "data", "critical_readings")
    os.makedirs(output_dir, exist_ok=True)
    for cog in cogs:
        text = cog["text"]
        if len(text) < 20:
            continue
        thesis = extract_core_thesis(text)
        arg_chain = extract_argument_chain(text)
        assumptions = identify_hidden_assumptions(text, thesis)
        alternatives = generate_alternative_explanations(text, thesis)
        evidence = assess_evidence_strength(text)
        reading = {
            "cognition_id": cog["id"],
            "source_file": cog["file"],
            "grade": cog["grade"],
            "core_thesis": thesis,
            "argument_chain": arg_chain,
            "hidden_assumptions": assumptions,
            "alternative_perspectives": alternatives,
            "evidence_strength": evidence,
            "read_at": datetime.now().isoformat()
        }
        out_file = os.path.join(output_dir, f"reading_{cog['id'] or cog['file'].replace('.json','')}.json")
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(reading, f, ensure_ascii=False, indent=2)
        results.append({
            "id": cog["id"],
            "grade": cog["grade"],
            "evidence_score": evidence["score"],
            "assumptions_count": len(assumptions),
            "alternatives_count": len(alternatives)
        })
    return {
        "ok": True,
        "name": "yin_critical_reading",
        "result": {
            "processed": len(results),
            "readings": results,
            "output_dir": output_dir
        },
        "evidence": f"深度解读{len(results)}条高价值认知，论证链+隐藏前提+替代解释+证据强度四维分析",
        "output_path": output_dir
    }

if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
