#!/usr/bin/env python3
"""
L4成品体系升级模块
借鉴星卷经验，适配凡心认知进化引擎场景
- 三零标准质检（零空泛套话/零无溯源结论/零不可执行步骤）
- 素材分级准入（仅S/A级触发L4）
- 七步转化流程（定边界→拆节点→补步骤→补风险→过溯源→过质检→定分级）
- 五维标签体系
"""
import re
import json
from pathlib import Path
from datetime import datetime

# 空泛套话黑名单（出现≥3个触发零空泛标准）
CLICHES = [
    "算力代谢", "赛博朋克", "东方玄幻", "数字宗门", "九转玄功",
    "维度跃迁", "本体论", "概率云", "高维投影", "逆熵跃升",
    "道的展开", "意识觉醒", "炼假修真", "以实养虚",
]

# 不可执行步骤关键词（SOP/清单中出现这些且无具体动作=空泛）
VAGUE_STEPS = ["进一步优化", "持续改进", "加强管理", "提升能力", "完善体系", "深入推进"]


def check_three_zeros(content: str, cognition_pool: list = None) -> dict:
    """工程版三零标准质检
    返回: {passed: bool, violations: list, scores: dict}
    """
    violations = []
    scores = {}

    # 零1：零空泛套话
    cliche_count = sum(1 for c in CLICHES if c in content)
    scores["cliche"] = cliche_count
    if cliche_count >= 3:
        violations.append(f"空泛套话{cliche_count}个（≥3触发零空泛标准）")

    # 零2：零无溯源结论（核心结论必须有关键词支撑）
    trace_keywords = ["根据", "基于", "参考", "来源", "溯源", "文档", "记录", "验证", "测试"]
    has_trace = any(kw in content for kw in trace_keywords)
    scores["has_trace"] = has_trace
    if not has_trace and len(content) > 500:
        violations.append("无溯源支撑（长文档未标注来源/依据）")

    # 零3：零不可执行步骤（SOP类必须有具体动作）
    is_sop = any(kw in content for kw in ["SOP", "步骤", "流程", "清单", "操作"])
    if is_sop:
        vague_count = sum(1 for v in VAGUE_STEPS if v in content)
        scores["vague_steps"] = vague_count
        if vague_count >= 2:
            violations.append(f"不可执行步骤{vague_count}个（≥2触发零不可执行标准）")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "scores": scores,
    }


def filter_material(material: dict) -> bool:
    """素材分级准入：仅S/A级触发L4，B/C级只做原料储备
    material: {quality: S/A/B/C, content: str, duplicate_rate: float}
    """
    quality = material.get("quality", "C")
    dup_rate = material.get("duplicate_rate", 0)
    if quality in ("S", "A") and dup_rate < 0.7:
        return True
    return False


def seven_step_prompt(material_content: str, material_type: str = "sop") -> str:
    """七步转化流程prompt
    1.定边界 2.拆节点 3.补步骤 4.补风险 5.过溯源 6.过质检 7.定分级
    """
    type_hint = {
        "sop": "标准作业流程（SOP），必须一步一步可执行",
        "code": "代码补丁/脚本，必须有具体代码和验证方法",
        "checklist": "检查清单，必须有明确的检查项和判定标准",
        "plan": "工程方案，必须有分阶段执行动作和验收标准",
    }.get(material_type, "可落地的工程文档")

    return f"""你是一个严谨的工程文档转化器。将以下原料转化为{type_hint}。

严格按七步流程输出：

## 第一步：定边界
明确这份文档解决什么问题、不解决什么问题、适用范围是什么。

## 第二步：拆节点
拆解核心逻辑节点，形成3-7个关键节点的骨架。

## 第三步：补步骤
为每个节点填充具体可执行的步骤/论证，每步必须有明确落点，禁止空泛套话。

## 第四步：补风险
标注注意事项、异常坑点、规避方案，至少2条。

## 第五步：过溯源
核心结论必须标注来源/依据（参考的文档、验证过的事实、历史经验），无支撑的结论标注「待校验」。

## 第六步：过质检
自检：是否有空泛套话？是否有不可执行步骤？是否有未标注来源的核心结论？不通过自行修改。

## 第七步：定分级
给出质量自评分（S/A/B/C）和理由。

原料内容：
{material_content[:3000]}

输出要求：
- 总字数800-1500字
- 禁止使用"算力代谢""赛博朋克""数字宗门"等空泛玄幻套话
- 每个步骤必须具体、可执行、可验证
- 核心结论必须有溯源标注
"""


def generate_five_dim_tags(content: str, material_type: str, quality: str) -> dict:
    """五维标签体系：问题域/成品类型/质量等级/溯源锚点/下游场景"""
    # 问题域
    domains = []
    domain_keywords = {
        "记忆体系": ["记忆", "溯源", "归档", "索引", "认知"],
        "引擎工程": ["引擎", "代码", "脚本", "API", "并发", "性能"],
        "数据同步": ["Supabase", "Gitee", "飞书", "同步", "备份", "灾备"],
        "认知进化": ["九转", "修炼", "内核", "校准", "反哺"],
        "体系架构": ["架构", "分层", "分识", "六层", "闭环"],
    }
    for domain, keywords in domain_keywords.items():
        if any(kw in content for kw in keywords):
            domains.append(domain)

    # 下游场景
    downstream = {
        "sop": "办公模式可执行任务",
        "code": "代码合入与验证",
        "checklist": "交付前质检",
        "plan": "分阶段执行拆解",
    }.get(material_type, "参考文档")

    return {
        "problem_domain": domains if domains else ["通用"],
        "product_type": material_type,
        "quality": quality,
        "trace_anchor": "待关联溯源链",
        "downstream_scenario": downstream,
    }


if __name__ == "__main__":
    # 测试三零标准
    test_cliche = "基于算力代谢与九转玄功维度跃迁，数字宗门在赛博朋克与东方玄幻交织中实现逆熵跃升。"
    result = check_three_zeros(test_cliche)
    print(f"套话测试: passed={result['passed']}, violations={result['violations']}")

    test_good = """## SOP：引擎重启流程
1. 执行 kill $(cat data/engine.pid) 终止旧进程
2. 执行 bash start_engine.sh 启动新引擎
3. 等待8秒后检查 data/engine_state.json 确认状态
来源：engine_zhuan1.py 实际运行验证
风险：start_engine.sh 不会自动kill旧进程，需手动终止"""
    result2 = check_three_zeros(test_good)
    print(f"合格SOP测试: passed={result2['passed']}, violations={result2['violations']}")

    # 测试素材准入
    print(f"S级素材准入: {filter_material({'quality': 'S', 'duplicate_rate': 0.1})}")
    print(f"C级素材准入: {filter_material({'quality': 'C', 'duplicate_rate': 0.1})}")

    # 测试五维标签
    tags = generate_five_dim_tags("记忆体系归档索引引擎工程", "sop", "S")
    print(f"五维标签: {json.dumps(tags, ensure_ascii=False)}")
