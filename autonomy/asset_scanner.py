#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资产扫描器 Asset Scanner V1.0
功能：扫描工程/认知/内容目录，提取每个资产的元数据（修改时间、大小、调用次数、报错记录等）
输出：asset_db.json 资产数据库
全程本地计算，零token消耗
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


def scan_engineering_assets(rules):
    """扫描工程类资产：脚本、配置、引擎模块"""
    assets = []
    eng_rules = rules.get("asset_types", {}).get("engineering", {})
    dirs = eng_rules.get("dirs", ["autonomy", "data", "scripts"])
    extensions = set(eng_rules.get("extensions", [".py", ".sh", ".json"]))

    # 从日志中提取调用/报错统计
    call_stats, error_stats = _parse_engine_log()

    for dirname in dirs:
        dirpath = BASE_DIR / dirname
        if not dirpath.exists():
            continue
        for root, _, files in os.walk(dirpath):
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix not in extensions:
                    continue
                meta = get_file_metadata(fpath)
                if not meta:
                    continue
                rel_path = meta["path"]
                # 调用次数：从日志中匹配文件名
                calls_30d = call_stats.get(rel_path, 0) + call_stats.get(fname, 0)
                errors_30d = error_stats.get(rel_path, 0) + error_stats.get(fname, 0)
                error_rate = errors_30d / max(1, calls_30d) if calls_30d > 0 else 0

                meta.update({
                    "asset_type": "engineering",
                    "calls_30d": calls_30d,
                    "errors_30d": errors_30d,
                    "error_rate": round(error_rate, 3),
                    "complexity_score": min(100, meta["line_count"] / 5),  # 行数估算复杂度
                })
                assets.append(meta)
    return assets


def scan_cognition_assets(rules):
    """扫描认知类资产：认知沉淀、认知池、坑库"""
    assets = []
    cog_rules = rules.get("asset_types", {}).get("cognition", {})
    dirs = cog_rules.get("dirs", ["cognition", "cognition_pool", "data/pit_library"])

    for dirname in dirs:
        dirpath = BASE_DIR / dirname
        if not dirpath.exists():
            continue
        for root, _, files in os.walk(dirpath):
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix not in (".md", ".json"):
                    continue
                meta = get_file_metadata(fpath)
                if not meta:
                    continue
                # 认知密度：从文件名或内容中提取
                density = _extract_cognition_density(fpath)
                # 应用次数：被引擎引用的次数（从日志匹配）
                applications = _count_cognition_applications(fname)

                meta.update({
                    "asset_type": "cognition",
                    "density": density,
                    "density_grade": _grade_density(density),
                    "application_count": applications,
                    "is_pit": "pit_library" in str(fpath),
                })
                assets.append(meta)
    return assets


def _parse_engine_log():
    """从引擎日志中提取调用和报错统计"""
    call_stats = defaultdict(int)
    error_stats = defaultdict(int)
    if not ENGINE_LOG.exists():
        return call_stats, error_stats

    # 只看最近30天的日志（实际日志可能没那么长，全量扫描）
    try:
        with open(ENGINE_LOG, "r", errors="ignore") as f:
            for line in f:
                # P1-6修复：只统计实际任务执行行([OK]/[Worker]/[GOAL])，排除import/堆栈/日志提及
                is_task_line = any(tag in line for tag in ["[OK]", "[Worker]", "[GOAL]", "[修炼]"])
                if is_task_line:
                    for pattern in [r"(\w+\.py)", r"(\w+\.json)", r"(\w+\.sh)"]:
                        matches = re.findall(pattern, line)
                        for m in matches:
                            # 排除系统/库文件名
                            if m not in ("json.py", "re.py", "os.py", "sys.py", "time.py"):
                                call_stats[m] += 1
                # 报错记录：只统计明确的ERROR行
                if "[ERROR]" in line or "Traceback" in line:
                    for pattern in [r"(\w+\.py)", r"(\w+\.json)"]:
                        matches = re.findall(pattern, line)
                        for m in matches:
                            error_stats[m] += 1
    except Exception:
        pass
    return call_stats, error_stats


def _extract_cognition_density(filepath):
    """从认知文件中提取密度值"""
    try:
        if filepath.suffix == ".json":
            with open(filepath) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("density", data.get("avg_density", 0))
            elif isinstance(data, list) and data:
                return data[0].get("density", 0)
        elif filepath.suffix == ".md":
            # 从markdown中尝试提取密度关键词
            with open(filepath, "r", errors="ignore") as f:
                content = f.read()
            # 匹配 "密度: 0.xx" 或 "均密0.xx"
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


def _count_cognition_applications(filename):
    """统计认知被引擎应用的次数（从日志匹配文件名/关键词）"""
    count = 0
    if not ENGINE_LOG.exists():
        return count
    try:
        keyword = filename.replace(".md", "").replace(".json", "")[:20]
        with open(ENGINE_LOG, "r", errors="ignore") as f:
            for line in f:
                if keyword in line and ("蒸馏" in line or "认知" in line or "通神" in line):
                    count += 1
    except Exception:
        pass
    return count


def scan_all_assets():
    """全量扫描所有资产"""
    rules = load_rules()
    all_assets = []

    # 工程类
    eng_assets = scan_engineering_assets(rules)
    all_assets.extend(eng_assets)

    # 认知类
    cog_assets = scan_cognition_assets(rules)
    all_assets.extend(cog_assets)

    # 内容类（暂不启用）
    content_rules = rules.get("asset_types", {}).get("content", {})
    if content_rules.get("enabled", False):
        # 内容类扫描留待二级落地
        pass

    # 构建资产数据库
    db = {
        "scanned_at": datetime.now().isoformat(),
        "total_assets": len(all_assets),
        "engineering_count": len(eng_assets),
        "cognition_count": len(cog_assets),
        "assets": all_assets,
    }

    # 保存
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ASSET_DB, "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    return db


def get_asset_db():
    """获取资产数据库"""
    if ASSET_DB.exists():
        with open(ASSET_DB) as f:
            return json.load(f)
    return scan_all_assets()


if __name__ == "__main__":
    print("=" * 50)
    print("资产扫描器 V1.0")
    print("=" * 50)
    db = scan_all_assets()
    print(f"\n扫描完成:")
    print(f"  总资产数: {db['total_assets']}")
    print(f"  工程类: {db['engineering_count']}")
    print(f"  认知类: {db['cognition_count']}")
    print(f"  数据库: {ASSET_DB}")

    # 打印Top10工程资产（按调用次数）
    eng = sorted([a for a in db["assets"] if a["asset_type"] == "engineering"],
                 key=lambda x: x["calls_30d"], reverse=True)
    print(f"\n工程类Top5（按调用次数）:")
    for a in eng[:5]:
        print(f"  {a['path']}: {a['calls_30d']}次调用, {a['errors_30d']}次报错, {a['days_since_modified']}天前修改")

    # 打印认知类分级统计
    cog = [a for a in db["assets"] if a["asset_type"] == "cognition"]
    grades = defaultdict(int)
    for a in cog:
        grades[a["density_grade"]] += 1
    print(f"\n认知类密度分级:")
    for grade in ["S", "A", "B", "C"]:
        print(f"  {grade}级: {grades.get(grade, 0)}条")
