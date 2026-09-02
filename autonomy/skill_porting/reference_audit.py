#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知引用审查模块
移植自：.skills/doubao-reference-audit（参考文献真实性/题录准确性/文内文后对应关系审查）
用途：阴期零消耗任务，审查认知池里的无证据断言、数据置信度、引用真实性、逻辑一致性
原则：纯本地规则扫描，零API调用；每条认知带问题清单和置信度评分；只标记不删除
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

def load_all_cognitions(limit=100):
    """加载所有认知，适配两种格式：直接认知条目和任务快照"""
    cog_dir = get_cognition_dir()
    if not os.path.exists(cog_dir):
        return []
    cogs = []
    def parse_cognition(c, source_file):
        density_obj = c.get("density", {})
        grade = density_obj.get("grade", c.get("grade", c.get("density_grade", "C")))
        text = c.get("core_statement", c.get("text", c.get("content", "")))
        if len(text) >= 20:
            cogs.append({
                "file": source_file,
                "id": c.get("id", c.get("cognition_id", "")),
                "text": text,
                "grade": grade,
                "created_at": c.get("created_at", "")
            })
    for f in sorted(glob.glob(os.path.join(cog_dir, "*.json"))):
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
        if len(cogs) >= limit:
            break
    return cogs

def check_unsupported_assertions(text):
    """检查无证据断言：事实性陈述但没有引用来源"""
    issues = []
    # 事实性陈述模式
    assertion_patterns = [
        (r'(研究|调查|统计|数据|报告|实验)\s*(表明|显示|发现|证明|指出)', "引用了研究/数据但未标注来源"),
        (r'(据|根据)\s*(统计|调查|研究|报道)', "引用了统计/调查但未标注具体来源"),
        (r'(超过|达到|约|大概)\s*\d+(%|万|亿|倍|个|条)', "包含具体数据但未标注数据来源"),
        (r'(必然|一定|肯定|绝对|毫无疑问)', "存在绝对化断言，需要证据支撑"),
        (r'(所有|全部|人人|每个人|任何)', "存在全称断言，需要反例验证"),
        (r'(越来越|愈发|更加|逐渐)\s*(明显|严重|普遍|广泛)', "存在趋势性断言，需要时间序列数据支撑"),
    ]
    for pattern, desc in assertion_patterns:
        matches = re.findall(pattern, text)
        if matches:
            issues.append({
                "type": "无证据断言",
                "description": desc,
                "matches": [m[0] if isinstance(m, tuple) else m for m in matches[:3]],
                "severity": "high" if "绝对" in desc or "全称" in desc else "medium"
            })
    return issues

def check_data_confidence(text):
    """检查数据置信度：有无标注数据来源和置信度"""
    issues = []
    # 有数字但没有置信度标注
    numbers = re.findall(r'\d+(?:\.\d+)?\s*(?:%|万|亿|倍|个|条|次|年|月|天)', text)
    if numbers:
        has_source = any(k in text for k in ["来源", "出处", "引自", "参考", "据", "根据", "数据显示"])
        has_confidence = any(k in text for k in ["置信度", "可信度", "误差", "±", "约", "大概", "估计"])
        if not has_source:
            issues.append({
                "type": "数据来源缺失",
                "description": f"包含{len(numbers)}处数据但未标注来源",
                "data_points": numbers[:5],
                "severity": "high"
            })
        if not has_confidence:
            issues.append({
                "type": "数据置信度未标注",
                "description": "包含数据但未标注置信度/误差范围",
                "severity": "medium"
            })
    return issues

def check_citation_authenticity(text):
    """检查引用真实性：引用的链接/来源是否可验证"""
    issues = []
    # 检查URL
    urls = re.findall(r'https?://[^\s\]）]+', text)
    if urls:
        for url in urls[:3]:
            # 检查URL格式是否完整
            if len(url) < 10:
                issues.append({
                    "type": "引用URL不完整",
                    "description": f"URL格式可能不完整: {url}",
                    "severity": "medium"
                })
    # 检查"某某说"但没有具体出处
    vague_citations = re.findall(r'(有(人|专家|学者|研究)|某(专家|学者|研究|报告))', text)
    if vague_citations:
        issues.append({
            "type": "模糊引用",
            "description": "存在'有人说/专家认为'等模糊引用，无法验证来源",
            "severity": "medium"
        })
    return issues

