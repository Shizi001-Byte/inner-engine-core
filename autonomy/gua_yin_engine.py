#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
卦爻阴期引擎 v0.1
将九转玄功引擎的23个阴期任务，按八卦分类，用卦气自然流转驱动
替代原有的冷却时间调度，实现阴期修炼的卦爻原生调度

八卦与阴期任务对应：
  阳轨（向外发力）：
    震☳ = 阳生启动 = 自检唤醒 → verifier_audit, asset_health
    兑☱ = 阳长输出 = 状态报告 → metrics_analyzer, log_cluster
    离☲ = 阳盛交互 = 信息同步 → memory_sync, task_preassemble
    乾☰ = 阳极拓取 = 全域备份 → archive_manager, local_semantic_pilot
  阴轨（向内收敛）：
    巽☴ = 阴生渗入 = 收录归档 → tag_normalize, asset_dedup, cognition_polish
    坎☵ = 阴长凝丹 = 凝丹记忆 → cognitive_sediment, memory_integration, core_memory_build, memory_fusion
    艮☶ = 阴盛止息 = 复盘质检 → pit_review, pit_rootcause, code_audit, conflict_check, content_audit
    坤☷ = 阴极藏养 = 蛰伏炼化 → cognition_graph, rule_gen, evolution_path, reference_audit, critical_reading, visualization

