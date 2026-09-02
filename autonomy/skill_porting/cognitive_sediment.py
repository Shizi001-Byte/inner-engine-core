#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知沉淀自动化模块
移植自：fanxin-cognitive-sediment（凡心专属认知沉淀与自我迭代技能）
用途：阴期零消耗任务，从引擎产出中自动蒸馏认知沉淀，计算密度分级，生成结构化文档
原则：纯本地规则处理，零API调用；C级低密套话过滤不入库；遵循五步工作流
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
COGNITION_POOL = BASE_DIR / "cognition_pool"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# 套话惩罚词表（命中扣分）
CLICHE_WORDS = [
    "赋能", "抓手", "闭环思维", "底层逻辑", "顶层设计", "生态位",
    "打法", "链路", "颗粒度", "对齐", "拉通", "沉淀", "复用",
    "赋能", "抓手", "闭环", "组合拳", "护城河", "第二曲线",
    "降维打击", "价值洼地", "风口", "赛道", "蓝海", "红海"
]

# 高密度信号词（命中加分）
HIGH_DENSITY_SIGNALS = [
    "具体步骤", "操作方法", "代码", "配置", "参数", "阈值",
    "失败原因", "根因", "临界点", "避坑", "边界", "验证",
    "首次发现", "修正了", "之前错误", "新认知", "整合了"
]

# 可执行密度信号
ACTION_SIGNALS = [
    "应该", "需要", "必须", "可以", "步骤", "方法", "操作",
    "执行", "实施", "修复", "优化", "调整", "配置", "部署"
]


def _extract_sentences(text):
    """从文本中提取句子"""
    # 按句号、问号、感叹号、换行分割
    sentences = re.split(r'[。！？\n]+', text)
    # 过滤太短的
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def _calc_info_density(text):
    """信息密度：核心概念数/总字数"""
    if not text or len(text) < 10:
        return 0.0
    # 数字、专业术语、专有名词计数
    numbers = len(re.findall(r'\d+\.?\d*', text))
    # 引号内的专有名词
    quotes = len(re.findall(r'["「『][^"」』]+["」』]', text))
    # 高密度信号词
    high_signals = sum(1 for w in HIGH_DENSITY_SIGNALS if w in text)
    # 套话惩罚
    cliches = sum(1 for w in CLICHE_WORDS if w in text)
    # 计算
    raw_density = (numbers * 0.3 + quotes * 0.2 + high_signals * 0.3) / (len(text) / 100)
    penalty = cliches * 0.1
    return max(0.0, min(1.0, raw_density - penalty))


def _calc_action_density(text):
    """可执行密度：动作点数/总字数"""
    if not text or len(text) < 10:
        return 0.0
    action_count = sum(1 for w in ACTION_SIGNALS if w in text)
    # 有序列表项（1. 2. 3. 或 - ）
    list_items = len(re.findall(r'^\s*[\d\-\*]+[\.、\)]', text, re.MULTILINE))
    raw = (action_count * 0.3 + list_items * 0.4) / (len(text) / 100)
    return min(1.0, raw)


def _calc_relation_density(cog_data, text):
    """关联密度：关联认知数"""
    # 简单实现：检查文本中是否引用了其他认知/文档/坑库
    relations = 0
    if "认知" in text or "之前" in text or "历史" in text:
        relations += 1
    if "坑" in text or "PIT" in text or "避坑" in text:
        relations += 1
    if "引擎" in text or "state" in text or "配置" in text:
        relations += 1
    return min(1.0, relations * 0.3)


def _grade_cognition(info_d, action_d, relation_d):
    """认知分级：S≥0.7 / A 0.5-0.7 / B 0.3-0.5 / C<0.3"""
    avg = (info_d + action_d + relation_d) / 3
    if avg >= 0.7:
        return "S", avg
    elif avg >= 0.5:
        return "A", avg
    elif avg >= 0.3:
        return "B", avg
    else:
        return "C", avg


def _extract_core_points(sentences, max_points=5):
    """从句子中提取核心认知点（选最长、密度最高的）"""
    scored = []
    for s in sentences:
        density = _calc_info_density(s)
        scored.append((density, s))
    scored.sort(reverse=True)
    return [s for _, s in scored[:max_points]]


def _scan_recent_outputs(limit=10):
    """扫描最近的产出文件"""
    files = []
    for ext in ["*.md", "*.txt"]:
        files.extend(OUTPUTS_DIR.rglob(ext))
    # 按修改时间排序，取最新的
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit]


