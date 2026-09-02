#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行记忆快照生成器 Runtime Memory Snapshot Generator
第一层核心记忆闭环 - 阳期侧工具
功能：每轮对话/任务结束时，自动生成关键快照（指令/核心推理/关键结果/关键认知/错误），存snapshots目录
原则：只存关键信息不存冗余；快照是阴期记忆融合的输入；可手动或自动触发
用法：
  python snapshot_generator.py --instruction "用户指令" --results "结果1,结果2" --insights "认知1,认知2"
  python snapshot_generator.py --from-log "对话日志文件路径"
  作为模块导入：from snapshot_generator import create_snapshot
"""
import json
import re
import os
import sys
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent.parent
SNAPSHOTS_DIR = BASE_DIR / "data" / "snapshots"
MAX_SNAPSHOTS = 200  # 最多保留200个快照


def _ensure_dir():
    """确保快照目录存在"""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_old_snapshots():
    """清理过旧的快照，只保留最近MAX_SNAPSHOTS个"""
    if not SNAPSHOTS_DIR.exists():
        return
    snapshots = sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), key=lambda f: f.stat().st_mtime)
    if len(snapshots) > MAX_SNAPSHOTS:
        for f in snapshots[:-MAX_SNAPSHOTS]:
            try:
                f.unlink()
            except Exception:
                pass


def _extract_key_points(text, max_points=5, min_length=10):
    """从文本中提取关键点（按句子分割，选最长/最有信息量的）"""
    if not text:
        return []
    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= min_length]
    # 按长度排序，选最长的
    sentences.sort(key=len, reverse=True)
    return sentences[:max_points]


def create_snapshot(instruction="", core_reasoning="", key_results=None,
                    key_insights=None, errors=None, tasks_executed=None,
                    trigger="manual", duration_seconds=0, extra=None):
    """
    创建运行记忆快照

    参数:
        instruction: 本轮核心指令
        core_reasoning: 核心推理过程摘要
        key_results: 关键结果列表
        key_insights: 关键认知列表
        errors: 错误列表 [{"type": "", "message": ""}]
        tasks_executed: 执行的任务列表
        trigger: 触发方式 manual/auto/error
        duration_seconds: 本轮耗时
        extra: 额外数据

    返回:
        快照文件路径
    """
    _ensure_dir()

    now = datetime.now()
    snapshot_id = f"snap_{now.strftime('%Y%m%d_%H%M%S')}"

    # 自动提取关键点
    if not key_results and core_reasoning:
        key_results = _extract_key_points(core_reasoning, max_points=3)
    if not key_insights and core_reasoning:
        # 从推理中提取包含"发现/意识到/原来/关键"的句子
        insights = [s for s in re.split(r'[。！？\n]+', core_reasoning)
                    if any(kw in s for kw in ["发现", "意识", "原来", "关键", "本质", "核心", "终于"])]
        key_insights = insights[:3] if insights else None

    snapshot = {
        "snapshot_id": snapshot_id,
        "created_at": now.isoformat(),
        "trigger": trigger,
        "instruction": instruction[:200] if instruction else "",
        "core_reasoning": core_reasoning[:500] if core_reasoning else "",
        "key_results": key_results or [],
        "key_insights": key_insights or [],
        "errors": errors or [],
        "tasks_executed": tasks_executed or [],
        "duration_seconds": round(duration_seconds, 1) if duration_seconds else 0,
    }
    if extra:
        snapshot["extra"] = extra

    # 保存快照
    filename = f"snapshot_{snapshot_id}.json"
    filepath = SNAPSHOTS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # 清理旧快照
    _cleanup_old_snapshots()

    return str(filepath)


def create_snapshot_from_conversation(conversation_text, instruction=""):
    """从对话日志中自动提取并创建快照"""
    # 提取关键结果（包含"完成/成功/生成/创建"的句子）
    results = [s for s in re.split(r'[。！？\n]+', conversation_text)
               if any(kw in s for kw in ["完成", "成功", "生成", "创建", "实现", "修复", "通过"])]
    # 提取关键认知
    insights = [s for s in re.split(r'[。！？\n]+', conversation_text)
                if any(kw in s for kw in ["发现", "意识", "原来", "关键", "本质", "核心", "终于", "离谱"])]
    # 提取错误
    errors = []
    for s in re.split(r'[。！？\n]+', conversation_text):
        if any(kw in s for kw in ["错误", "失败", "报错", "异常", "bug", "Bug"]):
            errors.append({"type": "runtime", "message": s[:100]})

    return create_snapshot(
        instruction=instruction,
        core_reasoning=conversation_text[:500],
        key_results=results[:5],
        key_insights=insights[:5],
        errors=errors[:5],
        trigger="auto_from_conversation",
    )


def list_snapshots(limit=10):
    """列出最近的快照"""
    if not SNAPSHOTS_DIR.exists():
        return []
    snapshots = sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in snapshots[:limit]:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            result.append({
                "file": f.name,
                "snapshot_id": data.get("snapshot_id", ""),
                "created_at": data.get("created_at", ""),
                "trigger": data.get("trigger", ""),
                "instruction": data.get("instruction", "")[:60],
                "results_count": len(data.get("key_results", [])),
                "insights_count": len(data.get("key_insights", [])),
                "errors_count": len(data.get("errors", [])),
            })
        except Exception:
            pass
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行记忆快照生成器")
    parser.add_argument("--instruction", "-i", default="", help="本轮核心指令")
    parser.add_argument("--reasoning", "-r", default="", help="核心推理摘要")
    parser.add_argument("--results", "-res", default="", help="关键结果，逗号分隔")
    parser.add_argument("--insights", "-ins", default="", help="关键认知，逗号分隔")
    parser.add_argument("--trigger", "-t", default="manual", help="触发方式")
    parser.add_argument("--list", "-l", action="store_true", help="列出最近快照")
    parser.add_argument("--from-conv", "-c", default="", help="从对话文本创建快照")
    args = parser.parse_args()

    if args.list:
        snapshots = list_snapshots(10)
        print(f"最近{len(snapshots)}个快照:")
        for s in snapshots:
            print(f"  {s['snapshot_id']} [{s['trigger']}] {s['instruction'][:50]} (结果{s['results_count']}/认知{s['insights_count']}/错误{s['errors_count']})")
        sys.exit(0)

    if args.from_conv:
        path = create_snapshot_from_conversation(args.from_conv, args.instruction)
        print(f"快照已创建: {path}")
        sys.exit(0)

    key_results = [r.strip() for r in args.results.split(",") if r.strip()] if args.results else None
    key_insights = [i.strip() for i in args.insights.split(",") if i.strip()] if args.insights else None

    path = create_snapshot(
        instruction=args.instruction,
        core_reasoning=args.reasoning,
        key_results=key_results,
        key_insights=key_insights,
        trigger=args.trigger,
    )
    print(f"快照已创建: {path}")
