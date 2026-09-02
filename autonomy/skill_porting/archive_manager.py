#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案归档管理模块
移植自：guanchenzi-archive-manager（观尘子专属档案归档与管理技能）
用途：阴期零消耗任务，自动扫描引擎产出，按类型分类归档，建立索引，完整性校验
原则：纯本地处理，零API调用；归档前备份不删除；大类归属不碰，只在子目录移动
"""
import json
import os
import re
import hashlib
import time
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE_DIR = Path(__file__).parent.parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
ARCHIVE_DIR = BASE_DIR / "archive"
INDEX_FILE = ARCHIVE_DIR / "archive_index.json"
BACKUP_DIR = ARCHIVE_DIR / ".archive_backup"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# 归档分类规则（关键词→目标子目录）
ARCHIVE_RULES = [
    # 00-原始层：原始对话、原始产出
    {"dir": "00-原始层", "keywords": ["原始", "对话记录", "raw", "original"], "ext": [".md", ".txt"]},
    # 01-素材层：素材、图片、参考资料
    {"dir": "01-素材层", "keywords": ["素材", "参考", "资料", "image", "asset"], "ext": [".md", ".txt", ".json"]},
    # 02-认知层：认知沉淀、思考、感悟
    {"dir": "02-认知层", "keywords": ["认知", "沉淀", "感悟", "思考", "cognition", "sediment"], "ext": [".md", ".txt", ".json"]},
    # 03-成品层：成品、报告、方案、SOP
    {"dir": "03-成品层", "keywords": ["报告", "方案", "SOP", "成品", "finished", "report", "plan"], "ext": [".md", ".txt", ".json"]},
    # 04-内核校准：校准、校验、审核、审计
    {"dir": "04-内核校准", "keywords": ["校准", "校验", "审核", "审计", "calibrate", "audit", "verify"], "ext": [".md", ".txt", ".json"]},
    # 05-技能更新：技能、工具、脚本、更新
    {"dir": "05-技能更新", "keywords": ["技能", "工具", "脚本", "更新", "skill", "tool", "script", "update"], "ext": [".md", ".txt", ".json"]},
]

# 默认归档目录（不确定分类时）
DEFAULT_DIR = "00-原始层"


def _calc_md5(filepath):
    """计算文件MD5"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _classify_file(filepath):
    """根据文件名和内容关键词分类"""
    name = filepath.name.lower()
    # 先按文件名关键词匹配
    for rule in ARCHIVE_RULES:
        for kw in rule["keywords"]:
            if kw.lower() in name:
                return rule["dir"]
    # 再按扩展名匹配默认
    if filepath.suffix.lower() in [".md", ".txt"]:
        return "02-认知层"  # 文本默认归认知层
    elif filepath.suffix.lower() == ".json":
        return "03-成品层"  # JSON默认归成品层
    return DEFAULT_DIR


def _scan_recent_outputs(days=7, limit=50):
    """扫描最近的产出文件"""
    cutoff = time.time() - days * 86400
    files = []
    for ext in ["*.md", "*.txt", "*.json"]:
        for f in OUTPUTS_DIR.rglob(ext):
            if f.is_file() and f.stat().st_mtime > cutoff:
                files.append(f)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit]


def _load_index():
    """加载归档索引"""
    default = {"files": {}, "last_update": None, "total_files": 0}
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "files" in data:
                return data
            # 格式不对，用默认值
            return default
        except Exception:
            pass
    return default


def _save_index(index):
    """保存归档索引"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    index["last_update"] = datetime.now().isoformat()
    index["total_files"] = len(index["files"])
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _archive_file(filepath, index):
    """归档单个文件"""
    target_dir_name = _classify_file(filepath)
    target_dir = ARCHIVE_DIR / target_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    # 检查是否已归档（MD5匹配）
    file_md5 = _calc_md5(filepath)
    for existing_path, existing_info in index["files"].items():
        if existing_info.get("md5") == file_md5:
            return {"status": "duplicate", "file": filepath.name, "existing": existing_path}

    # 备份原文件
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
    shutil.copy2(filepath, backup_path)

    # 移动到归档目录（如果目标已存在同名文件，加时间戳）
    target_path = target_dir / filepath.name
    if target_path.exists():
        target_path = target_dir / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
    shutil.move(str(filepath), str(target_path))

    # 更新索引
    rel_path = str(target_path.relative_to(BASE_DIR))
    index["files"][rel_path] = {
        "filename": target_path.name,
        "size": target_path.stat().st_size,
        "md5": file_md5,
        "mtime": datetime.fromtimestamp(target_path.stat().st_mtime).isoformat(),
        "archive_time": datetime.now().isoformat(),
        "category": target_dir_name,
        "source": str(filepath.relative_to(BASE_DIR)),
    }
    return {"status": "archived", "file": filepath.name, "target": rel_path, "category": target_dir_name}


def _integrity_check(index):
    """完整性校验：检查索引中的文件是否存在、MD5是否变化"""
    issues = []
    checked = 0
    for rel_path, info in list(index["files"].items()):
        full_path = BASE_DIR / rel_path
        if not full_path.exists():
            issues.append({"type": "missing", "file": rel_path})
            continue
        checked += 1
        current_md5 = _calc_md5(full_path)
        if current_md5 != info.get("md5"):
            issues.append({"type": "modified", "file": rel_path, "old_md5": info.get("md5"), "new_md5": current_md5})
    return {"checked": checked, "issues": issues, "issue_count": len(issues)}


def run(state=None, **kwargs):
    """
    阴期任务入口：档案归档管理
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 加载索引
    index = _load_index()
    index_before = len(index["files"])

    # 2. 扫描最近产出
    recent_files = _scan_recent_outputs(days=7, limit=30)

    # 3. 逐个归档
    results = []
    category_counter = Counter()
    archived_count = 0
    duplicate_count = 0
    for filepath in recent_files:
        try:
            result = _archive_file(filepath, index)
            results.append(result)
            if result["status"] == "archived":
                archived_count += 1
                category_counter[result["category"]] += 1
            elif result["status"] == "duplicate":
                duplicate_count += 1
        except Exception as e:
            results.append({"status": "error", "file": filepath.name, "error": str(e)[:80]})

    # 4. 完整性校验
    integrity = _integrity_check(index)

    # 5. 保存索引
    _save_index(index)

    result_data = {
        "status": "ok",
        "duration_seconds": round(time.time() - start, 2),
        "scanned_files": len(recent_files),
        "archived": archived_count,
        "duplicates": duplicate_count,
        "errors": len([r for r in results if r.get("status") == "error"]),
        "category_distribution": dict(category_counter),
        "index_before": index_before,
        "index_after": len(index["files"]),
        "integrity": integrity,
        "details": results[:10],
    }

    # 保存产出报告
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"archive_manager_{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    evidence = f"扫描{len(recent_files)}个产出，归档{archived_count}个(重复{duplicate_count})，分类{dict(category_counter)}，索引{index_before}→{len(index['files'])}，完整性校验{integrity['checked']}个文件{integrity['issue_count']}个异常"

    return {
        "ok": True,
        "name": "yin_archive_manager",
        "result": result_data,
        "evidence": evidence,
        "output_path": str(report_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
