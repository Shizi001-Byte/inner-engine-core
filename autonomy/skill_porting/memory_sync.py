#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆同步与完整性校验模块
移植自：guanchenzi-memory-sync（观尘子专属记忆同步与档案完整性校验技能）
用途：阴期零消耗任务，只读校验核心文档完整性、归档同步状态、变化检测，生成告警报告
原则：纯只读操作，不修改任何文件；发现问题只报告不自动处理；核心文档异常立即告警
"""
import json
import os
import re
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

BASE_DIR = Path(__file__).parent.parent.parent
ARCHIVE_DIR = BASE_DIR / "archive"
ARCHIVE_INDEX = ARCHIVE_DIR / "archive_index.json"
COGNITION_DIR = BASE_DIR / "cognition"
OUTPUTS_DIR = BASE_DIR / "outputs"
DATA_DIR = BASE_DIR / "data"
ANCHORS_DIR = BASE_DIR / "anchors"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"
SYNC_REPORT_DIR = BASE_DIR / "data" / "integrity_reports"

# 核心文档目录（需要严格校验的）
CORE_DIRS = [
    {"path": "anchors", "name": "锚点目录", "critical": True},
    {"path": "cognition", "name": "认知文档", "critical": False},
    {"path": "data/engine_state.json", "name": "引擎状态文件", "critical": True},
    {"path": "data/pit_library", "name": "坑库", "critical": True},
    {"path": "autonomy/engine_zhuan1.py", "name": "引擎主脚本", "critical": True},
]

# 告警等级
ALERT_CRITICAL = "🔴严重"
ALERT_WARNING = "🟡警告"
ALERT_INFO = "🟢提示"


def _calc_md5(filepath):
    """计算文件MD5"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_archive_index():
    """加载归档索引"""
    if ARCHIVE_INDEX.exists():
        try:
            with open(ARCHIVE_INDEX, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "files" in data:
                return data
        except Exception:
            pass
    return {"files": {}}


def _load_last_sync_report():
    """加载上次同步报告（用于变化检测）"""
    if not SYNC_REPORT_DIR.exists():
        return None
    reports = sorted(SYNC_REPORT_DIR.glob("sync_report_*.json"))
    if not reports:
        return None
    try:
        with open(reports[-1], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _check_core_docs():
    """核心文档完整性校验"""
    issues = []
    checked = 0
    core_snapshot = {}
    for core in CORE_DIRS:
        path = BASE_DIR / core["path"]
        if path.is_file():
            checked += 1
            if not path.exists():
                issues.append({"level": ALERT_CRITICAL, "type": "核心文档缺失", "target": core["name"], "path": str(path)})
            else:
                core_snapshot[str(path)] = {
                    "name": core["name"],
                    "md5": _calc_md5(path),
                    "size": path.stat().st_size,
                    "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                }
        elif path.is_dir():
            if not path.exists():
                issues.append({"level": ALERT_CRITICAL, "type": "核心目录缺失", "target": core["name"], "path": str(path)})
            else:
                file_count = 0
                for f in path.rglob("*"):
                    if f.is_file():
                        file_count += 1
                        rel = str(f.relative_to(BASE_DIR))
                        core_snapshot[rel] = {
                            "name": f"{core['name']}/{f.name}",
                            "md5": _calc_md5(f),
                            "size": f.stat().st_size,
                        }
                checked += file_count
    return {"checked": checked, "issues": issues, "snapshot": core_snapshot}


def _check_archive_sync(days=7, limit=50):
    """归档同步检查：最近产出是否都已归档"""
    cutoff = time.time() - days * 86400
    archive_index = _load_archive_index()
    archived_md5s = {info.get("md5") for info in archive_index.get("files", {}).values()}

    # 收集最近的产出文件，按修改时间排序，取最新的limit个
    all_recent = []
    for ext in ["*.md", "*.txt", "*.json"]:
        for f in OUTPUTS_DIR.rglob(ext):
            if f.is_file() and f.stat().st_mtime > cutoff:
                all_recent.append(f)
    all_recent.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    recent_files = all_recent[:limit]

    unarchived = []
    for f in recent_files:
        file_md5 = _calc_md5(f)
        if file_md5 not in archived_md5s:
            unarchived.append({"file": f.name, "path": str(f.relative_to(BASE_DIR)), "md5": file_md5})

    return {
        "recent_count": len(recent_files),
        "scanned_total": len(all_recent),
        "archived_count": len(recent_files) - len(unarchived),
        "unarchived_count": len(unarchived),
        "unarchived_list": unarchived[:10],
        "sync_rate": round((len(recent_files) - len(unarchived)) / len(recent_files) * 100, 1) if recent_files else 100,
    }


def _detect_changes(current_snapshot, last_report):
    """变化检测：与上次报告对比"""
    if not last_report or "core_snapshot" not in last_report:
        return {"status": "skipped", "reason": "无上次报告，首次运行"}
    last_snapshot = last_report["core_snapshot"]
    changes = {"added": [], "removed": [], "modified": []}
    # 新增
    for path in current_snapshot:
        if path not in last_snapshot:
            changes["added"].append(path)
    # 删除
    for path in last_snapshot:
        if path not in current_snapshot:
            changes["removed"].append(path)
    # 修改
    for path in current_snapshot:
        if path in last_snapshot:
            if current_snapshot[path].get("md5") != last_snapshot[path].get("md5"):
                changes["modified"].append(path)
    return changes


def run(state=None, **kwargs):
    """
    阴期任务入口：记忆同步与完整性校验
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    SYNC_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 核心文档校验
    core_check = _check_core_docs()

    # 2. 归档同步检查
    archive_sync = _check_archive_sync(days=7)

    # 3. 变化检测
    last_report = _load_last_sync_report()
    changes = _detect_changes(core_check["snapshot"], last_report)

    # 4. 汇总告警
    all_issues = core_check["issues"]
    if archive_sync["unarchived_count"] > 0:
        all_issues.append({"level": ALERT_INFO, "type": "产出未归档", "count": archive_sync["unarchived_count"]})
    if changes.get("removed"):
        all_issues.append({"level": ALERT_WARNING, "type": "文件被删除", "count": len(changes["removed"]), "files": changes["removed"][:5]})
    if changes.get("modified"):
        all_issues.append({"level": ALERT_INFO, "type": "文件被修改", "count": len(changes["modified"]), "files": changes["modified"][:5]})

    critical_count = len([i for i in all_issues if i["level"] == ALERT_CRITICAL])
    warning_count = len([i for i in all_issues if i["level"] == ALERT_WARNING])
    info_count = len([i for i in all_issues if i["level"] == ALERT_INFO])

    result = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "core_docs_checked": core_check["checked"],
        "archive_sync": archive_sync,
        "changes": changes,
        "alerts": {
            "critical": critical_count,
            "warning": warning_count,
            "info": info_count,
            "total": len(all_issues),
        },
        "issues": all_issues[:10],
        "core_snapshot": core_check["snapshot"],
    }

    # 保存报告
    report_path = SYNC_REPORT_DIR / f"sync_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 同时保存到yin_period产出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"memory_sync_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    evidence = f"核心文档校验{core_check['checked']}个，归档同步率{archive_sync['sync_rate']}%({archive_sync['unarchived_count']}个未归档)，告警{critical_count}严重/{warning_count}警告/{info_count}提示"

    return {
        "ok": critical_count == 0,
        "name": "yin_memory_sync",
        "result": result,
        "evidence": evidence,
        "output_path": str(output_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
