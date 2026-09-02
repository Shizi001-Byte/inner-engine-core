#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资产扫描器 Asset Scanner V1.1
功能：扫描工程/认知/内容目录，提取每个资产的元数据（修改时间、大小、调用次数、报错记录等）
输出：asset_db.json 资产数据库
全程本地计算，零token消耗

V1.1优化（2026-08-24）：
1. 日志只读一次，批量在内存中搜索所有认知关键词（之前每个文件打开一次日志，2773次全量读取导致卡死）
2. 分批增量扫描：每次默认扫500个文件，记录进度到asset_db.scan_progress，下次继续
3. 保留scan_all_assets()全量接口兼容旧调用，内部循环调用分批版本直到完成
"""
import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
ASSET_DB = DATA_DIR / "asset_db.json"
RULES_CONFIG = DATA_DIR / "asset_rules.json"
ENGINE_LOG = BASE_DIR / "logs" / "daemon_zhuan1_stdout.log"

DEFAULT_BATCH_SIZE = 500


def load_rules():
    if RULES_CONFIG.exists():
        with open(RULES_CONFIG) as f:
            return json.load(f)
    return {}


def get_file_metadata(filepath):
    """提取文件基础元数据"""
    try:
        stat = filepath.stat()
        return {
            "path": str(filepath.relative_to(BASE_DIR)),
            "name": filepath.name,
            "suffix": filepath.suffix,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "days_since_modified": (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
            "line_count": _count_lines(filepath),
        }
    except Exception:
        return None


def _count_lines(filepath):
    """统计文件行数（工程类复杂度指标）"""
    try:
        with open(filepath, "r", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _collect_all_files(rules):
    """收集所有待扫描文件，返回[(asset_type, filepath), ...]列表"""
    files = []
    # 工程类
    eng_rules = rules.get("asset_types", {}).get("engineering", {})
    dirs = eng_rules.get("dirs", ["autonomy", "data", "scripts"])
    extensions = set(eng_rules.get("extensions", [".py", ".sh", ".json"]))
    for dirname in dirs:
        dirpath = BASE_DIR / dirname
        if not dirpath.exists():
            continue
        for root, _, fnames in os.walk(dirpath):
            for fname in fnames:
                fpath = Path(root) / fname
                if fpath.suffix in extensions:
                    files.append(("engineering", fpath))
    # 认知类
    cog_rules = rules.get("asset_types", {}).get("cognition", {})
    dirs = cog_rules.get("dirs", ["cognition", "cognition_pool", "data/pit_library"])
    for dirname in dirs:
        dirpath = BASE_DIR / dirname
        if not dirpath.exists():
            continue
        for root, _, fnames in os.walk(dirpath):
            for fname in fnames:
                fpath = Path(root) / fname
                if fpath.suffix in (".md", ".json"):
                    files.append(("cognition", fpath))
    return files


def _parse_engine_log():
    """从引擎日志中提取调用和报错统计（只读一次）"""
    call_stats = defaultdict(int)
    error_stats = defaultdict(int)
    if not ENGINE_LOG.exists():
        return call_stats, error_stats, ""
    log_content = ""
    try:
        with open(ENGINE_LOG, "r", errors="ignore") as f:
            log_content = f.read()
        for line in log_content.split("\n"):
            is_task_line = any(tag in line for tag in ["[OK]", "[Worker]", "[GOAL]", "[修炼]"])
            if is_task_line:
                for pattern in [r"(\w+\.py)", r"(\w+\.json)", r"(\w+\.sh)"]:
                    matches = re.findall(pattern, line)
                    for m in matches:
                        if m not in ("json.py", "re.py", "os.py", "sys.py", "time.py"):
                            call_stats[m] += 1
            if "[ERROR]" in line or "Traceback" in line:
                for pattern in [r"(\w+\.py)", r"(\w+\.json)"]:
                    matches = re.findall(pattern, line)
                    for m in matches:
                        error_stats[m] += 1
    except Exception:
        pass
    return call_stats, error_stats, log_content


def _count_cognition_applications_batch(filenames, log_content):
    """批量统计认知被引擎应用的次数（日志已读入内存，避免重复打开）"""
    results = {}
    if not log_content:
        return {f: 0 for f in filenames}
    lines = log_content.split("\n")
    for filename in filenames:
        keyword = filename.replace(".md", "").replace(".json", "")[:20]
        count = 0
        for line in lines:
            if keyword in line and ("蒸馏" in line or "认知" in line or "通神" in line):
                count += 1
        results[filename] = count
    return results


def _normalize_density(val):
    """PIT-083修复：将density字段统一转为float。"""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        info = val.get("info_density")
        if isinstance(info, (int, float)):
            return float(info)
        vals = [v for k, v in val.items() if isinstance(v, (int, float)) and "density" in k.lower()]
        if vals:
            return sum(vals) / len(vals)
        return 0.0
    return 0.0


def _extract_cognition_density(filepath):
    """从认知文件中提取密度值"""
    try:
        if filepath.suffix == ".json":
            with open(filepath) as f:
                data = json.load(f)
            if isinstance(data, dict):
                raw = data.get("density", data.get("avg_density", 0))
                return _normalize_density(raw)
            elif isinstance(data, list) and data:
                raw = data[0].get("density", 0)
                return _normalize_density(raw)
        elif filepath.suffix == ".md":
            with open(filepath, "r", errors="ignore") as f:
                content = f.read()
            m = re.search(r"(?:密度|均密)[^\d]*(\d+\.?\d*)", content)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return 0.0


def _grade_density(density):
    """密度分级"""
    if density >= 0.7:
        return "S"
    elif density >= 0.5:
        return "A"
    elif density >= 0.3:
        return "B"
    else:
        return "C"


def scan_all_assets_batch(batch_size=DEFAULT_BATCH_SIZE):
    """分批增量扫描：每次扫batch_size个文件，记录进度，下次继续。

    返回asset_db，其中scan_progress字段记录进度：
      phase: "scanning" | "done"
      file_index: 已扫描到的文件索引
      total_files: 文件总数
      batch_size: 每批数量
    """
    rules = load_rules()

    # 加载已有数据库和进度
    existing_assets = {}
    progress = {
        "phase": "scanning",
        "file_index": 0,
        "total_files": 0,
        "batch_size": batch_size,
    }
    if ASSET_DB.exists():
        try:
            with open(ASSET_DB) as f:
                old_db = json.load(f)
            for a in old_db.get("assets", []):
                existing_assets[a["path"]] = a
            old_progress = old_db.get("scan_progress", {})
            progress.update(old_progress)
        except Exception:
            pass

    # 收集所有文件
    all_files = _collect_all_files(rules)
    progress["total_files"] = len(all_files)

    # 如果上一轮已完成，重新开始新一轮（清空旧数据）
    if progress.get("phase") == "done" or progress.get("file_index", 0) >= len(all_files):
        existing_assets = {}
        progress["file_index"] = 0
        progress["phase"] = "scanning"

    # 确定本次扫描范围
    start_idx = progress.get("file_index", 0)
    end_idx = min(start_idx + batch_size, len(all_files))

    # 日志只读一次（核心优化：之前每个认知文件都打开一次日志）
    call_stats, error_stats, log_content = _parse_engine_log()

    # 预提取本批认知文件名，批量统计应用次数
    cog_filenames_in_batch = [fpath.name for atype, fpath in all_files[start_idx:end_idx] if atype == "cognition"]
    cog_app_counts = _count_cognition_applications_batch(cog_filenames_in_batch, log_content)

    # 扫描本批文件
    for i in range(start_idx, end_idx):
        asset_type, fpath = all_files[i]
        meta = get_file_metadata(fpath)
        if not meta:
            continue
        if asset_type == "engineering":
            rel_path = meta["path"]
            calls_30d = call_stats.get(rel_path, 0) + call_stats.get(fpath.name, 0)
            errors_30d = error_stats.get(rel_path, 0) + error_stats.get(fpath.name, 0)
            error_rate = errors_30d / max(1, calls_30d) if calls_30d > 0 else 0
            meta.update({
                "asset_type": "engineering",
                "calls_30d": calls_30d,
                "errors_30d": errors_30d,
                "error_rate": round(error_rate, 3),
                "complexity_score": min(100, meta["line_count"] / 5),
            })
        else:  # cognition
            density = _extract_cognition_density(fpath)
            applications = cog_app_counts.get(fpath.name, 0)
            meta.update({
                "asset_type": "cognition",
                "density": density,
                "density_grade": _grade_density(density),
                "application_count": applications,
                "is_pit": "pit_library" in str(fpath),
            })
        existing_assets[meta["path"]] = meta

    # 更新进度
    progress["file_index"] = end_idx
    progress["last_batch_at"] = datetime.now().isoformat()
    if end_idx >= len(all_files):
        progress["phase"] = "done"
    else:
        progress["phase"] = "scanning"

    # 构建数据库
    all_assets = list(existing_assets.values())
    eng_count = sum(1 for a in all_assets if a.get("asset_type") == "engineering")
    cog_count = sum(1 for a in all_assets if a.get("asset_type") == "cognition")

    db = {
        "scanned_at": datetime.now().isoformat(),
        "total_assets": len(all_assets),
        "engineering_count": eng_count,
        "cognition_count": cog_count,
        "scan_progress": progress,
        "assets": all_assets,
    }

    # 保存
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ASSET_DB, "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    return db


def scan_all_assets():
    """全量扫描所有资产（兼容旧调用）：内部循环调用分批版本直到完成"""
    while True:
        db = scan_all_assets_batch(DEFAULT_BATCH_SIZE)
        if db.get("scan_progress", {}).get("phase") == "done":
            return db


def get_asset_db():
    """获取资产数据库"""
    if ASSET_DB.exists():
        with open(ASSET_DB) as f:
            return json.load(f)
    return scan_all_assets()


if __name__ == "__main__":
    print("=" * 50)
    print("资产扫描器 V1.1（分批增量模式）")
    print("=" * 50)
    db = scan_all_assets_batch()
    prog = db.get("scan_progress", {})
    print(f"\n本批扫描完成:")
    print(f"  进度: {prog.get('file_index', 0)}/{prog.get('total_files', 0)}")
    print(f"  阶段: {prog.get('phase')}")
    print(f"  总资产数: {db['total_assets']}")
    print(f"  工程类: {db['engineering_count']}")
    print(f"  认知类: {db['cognition_count']}")
    print(f"  数据库: {ASSET_DB}")
    if prog.get("phase") != "done":
        print(f"\n  未完成，下次调用继续从索引{prog.get('file_index')}开始")
