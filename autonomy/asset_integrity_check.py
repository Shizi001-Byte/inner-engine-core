#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资产完整性校验 Asset Integrity Check V1.0
功能：每日自动扫描校验资产完整性
- 文件存在性校验：索引中的文件是否都存在
- MD5一致性校验：文件内容是否被篡改
- 孤儿文件检测：存在但未入索引的文件
- 索引一致性：索引条目是否完整
- 关键资产备份检查：核心配置/凭证是否有备份
全程本地计算，零token消耗
"""
import json
import hashlib
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
ARCHIVE_INDEX = DATA_DIR / "archive_index.json"
INTEGRITY_REPORT_DIR = DATA_DIR / "integrity_reports"
BACKUP_DIR = BASE_DIR / "archive"

# 关键资产清单（必须存在且有备份）
CRITICAL_ASSETS = [
    "data/model_credentials.json",
    "data/engine_state.json",
    "data/archive_index.json",
    "data/prediction_rules.json",
    "data/asset_rules.json",
    "autonomy/engine_zhuan1.py",
    "autonomy/prediction_layer.py",
    "autonomy/cognition_density.py",
]


def file_md5(filepath):
    """计算文件MD5"""
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def load_index():
    """加载归档索引"""
    if ARCHIVE_INDEX.exists():
        with open(ARCHIVE_INDEX) as f:
            return json.load(f)
    return {}


def check_integrity():
    """执行完整性校验"""
    index = load_index()
    issues = []
    stats = {
        "index_total": len(index),
        "files_exist": 0,
        "files_missing": 0,
        "md5_match": 0,
        "md5_mismatch": 0,
        "orphan_files": 0,
        "critical_ok": 0,
        "critical_missing": 0,
    }

    # ============================================================
    # 1. 文件存在性 + MD5一致性校验
    # ============================================================
    indexed_paths = set()
    for task_id, entry in index.items():
        rel_path = entry.get("path", "")
        indexed_paths.add(rel_path)
        full_path = BASE_DIR / rel_path

        if not full_path.exists():
            stats["files_missing"] += 1
            issues.append({
                "type": "missing_file",
                "severity": "high",
                "task_id": task_id,
                "path": rel_path,
                "message": f"索引中的文件不存在: {rel_path}",
            })
            continue

        stats["files_exist"] += 1

        # MD5校验
        indexed_md5 = entry.get("md5", "")
        if indexed_md5:
            actual_md5 = file_md5(full_path)
            if actual_md5 and actual_md5 == indexed_md5:
                stats["md5_match"] += 1
            else:
                stats["md5_mismatch"] += 1
                issues.append({
                    "type": "md5_mismatch",
                    "severity": "medium",
                    "task_id": task_id,
                    "path": rel_path,
                    "indexed_md5": indexed_md5,
                    "actual_md5": actual_md5,
                    "message": f"文件MD5不匹配（可能被修改）: {rel_path}",
                })

    # ============================================================
    # 2. 孤儿文件检测（认知目录中存在但未入索引的文件）
    # ============================================================
    cognition_dir = BASE_DIR / "cognition"
    if cognition_dir.exists():
        for root, _, files in os.walk(cognition_dir):
            for fname in files:
                if fname.startswith("."):
                    continue
                full_path = Path(root) / fname
                rel_path = str(full_path.relative_to(BASE_DIR))
                if rel_path not in indexed_paths:
                    stats["orphan_files"] += 1
                    issues.append({
                        "type": "orphan_file",
                        "severity": "low",
                        "path": rel_path,
                        "message": f"认知文件未入归档索引: {rel_path}",
                    })

    # ============================================================
    # 3. 关键资产检查
    # ============================================================
    for rel_path in CRITICAL_ASSETS:
        full_path = BASE_DIR / rel_path
        if full_path.exists():
            stats["critical_ok"] += 1
            # 检查是否有备份（archive目录下）
            backup_path = BACKUP_DIR / "03-成品层" / Path(rel_path).name
            if not backup_path.exists():
                issues.append({
                    "type": "no_backup",
                    "severity": "medium",
                    "path": rel_path,
                    "message": f"关键资产无备份: {rel_path}",
                })
        else:
            stats["critical_missing"] += 1
            issues.append({
                "type": "critical_missing",
                "severity": "critical",
                "path": rel_path,
                "message": f"关键资产丢失: {rel_path}",
            })

    # ============================================================
    # 4. 索引条目完整性
    # ============================================================
    required_fields = ["task_type", "path", "md5", "size", "archived_at"]
    for task_id, entry in index.items():
        missing = [f for f in required_fields if f not in entry]
        if missing:
            issues.append({
                "type": "index_incomplete",
                "severity": "low",
                "task_id": task_id,
                "missing_fields": missing,
                "message": f"索引条目缺少字段: {task_id} 缺{missing}",
            })

    # ============================================================
    # 生成报告
    # ============================================================
    severity_counts = defaultdict(int)
    for issue in issues:
        severity_counts[issue["severity"]] += 1

    report = {
        "check_time": datetime.now().isoformat(),
        "stats": stats,
        "severity_summary": dict(severity_counts),
        "issues": issues,
        "overall_status": "healthy" if severity_counts.get("critical", 0) == 0 and severity_counts.get("high", 0) == 0 else "warning",
    }

    # 保存报告
    INTEGRITY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = INTEGRITY_REPORT_DIR / f"integrity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    report["report_path"] = str(report_path)

    return report


def print_report(report):
    """打印可读报告"""
    print("=" * 60)
    print(f"资产完整性校验报告 | {report['check_time']}")
    print(f"整体状态: {report['overall_status'].upper()}")
    print("=" * 60)

    s = report["stats"]
    print(f"\n【统计概览】")
    print(f"  索引条目: {s['index_total']}")
    print(f"  文件存在: {s['files_exist']} / 丢失: {s['files_missing']}")
    print(f"  MD5一致: {s['md5_match']} / 不匹配: {s['md5_mismatch']}")
    print(f"  孤儿文件: {s['orphan_files']}")
    print(f"  关键资产: {s['critical_ok']}正常 / {s['critical_missing']}丢失")

    print(f"\n【问题分级】")
    for sev, count in report["severity_summary"].items():
        print(f"  {sev.upper()}: {count}")

    if report["issues"]:
        print(f"\n【问题详情】")
        for issue in report["issues"][:15]:
            print(f"  [{issue['severity'].upper()}] {issue['type']}: {issue['message']}")
        if len(report["issues"]) > 15:
            print(f"  ... 还有{len(report['issues']) - 15}条问题")

    print(f"\n报告已保存: {report.get('report_path', 'N/A')}")
    print("=" * 60)


if __name__ == "__main__":
    report = check_integrity()
    print_report(report)
