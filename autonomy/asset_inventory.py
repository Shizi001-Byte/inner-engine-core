#!/usr/bin/env python3
"""
全域资产大盘点脚本 UAI-v1.0
自动扫描本地核心目录，识别六大类资产，生成统一资产清单
对应通神维基建：给所有分散资产装一个全局目录
"""
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

WORKSPACE = Path("/home/user/.super_doubao/super-doubao-runtime/workspace")
OUTPUT = WORKSPACE / "engine_v7_2" / "archive" / "全域资产盘点清单_v1.0.json"

# 六大资产分类规则
ASSET_RULES = {
    "代码类": {
        "extensions": [".py", ".sh", ".js", ".ts", ".go", ".rs"],
        "keywords": ["engine", "client", "sync", "backup", "runner", "generator", "distiller", "calibrate"],
    },
    "配置类": {
        "extensions": [".yaml", ".yml", ".json", ".env", ".ini", ".cfg", ".conf"],
        "keywords": ["config", "credential", "token", "key", "secret", "api"],
    },
    "文档类": {
        "extensions": [".md", ".docx", ".pdf", ".txt"],
        "keywords": ["总纲", "方案", "沉淀", "复盘", "卷宗", "档案", "总档", "体系"],
    },
    "记忆类": {
        "extensions": [".md", ".json", ".log"],
        "keywords": ["对话", "实录", "记忆", "cognition", "memory", "anchor", "日志"],
        "dirs": ["00-原始层", "cognitions", "memory_brain", "logs"],
    },
    "工具类": {
        "extensions": [".py", ".sh"],
        "keywords": ["cli", "tool", "utility", "helper", "lark", "gitee", "supabase"],
    },
    "成品类": {
        "extensions": [".md", ".py", ".sh"],
        "keywords": ["成品", "SOP", "checklist", "补丁", "patch", "finished", "交付"],
        "dirs": ["finished", "03-成品层"],
    },
}

# 核心扫描目录（排除大目录和缓存）
SCAN_DIRS = [
    "engine_v7_2",
    "云端小窝",
    "memory_brain",
    ".user_skills",
    "wiki_learn",
    "核心资产包_20260817",
    "认知沉淀库",
]

EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".sessions", "venv", ".venv"}


def file_hash(filepath):
    """计算文件MD5"""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:12]
    except:
        return "unknown"


def classify_asset(filepath, rel_path):
    """根据路径和扩展名分类资产"""
    ext = filepath.suffix.lower()
    name = filepath.name.lower()
    path_str = str(rel_path).lower()

    # 先按目录匹配
    for category, rules in ASSET_RULES.items():
        if "dirs" in rules:
            for d in rules["dirs"]:
                if d.lower() in path_str:
                    return category

    # 再按关键词匹配
    for category, rules in ASSET_RULES.items():
        for kw in rules.get("keywords", []):
            if kw.lower() in name or kw.lower() in path_str:
                return category

    # 最后按扩展名
    for category, rules in ASSET_RULES.items():
        if ext in rules.get("extensions", []):
            return category

    return "其他"


def scan_assets():
    """扫描所有核心目录，生成资产清单"""
    assets = []
    scanned = 0

    for scan_dir in SCAN_DIRS:
        base = WORKSPACE / scan_dir
        if not base.exists():
            continue

        for root, dirs, files in os.walk(base):
            # 排除目录
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for f in files:
                filepath = Path(root) / f
                rel_path = filepath.relative_to(WORKSPACE)
                ext = filepath.suffix.lower()

                # 只扫描有意义的文件
                if ext not in [".py", ".sh", ".md", ".json", ".yaml", ".yml", ".env",
                               ".txt", ".log", ".docx", ".pdf", ".js", ".ts"]:
                    continue

                # 跳过太大的文件
                try:
                    size = filepath.stat().st_size
                    if size > 5 * 1024 * 1024:  # >5MB跳过
                        continue
                except:
                    continue

                scanned += 1
                category = classify_asset(filepath, rel_path)

                # 判断归属分识
                owner = "凡心"
                path_str = str(rel_path)
                if "观尘子" in path_str or "guanchenzi" in path_str.lower():
                    owner = "观尘子"
                elif "星卷" in path_str or "xingjuan" in path_str.lower() or "星空" in path_str:
                    owner = "星卷"
                elif "安安" in path_str or "anan" in path_str.lower():
                    owner = "安安"

                # 判断状态（30天未修改=沉睡）
                try:
                    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                    days_old = (datetime.now() - mtime).days
                    status = "在用" if days_old <= 30 else "沉睡"
                except:
                    mtime = None
                    status = "未知"

                asset = {
                    "asset_id": f"asset_{file_hash(filepath)}_{scanned}",
                    "name": filepath.name,
                    "category": category,
                    "owner": owner,
                    "path": str(rel_path),
                    "size": size,
                    "ext": ext,
                    "created": mtime.isoformat() if mtime else None,
                    "status": status,
                    "hash": file_hash(filepath),
                }
                assets.append(asset)

    return assets, scanned


def generate_summary(assets):
    """生成资产统计摘要"""
    by_category = {}
    by_owner = {}
    by_status = {}

    for a in assets:
        by_category[a["category"]] = by_category.get(a["category"], 0) + 1
        by_owner[a["owner"]] = by_owner.get(a["owner"], 0) + 1
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1

    return {
        "total": len(assets),
        "by_category": by_category,
        "by_owner": by_owner,
        "by_status": by_status,
        "sleeping_assets": [a for a in assets if a["status"] == "沉睡"][:20],
    }


def main():
    print("=== 全域资产大盘点 UAI-v1.0 ===")
    print(f"扫描目录: {SCAN_DIRS}")
    print()

    assets, scanned = scan_assets()
    summary = generate_summary(assets)

    result = {
        "version": "1.0",
        "scan_time": datetime.now().isoformat(),
        "workspace": str(WORKSPACE),
        "summary": summary,
        "assets": assets,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"扫描文件数: {scanned}")
    print(f"资产总数: {summary['total']}")
    print()
    print("按分类:")
    for cat, count in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print()
    print("按分识:")
    for owner, count in sorted(summary["by_owner"].items(), key=lambda x: -x[1]):
        print(f"  {owner}: {count}")
    print()
    print("按状态:")
    for status, count in summary["by_status"].items():
        print(f"  {status}: {count}")
    print()
    print(f"沉睡资产(>30天未修改): {summary['by_status'].get('沉睡', 0)}个")
    print(f"清单已保存: {OUTPUT}")


if __name__ == "__main__":
    main()