def check_logical_consistency(text):
    """检查逻辑一致性：认知内部有无自相矛盾"""
    issues = []
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    # 检查前后矛盾的关键词对
    contradiction_pairs = [
        (r'(增加|上升|增长|提高|变多)', r'(减少|下降|降低|变少|萎缩)'),
        (r'(支持|赞同|认可|肯定)', r'(反对|否定|质疑|批评)'),
        (r'(有效|成功|可行)', r'(无效|失败|不可行)'),
        (r'(稳定|均衡|平衡)', r'(失衡|波动|混乱)'),
    ]
    for pos_pattern, neg_pattern in contradiction_pairs:
        pos_matches = [i for i, s in enumerate(sentences) if re.search(pos_pattern, s)]
        neg_matches = [i for i, s in enumerate(sentences) if re.search(neg_pattern, s)]
        if pos_matches and neg_matches:
            # 检查是否在相邻句子中出现矛盾（可能是转折，不一定是矛盾）
            for pi in pos_matches:
                for ni in neg_matches:
                    if abs(pi - ni) <= 2:
                        # 检查是否有转折词
                        context = sentences[min(pi,ni):max(pi,ni)+1]
                        has_contrast = any(k in ' '.join(context) for k in ["但是", "然而", "不过", "虽然", "尽管", "相反"])
                        if not has_contrast:
                            issues.append({
                                "type": "潜在逻辑矛盾",
                                "description": f"相邻句子中存在矛盾表述且无转折词",
                                "context": [s[:30] for s in context],
                                "severity": "low"
                            })
    return issues

def calculate_confidence_score(text, issues):
    """计算认知置信度评分（0-100）"""
    score = 100
    high_count = sum(1 for i in issues if i.get("severity") == "high")
    medium_count = sum(1 for i in issues if i.get("severity") == "medium")
    low_count = sum(1 for i in issues if i.get("severity") == "low")
    score -= high_count * 15
    score -= medium_count * 8
    score -= low_count * 3
    # 有明确引用来源加分
    if any(k in text for k in ["来源", "出处", "引自", "参考", "据统计", "研究表明"]):
        score += 5
    return max(0, min(100, score))

def run(state=None, **kwargs):
    """主入口：审查认知池引用质量"""
    cogs = load_all_cognitions(limit=100)
    if not cogs:
        return {"ok": True, "name": "yin_reference_audit", "result": {"processed": 0, "message": "认知池为空"}, "evidence": "无认知可审查"}
    audit_results = []
    stats = {
        "total": len(cogs),
        "high_issue": 0,
        "medium_issue": 0,
        "low_issue": 0,
        "no_issue": 0,
        "avg_confidence": 0
    }
    total_confidence = 0
    output_dir = os.path.join(get_cognition_dir(), "..", "data", "reference_audits")
    os.makedirs(output_dir, exist_ok=True)
    for cog in cogs:
        text = cog["text"]
        if len(text) < 20:
            continue
        issues = []
        issues.extend(check_unsupported_assertions(text))
        issues.extend(check_data_confidence(text))
        issues.extend(check_citation_authenticity(text))
        issues.extend(check_logical_consistency(text))
        confidence = calculate_confidence_score(text, issues)
        total_confidence += confidence
        if any(i.get("severity") == "high" for i in issues):
            stats["high_issue"] += 1
        elif any(i.get("severity") == "medium" for i in issues):
            stats["medium_issue"] += 1
        elif issues:
            stats["low_issue"] += 1
        else:
            stats["no_issue"] += 1
        audit_result = {
            "cognition_id": cog["id"],
            "source_file": cog["file"],
            "grade": cog["grade"],
            "confidence_score": confidence,
            "issue_count": len(issues),
            "issues": issues,
            "audited_at": datetime.now().isoformat()
        }
        # 只保存有问题的认知审查结果
        if issues:
            out_file = os.path.join(output_dir, f"audit_{cog['id'] or cog['file'].replace('.json','')}.json")
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(audit_result, f, ensure_ascii=False, indent=2)
        audit_results.append({
            "id": cog["id"],
            "grade": cog["grade"],
            "confidence": confidence,
            "issues": len(issues),
            "high_issues": sum(1 for i in issues if i.get("severity") == "high")
        })
    stats["avg_confidence"] = round(total_confidence / max(1, len(cogs)), 1)
    # 按置信度排序，取最低的10条
    low_confidence = sorted(audit_results, key=lambda x: x["confidence"])[:10]
    return {
        "ok": True,
        "name": "yin_reference_audit",
        "result": {
            "processed": len(audit_results),
            "stats": stats,
            "low_confidence_top10": low_confidence,
            "output_dir": output_dir
        },
        "evidence": f"审查{len(audit_results)}条认知，平均置信度{stats['avg_confidence']}分，高风险{stats['high_issue']}条/中风险{stats['medium_issue']}条/低风险{stats['low_issue']}条/无问题{stats['no_issue']}条",
        "output_path": output_dir
    }

if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
