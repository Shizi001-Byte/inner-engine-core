#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆融合任务 Memory Fusion Task
第一层核心记忆闭环 - 阴期零消耗任务
功能：扫描阳期运行快照，提取关键记忆，与核心记忆体对比融合去重，更新权重，回灌state
原则：增量处理快照，不重复全量扫描；去重基于核心语句相似度；融合日志可追溯
"""
import json
import re
import os
import time
import hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE_DIR = Path(__file__).parent.parent.parent
SNAPSHOTS_DIR = BASE_DIR / "data" / "snapshots"
CORE_MEMORY_FILE = BASE_DIR / "data" / "core_memory.json"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
FUSION_LOG = BASE_DIR / "data" / "fusion_log.json"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# 导入核心记忆体构建器
import sys
sys.path.insert(0, str(Path(__file__).parent))
from core_memory_build import build_core_memory, _inject_to_state


def _load_core_memory():
    """加载核心记忆体"""
    if CORE_MEMORY_FILE.exists():
        try:
            with open(CORE_MEMORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _load_fusion_log():
    """加载融合日志"""
    if FUSION_LOG.exists():
        try:
            with open(FUSION_LOG, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_fusion": None, "fusion_count": 0, "processed_snapshots": [], "history": []}


def _save_fusion_log(log):
    """保存融合日志"""
    with open(FUSION_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _scan_snapshots():
    """扫描阳期运行快照"""
    if not SNAPSHOTS_DIR.exists():
        return []
    snapshots = []
    for f in SNAPSHOTS_DIR.glob("snapshot_*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            data["_file"] = f.name
            data["_path"] = str(f)
            data["_mtime"] = f.stat().st_mtime
            snapshots.append(data)
        except Exception:
            pass
    snapshots.sort(key=lambda x: x.get("_mtime", 0))
    return snapshots


def _extract_memory_from_snapshot(snapshot):
    """从快照中提取关键记忆条目"""
    memories = []
    # 提取关键错误/坑
    errors = snapshot.get("errors", [])
    if isinstance(errors, list):
        for err in errors[:5]:
            if isinstance(err, dict):
                memories.append({
                    "type": "pit_candidate",
                    "title": err.get("message", str(err))[:80],
                    "detail": json.dumps(err, ensure_ascii=False)[:200],
                    "source": snapshot.get("snapshot_id", "unknown"),
                })
    # 提取关键认知
    key_insights = snapshot.get("key_insights", [])
    if isinstance(key_insights, list):
        for insight in key_insights[:5]:
            if isinstance(insight, str) and len(insight) > 10:
                memories.append({
                    "type": "cognition_candidate",
                    "core_statement": insight[:120],
                    "source": snapshot.get("snapshot_id", "unknown"),
                })
    # 提取关键结果
    key_results = snapshot.get("key_results", [])
    if isinstance(key_results, list):
        for result in key_results[:3]:
            if isinstance(result, str) and len(result) > 10:
                memories.append({
                    "type": "result_record",
                    "content": result[:120],
                    "source": snapshot.get("snapshot_id", "unknown"),
                })
    return memories


def _deduplicate(new_memories, core_memory):
    """与核心记忆体去重（基于核心语句简单匹配）"""
    if not core_memory:
        return new_memories, 0
    # 收集现有认知的核心语句
    existing_statements = set()
    for entry in core_memory.get("categories", {}).get("cognition", {}).get("entries", {}).values():
        stmt = entry.get("core_statement", "")
        if stmt:
            existing_statements.add(stmt[:50])
    for entry in core_memory.get("categories", {}).get("pits", {}).get("entries", {}).values():
        name = entry.get("name", "")
        if name:
            existing_statements.add(name[:50])

    unique = []
    dup_count = 0
    for mem in new_memories:
        key = ""
        if mem["type"] == "cognition_candidate":
            key = mem.get("core_statement", "")[:50]
        elif mem["type"] == "pit_candidate":
            key = mem.get("title", "")[:50]
        else:
            key = mem.get("content", "")[:50]
        if key and key in existing_statements:
            dup_count += 1
        else:
            unique.append(mem)
            existing_statements.add(key)
    return unique, dup_count


def run(state=None, **kwargs):
    """阴期任务入口：记忆融合"""
    start = time.time()

    # 1. 加载核心记忆体和融合日志
    core_memory = _load_core_memory()
    fusion_log = _load_fusion_log()
    processed = set(fusion_log.get("processed_snapshots", []))

    # 2. 扫描快照
    snapshots = _scan_snapshots()
    new_snapshots = [s for s in snapshots if s.get("_file") not in processed]

    if not new_snapshots and core_memory:
        # 没有新快照，但核心记忆体存在，检查是否需要重建
        # 如果核心记忆体超过24小时没更新，重建一次
        built_at = core_memory.get("built_at", "")
        need_rebuild = True
        if built_at:
            try:
                build_time = datetime.fromisoformat(built_at)
                if (datetime.now() - build_time).total_seconds() < 86400:
                    need_rebuild = False
            except Exception:
                pass
        if not need_rebuild:
            return {
                "ok": True,
                "name": "yin_memory_fusion",
                "result": {"status": "skipped", "reason": "no new snapshots, core memory fresh"},
                "evidence": "无新快照，核心记忆体在24小时内，跳过融合",
            }

    # 3. 处理新快照，提取记忆
    all_new_memories = []
    snapshot_summary = []
    for snap in new_snapshots:
        memories = _extract_memory_from_snapshot(snap)
        all_new_memories.extend(memories)
        snapshot_summary.append({
            "file": snap.get("_file"),
            "memories_extracted": len(memories),
            "snapshot_id": snap.get("snapshot_id", "unknown"),
        })
        processed.add(snap.get("_file"))

    # 4. 去重
    unique_memories, dup_count = _deduplicate(all_new_memories, core_memory)

    # 5. 重建核心记忆体（全量重建，包含新的记忆）
    # 注意：新提取的记忆目前不会自动写入认知池/坑库，
    # 而是记录在融合日志中，阳期可以人工确认后写入
    new_core_memory = build_core_memory()

    # 6. 回灌state
    inject_result = _inject_to_state(new_core_memory)

    # 7. 更新融合日志
    fusion_log["last_fusion"] = datetime.now().isoformat()
    fusion_log["fusion_count"] = fusion_log.get("fusion_count", 0) + 1
    fusion_log["processed_snapshots"] = list(processed)[-200:]  # 只保留最近200个
    fusion_entry = {
        "time": datetime.now().isoformat(),
        "new_snapshots": len(new_snapshots),
        "memories_extracted": len(all_new_memories),
        "unique_memories": len(unique_memories),
        "duplicates": dup_count,
        "snapshot_summary": snapshot_summary,
        "pending_memories": unique_memories[:20],  # 待阳期确认的记忆
    }
    fusion_log.setdefault("history", []).append(fusion_entry)
    fusion_log["history"] = fusion_log["history"][-50:]  # 只保留最近50次
    _save_fusion_log(fusion_log)

    result = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "new_snapshots_processed": len(new_snapshots),
        "memories_extracted": len(all_new_memories),
        "unique_memories": len(unique_memories),
        "duplicates_filtered": dup_count,
        "core_memory_total": new_core_memory["stats"]["total_entries"],
        "fusion_count": fusion_log["fusion_count"],
        "pending_confirmation": len(unique_memories),
    }

    evidence = f"记忆融合完成：处理{len(new_snapshots)}个新快照，提取{len(all_new_memories)}条记忆，去重{dup_count}条，新增{len(unique_memories)}条待确认，核心记忆体共{new_core_memory['stats']['total_entries']}条，回灌state={'成功' if inject_result is True else inject_result}"

    # 保存产出报告
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"memory_fusion_{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "name": "yin_memory_fusion",
        "result": result,
        "evidence": evidence,
        "output_path": str(report_path),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