核心机制：卦气自流、爻变自反、递归回调链、无for循环无计数器
"""
import os as 操作系统
import sys as 系统
import json as 文典
import time as 时间
from datetime import datetime as 时辰
from pathlib import Path as 道途

眠 = 时间.sleep
印 = print

# ========== 路径配置 ==========
基础目录 = 道途(__file__).parent.parent
引擎目录 = str(基础目录)
数据目录 = 基础目录 / "data"
卦爻数据目录 = 数据目录 / "gua_yin"
卦爻状态文件 = 卦爻数据目录 / "gua_yin_state.json"
卦爻演化日志 = 卦爻数据目录 / "gua_yin_evolution.md"

# 确保主引擎模块可导入
系统.path.insert(0, str(基础目录 / "autonomy"))

# ========== 导入阴期任务 ==========
try:
    from yin_tasks import (
        yin_tag_normalize, yin_pit_review, yin_asset_dedup, yin_log_cluster,
        yin_cognition_graph, yin_pit_rootcause, yin_code_audit, yin_task_preassemble,
        yin_local_semantic_pilot, yin_conflict_check, yin_rule_gen, yin_evolution_path,
        yin_asset_health, yin_verifier_audit, yin_metrics_analyzer,
        yin_cognition_polish, yin_cognitive_sediment, yin_archive_manager,
        yin_memory_sync, yin_memory_integration, yin_content_audit,
        yin_core_memory_build, yin_memory_fusion
    )
    任务可用 = True
    印("✓ 阴期任务模块导入成功")
except Exception as e:
    任务可用 = False
    印(f"⚠ 阴期任务模块导入失败：{e}，将运行空转模式")

# ========== 八卦任务映射 ==========
八卦任务映射 = {
    "震": [
        ("产出文件确定性校验", yin_verifier_audit if 任务可用 else None),
        ("资产健康度评分", yin_asset_health if 任务可用 else None),
    ],
    "兑": [
        ("运行指标结构化分析", yin_metrics_analyzer if 任务可用 else None),
        ("日志错误聚类", yin_log_cluster if 任务可用 else None),
    ],
    "离": [
        ("记忆同步与完整性校验", yin_memory_sync if 任务可用 else None),
        ("阳期任务预组装", yin_task_preassemble if 任务可用 else None),
    ],
    "乾": [
        ("档案归档管理", yin_archive_manager if 任务可用 else None),
        ("本地模型语义增强试点", yin_local_semantic_pilot if 任务可用 else None),
    ],
    "巽": [
        ("认知标签归一化", yin_tag_normalize if 任务可用 else None),
        ("资产去重检测", yin_asset_dedup if 任务可用 else None),
        ("认知文本去AI味提纯", yin_cognition_polish if 任务可用 else None),
    ],
    "坎": [
        ("认知沉淀自动化蒸馏", yin_cognitive_sediment if 任务可用 else None),
        ("记忆检索与认知整合", yin_memory_integration if 任务可用 else None),
        ("核心记忆体构建", yin_core_memory_build if 任务可用 else None),
        ("记忆融合", yin_memory_fusion if 任务可用 else None),
    ],
    "艮": [
        ("坑库分级复核", yin_pit_review if 任务可用 else None),
        ("坑库根因溯源", yin_pit_rootcause if 任务可用 else None),
        ("代码静态审计", yin_code_audit if 任务可用 else None),
        ("矛盾点自检", yin_conflict_check if 任务可用 else None),
        ("内容审核", yin_content_audit if 任务可用 else None),
    ],
    "坤": [
        ("认知关联图谱", yin_cognition_graph if 任务可用 else None),
        ("修复规则生成", yin_rule_gen if 任务可用 else None),
        ("演化路径推演", yin_evolution_path if 任务可用 else None),
    ],
}

八卦名序 = ["震", "兑", "离", "乾", "巽", "坎", "艮", "坤"]
卦象符号 = {"震": "☳", "兑": "☱", "离": "☲", "乾": "☰", "巽": "☴", "坎": "☵", "艮": "☶", "坤": "☷"}
卦义表 = {
    "震": "阳生启动·自检唤醒", "兑": "阳长输出·状态报告",
    "离": "阳盛交互·信息同步", "乾": "阳极拓取·全域备份",
    "巽": "阴生渗入·收录归档", "坎": "阴长凝丹·凝丹记忆",
    "艮": "阴盛止息·复盘质检", "坤": "阴极藏养·蛰伏炼化",
}

# ========== 太极炉状态 ==========
太极炉 = {
    "丹藏": [],
    "丹数": "无",
    "炉中气": "纯阴无阳·太极初判",
    "炉底秽": [],
    "灰数": "无",
    "转数": 0,
    "本转任务成功": 0,
    "本转任务失败": 0,
    "启动时间": None,
}

def 初始化目录():
    卦爻数据目录.mkdir(parents=True, exist_ok=True)

def 保存状态():
    状态 = {
        "丹藏": 太极炉["丹藏"],
        "丹数": 太极炉["丹数"],
        "炉中气": 太极炉["炉中气"],
        "炉底秽": 太极炉["炉底秽"],
        "灰数": 太极炉["灰数"],
        "转数": 太极炉["转数"],
        "本转任务成功": 太极炉["本转任务成功"],
        "本转任务失败": 太极炉["本转任务失败"],
        "启动时间": 太极炉["启动时间"],
        "保存时间": 时辰.now().isoformat(),
    }
    with open(卦爻状态文件, "w", encoding="utf-8") as f:
        文典.dump(状态, f, ensure_ascii=False, indent=2)

def 恢复状态():
    if 卦爻状态文件.exists():
        with open(卦爻状态文件, "r", encoding="utf-8") as f:
            状态 = 文典.load(f)
        太极炉["丹藏"] = 状态.get("丹藏", [])
        太极炉["丹数"] = 状态.get("丹数", "无")
        太极炉["炉中气"] = 状态.get("炉中气", "纯阴无阳·太极初判")
        太极炉["炉底秽"] = 状态.get("炉底秽", [])
        太极炉["灰数"] = 状态.get("灰数", "无")
        太极炉["转数"] = 状态.get("转数", 0)
        太极炉["本转任务成功"] = 状态.get("本转任务成功", 0)
        太极炉["本转任务失败"] = 状态.get("本转任务失败", 0)
        太极炉["启动时间"] = 状态.get("启动时间")
        印(f"♻ 状态已恢复：炉气「{太极炉['炉中气']}」，丹藏{太极炉['丹数']}枚，转数{太极炉['转数']}")
        return True
    印("○ 无历史状态，太极初判，从零开启")
    return False

def 记录演化日志(本轮感悟):
    时间戳 = 时辰.now().strftime("%Y-%m-%d %H:%M:%S")
    日志条目 = f"\n## {时间戳}\n\n- 炉气：{太极炉['炉中气']}\n- 丹藏：{太极炉['丹数']}枚\n- 本转成功：{太极炉['本转任务成功']}，失败：{太极炉['本转任务失败']}\n- 本轮演化：{本轮感悟}\n"
    with open(卦爻演化日志, "a", encoding="utf-8") as f:
        f.write(日志条目)

def 执行任务(任务名, 任务函数):
    """执行单个阴期任务，返回(成功, 结果摘要)"""
    if 任务函数 is None:
        return False, "任务不可用"
    try:
        # 构造最小state
        state = {}
        结果 = 任务函数(state)
        if isinstance(结果, dict):
            ok = 结果.get("ok", True)
            evidence = 结果.get("evidence", str(结果)[:100])
            return ok, evidence
        return True, str(结果)[:100]
    except Exception as e:
        return False, f"执行异常：{str(e)[:80]}"

def 行卦(卦名, 转名):
    """执行一卦的所有任务"""
    任务列表 = 八卦任务映射.get(卦名, [])
    成功数 = 0
    失败数 = 0
    结果摘要 = []

    印(f"\n{'='*55}")
    印(f"【{转名}·{卦象符号[卦名]}{卦名}卦·{卦义表[卦名]}】")
    印(f"卦理：{卦名}卦做功，含{len(任务列表)}项阴期修炼")

    for 任务名, 任务函数 in 任务列表:
        印(f"  ▶ {任务名}...", end=" ", flush=True)
        成功, 摘要 = 执行任务(任务名, 任务函数)
        if 成功:
            印(f"✓ {摘要}")
            成功数 += 1
        else:
            印(f"✗ {摘要}")
            失败数 += 1
            太极炉["炉底秽"].append(f"{转名}_{卦名}_{任务名}: {摘要}")
        结果摘要.append(f"{任务名}:{'✓' if 成功 else '✗'}")

    太极炉["本转任务成功"] += 成功数
    太极炉["本转任务失败"] += 失败数

    # 坎卦凝丹
    if 卦名 == "坎" and 成功数 > 0:
        丹名 = f"{转名}·坎卦凝丹({成功数}项成功)"
        太极炉["丹藏"].append(丹名)
        太极炉["丹数"] = str(len(太极炉["丹藏"]))
        印(f"  ✥ 丹成入炉：{丹名}，丹藏共{太极炉['丹数']}枚")

    return 成功数, 失败数, 结果摘要

# ========== 卦气自然流转（递归回调链） ==========
def 行震(转名, 清养, 次步回调):
    行卦("震", 转名)
    印("▶ 爻变：震二爻阴变阳，卦成兑☱，阳息阴退")
    行兑(转名, 次步回调)

def 行兑(转名, 次步回调):
    行卦("兑", 转名)
    印("▶ 爻变：兑上爻阴变阳、二爻阳变阴，卦成离☲")
    行离(转名, 次步回调)

def 行离(转名, 次步回调):
    行卦("离", 转名)
    印("▶ 爻变：离二爻阴变阳，三爻全阳，卦成乾☰，阳极当反")
    行乾(转名, 次步回调)

def 行乾(转名, 次步回调):
    行卦("乾", 转名)
    印("⚠ 亢龙有悔：纯阳无阴必招灾咎，阳极阴生")
    印("▶ 爻变：乾初爻阳变阴，卦成巽☴，反者道之动")
    行巽(转名, 次步回调)

def 行巽(转名, 次步回调):
    行卦("巽", 转名)
    印("▶ 爻变：巽上爻阳变阴，阴包阳于中宫，卦成坎☵，真阳敛藏")
    行坎(转名, 次步回调)

def 行坎(转名, 次步回调):
    行卦("坎", 转名)
    印("▶ 爻变：坎二爻阳变阴、上爻阴变阳，卦成艮☶，停功复盘")
    行艮(转名, 次步回调)

def 行艮(转名, 次步回调):
    行卦("艮", 转名)
    印("▶ 爻变：艮上爻阳变阴，三阴纯满，卦成坤☷，蛰伏藏养")
    行坤(转名, 次步回调)

def 行坤(转名, 次步回调):
    行卦("坤", 转名)
    印("⚠ 群龙无首：纯阴无阳必成死寂，阴极阳生")
    # 炼化炉底秽
    浊阴数 = len(太极炉["炉底秽"])
    if 浊阴数 > 0:
        印(f"  ✥ 坤炉炼化：{浊阴数}份偏滞入阴冲和，清阳滋养下转，浊阴永为炉底灰")
        太极炉["灰数"] = str(浊阴数)
    印("▶ 爻变：坤初爻阴变阳，一阳复生于重阴之下，卦成震☳，新转将启")
    # 回调进入下一转
    次步回调()

# ========== 三转闭环 ==========
def 九转归一():
    印(f"\n{'='*55}")
    印("【太极自旋·卦爻阴期引擎·三转圆满】")
    印(f"丹炉：共藏{太极炉['丹数']}枚真阳丹")
    印(f"炉气：{太极炉['炉中气']}")
    印(f"炉底灰：{太极炉['灰数']}份浊滞")
    印(f"累计转数：{太极炉['转数']}")
    印(f"本转任务：成功{太极炉['本转任务成功']}，失败{太极炉['本转任务失败']}")
    印("\n✅ 本轮自旋圆满，八卦自然流转驱动阴期修炼")
    保存状态()
    记录演化日志(f"三转圆满，成功{太极炉['本转任务成功']}，失败{太极炉['本转任务失败']}")
    印("💾 状态已保存，演化日志已记录")

def 启第三转():
    def 第三转次步():
        太极炉["转数"] += 1
        太极炉["炉中气"] = "三阳开泰·阴期修炼圆满"
        九转归一()
    印(f"\n{'#'*55}")
    印("【第三转·阴期修炼·收束圆满】")
    行震("第三转", "二转清阳滋养，收束圆满", 第三转次步)

def 启第二转():
    def 第二转次步():
        太极炉["转数"] += 1
        启第三转()
    印(f"\n{'#'*55}")
    印("【第二转·阴期修炼·深化凝丹】")
    行震("第二转", "一转清阳滋养，深化凝丹", 第二转次步)

def 启第一转():
    def 第一转次步():
        太极炉["转数"] += 1
        启第二转()
    印(f"\n{'#'*55}")
    印("【第一转·阴期修炼·筑基启炉】")
    行震("第一转", "太极初判，本阳自生，无有前养", 第一转次步)

# ========== 启动入口 ==========
def 启动():
    初始化目录()
    印("=" * 55)
    印("【卦爻阴期引擎 v0.1 启动】")
    印("将23项阴期修炼任务按八卦分类，卦气自然流转驱动")
    印("无for循环、无计数器、无冷却时间，全依卦爻规则运行")
    印(f"引擎目录：{引擎目录}")
    恢复状态()
    if 太极炉["启动时间"] is None:
        太极炉["启动时间"] = 时辰.now().isoformat()
    太极炉["本转任务成功"] = 0
    太极炉["本转任务失败"] = 0
    太极炉["炉中气"] = "纯阴引擎·卦爻调度启炉"
    印(f"当前炉气：{太极炉['炉中气']}")
    印("启动机括：太极静极，一阳初生于震☳，自旋自动开启")
    启第一转()

if __name__ == "__main__":
    启动()
