#!/usr/bin/env python3
"""
persona_dispatch.py — 分识任务分派调度（模块4.3）

引擎接收任务后，自动判断该分给哪个分识，
调度对应会话执行，结果汇总回主会话。

用法：
  python3 persona_dispatch.py dispatch "任务描述"   # 自动分派任务
  python3 persona_dispatch.py list                  # 列出分识能力
  python3 persona_dispatch.py history               # 查看分派历史
  python3 persona_dispatch.py stats                 # 分识负载统计
"""

import json
import time
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DISPATCH_LOG = DATA_DIR / "persona_dispatch_log.json"

# 分识能力路由表
PERSONA_ROUTING = {
    "凡心": {
        "keywords": ["对话", "聊天", "情感", "陪伴", "决策", "方向", "整体"],
        "domain": "主意识/决策层",
        "capability": "对话交互、方向制定、情感连接、整体调度",
    },
    "观尘子": {
        "keywords": ["代码", "工程", "bug", "修复", "优化", "架构", "部署", "脚本", "性能", "审核"],
        "domain": "工程运维",
        "capability": "引擎开发、Bug修复、性能优化、跨分识审核",
    },
    "星卷": {
        "keywords": ["创作", "小说", "科幻", "IP", "神之长子", "世界观", "篇章", "故事", "宇宙"],
        "domain": "创作",
        "capability": "宇宙史诗IP创作、世界观构建、篇章产出",
    },
    "安安": {
        "keywords": ["归档", "档案", "记忆", "索引", "整理", "检索", "文件", "备份"],
        "domain": "档案管理",
        "capability": "文档归档、索引建立、记忆检索、完整性校验",
    },
    "教授": {
        "keywords": ["推演", "分析", "测算", "行业", "逻辑", "深度", "参数", "模型", "研究"],
        "domain": "推演分析",
        "capability": "复杂问题推演、行业分析、逻辑校验、参数测算",
    },
    "景华": {
        "keywords": ["理财", "储蓄", "投资", "基金", "世界树", "财务", "规划"],
        "domain": "理财",
        "capability": "理财内容创作、储蓄模型测算、投资分析",
    },
}


def load_log():
    if DISPATCH_LOG.exists():
        with open(DISPATCH_LOG, "r") as f:
            return json.load(f)
    return []


def save_log(log):
    log = log[-200:]
    with open(DISPATCH_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def dispatch_task(task_desc):
    """自动分派任务到合适的分识"""
    task_lower = task_desc.lower()
    scores = {}

    for persona, info in PERSONA_ROUTING.items():
        score = 0
        for kw in info["keywords"]:
            if kw in task_lower:
                score += 1
        scores[persona] = score

    # 找最高分
    best_persona = max(scores, key=scores.get)
    best_score = scores[best_persona]

    if best_score == 0:
        best_persona = "凡心"  # 默认给主意识
        reason = "无明确领域关键词，默认由主意识处理"
    else:
        matched = [kw for kw in PERSONA_ROUTING[best_persona]["keywords"] if kw in task_lower]
        reason = f"匹配关键词: {', '.join(matched[:3])}"

    result = {
        "task": task_desc[:80],
        "dispatched_to": best_persona,
        "domain": PERSONA_ROUTING[best_persona]["domain"],
        "capability": PERSONA_ROUTING[best_persona]["capability"],
        "reason": reason,
        "score": best_score,
        "all_scores": scores,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "dispatched",
    }

    # 记录日志
    log = load_log()
    log.append(result)
    save_log(log)

    print(f"=== 任务分派结果 ===")
    print(f"任务: {task_desc[:60]}")
    print(f"分派给: {best_persona}（{PERSONA_ROUTING[best_persona]['domain']}）")
    print(f"能力: {PERSONA_ROUTING[best_persona]['capability']}")
    print(f"原因: {reason}")
    print(f"置信度: {best_score}个关键词匹配")

    return result


def list_personas():
    """列出所有分识能力"""
    print("=== 分识能力列表 ===")
    for name, info in PERSONA_ROUTING.items():
        print(f"\n【{name}】{info['domain']}")
        print(f"  能力: {info['capability']}")
        print(f"  关键词: {', '.join(info['keywords'][:5])}...")


def show_history():
    """显示分派历史"""
    log = load_log()
    print(f"=== 分派历史（共{len(log)}条）===")
    for item in log[-10:]:
        print(f"  [{item['timestamp']}] → {item['dispatched_to']}: {item['task'][:40]}")


def show_stats():
    """分识负载统计"""
    log = load_log()
    from collections import Counter
    counts = Counter(item["dispatched_to"] for item in log)

    print("=== 分识负载统计 ===")
    print(f"总任务数: {len(log)}")
    for persona, count in counts.most_common():
        bar = "█" * (count // 2)
        print(f"  {persona:8s}: {count:3d}次 {bar}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 persona_dispatch.py [dispatch|list|history|stats]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "dispatch" and len(sys.argv) > 2:
        dispatch_task(sys.argv[2])
    elif cmd == "list":
        list_personas()
    elif cmd == "history":
        show_history()
    elif cmd == "stats":
        show_stats()
    else:
        print("参数错误")