def _generate_sediment_doc(source_file, text, core_points, grade, densities):
    """生成认知沉淀文档（遵循技能模板）"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    date_compact = datetime.now().strftime("%Y%m%d")
    # 从文件名提取主题关键词
    stem = source_file.stem
    theme = re.sub(r'selfgen_\d+_\d+_', '', stem)[:20] if "selfgen" in stem else stem[:20]

    doc = f"""# 【认知沉淀】{theme}
**日期**：{date_str}
**触发场景**：阴期自动蒸馏（来源：{source_file.name}）
**认知层级**：{'体系级' if grade == 'S' else '深层感悟' if grade == 'A' else '中层逻辑' if grade == 'B' else '表层信息'}
**认知状态**：首次认知
---
## 一、核心认知提炼（{len(core_points)}条）
"""
    for i, point in enumerate(core_points, 1):
        doc += f"{i}. **{point[:80]}**：{point[80:150] if len(point) > 80 else ''}\n"

    doc += f"""
---
## 二、详细展开
### 密度指标
- 信息密度：{densities['info']:.3f}
- 可执行密度：{densities['action']:.3f}
- 关联密度：{densities['relation']:.3f}
- 综合评分：{densities['avg']:.3f}（{grade}级）

### 来源摘要
{text[:500]}...
---
## 三、与历史认知对比
- 状态：首次明确认知（阴期自动蒸馏，待阳期人工确认后可升级为迭代认知）
---
## 四、对体系的影响
- 对记忆修补的影响：待确认
- 对自我迭代的影响：待确认
---
## 五、后续行动点
- [ ] 阳期人工复核，确认是否升级为核心认知
- [ ] 如为S/A级，同步到认知池核心层
---
## 标签
#阴期蒸馏 #自动沉淀 #{grade}级 #{theme}
---
*本文档由阴期认知沉淀模块自动生成，来源：{source_file.name}*
"""
    return doc, theme


def run(state=None, **kwargs):
    """
    阴期任务入口：认知沉淀自动化蒸馏
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    COGNITION_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 扫描最近产出
    recent_files = _scan_recent_outputs(limit=10)
    if not recent_files:
        return {"ok": True, "name": "yin_cognitive_sediment",
                "result": {"status": "skipped", "reason": "no recent outputs"},
                "evidence": "无最近产出文件，跳过"}

    # 2. 逐个处理
    results = []
    new_docs = 0
    grade_counter = Counter()
    for source_file in recent_files:
        try:
            with open(source_file, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if len(text) < 50:
                continue
            # 提取句子
            sentences = _extract_sentences(text)
            if not sentences:
                continue
            # 计算密度
            info_d = _calc_info_density(text)
            action_d = _calc_action_density(text)
            relation_d = _calc_relation_density(None, text)
            grade, avg = _grade_cognition(info_d, action_d, relation_d)
            # C级过滤
            if grade == "C":
                grade_counter["C_filtered"] += 1
                continue
            # 提取核心点
            core_points = _extract_core_points(sentences, max_points=5)
            # 生成文档
            densities = {"info": info_d, "action": action_d, "relation": relation_d, "avg": avg}
            doc, theme = _generate_sediment_doc(source_file, text, core_points, grade, densities)
            # 保存
            date_compact = datetime.now().strftime("%Y%m%d")
            output_path = COGNITION_DIR / f"认知沉淀_{date_compact}_{theme}_{grade}.md"
            # 避免覆盖
            if output_path.exists():
                output_path = COGNITION_DIR / f"认知沉淀_{date_compact}_{theme}_{grade}_{int(time.time())}.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(doc)
            new_docs += 1
            grade_counter[grade] += 1
            results.append({"file": source_file.name, "grade": grade, "avg": round(avg, 3), "output": output_path.name})
        except Exception as e:
            results.append({"file": source_file.name, "error": str(e)[:80]})

    result = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "scanned_files": len(recent_files),
        "new_docs": new_docs,
        "grade_distribution": dict(grade_counter),
        "details": results[:10],
    }

    # 保存产出报告
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"cognitive_sediment_{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    evidence = f"扫描{len(recent_files)}个产出，生成{new_docs}份认知沉淀（{dict(grade_counter)}），C级过滤{grade_counter.get('C_filtered',0)}份"

    return {
        "ok": True,
        "name": "yin_cognitive_sediment",
        "result": result,
        "evidence": evidence,
        "output_path": str(report_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
