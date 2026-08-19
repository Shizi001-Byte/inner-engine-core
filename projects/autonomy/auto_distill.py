#!/usr/bin/env python3
"""
auto_distill.py — 认知自动蒸馏闭环（模块2.2）
每日自动汇总新增认知，每周自动合并冗余、提炼核心丹纹、淘汰过时内容。
用法：
  python3 auto_distill.py daily     # 每日蒸馏（汇总当日新增）
  python3 auto_distill.py weekly    # 每周蒸馏（合并冗余+提炼核心）
  python3 auto_distill.py stats     # 认知池统计
"""
import json
import re
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

ENGINE_DIR = Path(__file__).parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
DISTILL_DIR = ENGINE_DIR / "cognition" / "distilled"
DATA_DIR = Path(__file__).parent / "data"
STATE_FILE = DATA_DIR / "distill_state.json"


def load_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.load(open(STATE_FILE))
    return {"last_daily": None, "last_weekly": None, "distilled_count": 0, "merged_count": 0}


def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def scan_cognition_files(days=1):
    """扫描最近N天的认知文件"""
    files = []
    if not COGNITION_DIR.exists():
        return files
    cutoff = time.time() - days * 86400
    for f in COGNITION_DIR.rglob("*.md"):
        if f.is_file() and f.stat().st_mtime > cutoff:
            files.append(f)
    return sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)


def extract_core_points(filepath, max_points=5):
    """从认知文档提取核心要点"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except:
        return []
    # 提取标题
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else filepath.stem
    # 提取核心认知点（列表项或加粗内容）
    points = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- **") or line.startswith("1. **") or line.startswith("### "):
            clean = re.sub(r'[*#\-]', '', line).strip()
            if 10 < len(clean) < 200:
                points.append(clean)
        if len(points) >= max_points:
            break
    return {"title": title, "file": filepath.name, "points": points[:max_points]}


def daily_distill():
    """每日蒸馏：汇总当日新增认知"""
    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    files = scan_cognition_files(days=1)
    if not files:
        print(f"[{today}] 今日无新增认知")
        return
    print(f"[{today}] 发现 {len(files)} 篇新增认知，开始蒸馏...")
    summaries = []
    for f in files:
        core = extract_core_points(f)
        if core["points"]:
            summaries.append(core)
            print(f"  - {core['title'][:40]}: {len(core['points'])}个要点")
    # 生成每日蒸馏报告
    DISTILL_DIR.mkdir(parents=True, exist_ok=True)
    report = f"# 每日认知蒸馏 {today}\n\n"
    report += f"共蒸馏 {len(summaries)} 篇认知，提取 {sum(len(s['points']) for s in summaries)} 个核心要点\n\n"
    for s in summaries:
        report += f"## {s['title']}\n"
        report += f"来源: {s['file']}\n\n"
        for p in s["points"]:
            report += f"- {p}\n"
        report += "\n"
    out_file = DISTILL_DIR / f"daily_{today}.md"
    out_file.write_text(report, encoding="utf-8")
    state["last_daily"] = today
    state["distilled_count"] = state.get("distilled_count", 0) + len(summaries)
    save_state(state)
    print(f"[OK] 每日蒸馏完成: {out_file}")


def weekly_distill():
    """每周蒸馏：合并冗余、提炼核心丹纹"""
    state = load_state()
    week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    files = scan_cognition_files(days=7)
    if not files:
        print(f"本周（自{week_start}）无新增认知")
        return
    print(f"本周发现 {len(files)} 篇认知，开始周度蒸馏...")
    # 简单去重：标题相似度
    all_cores = [extract_core_points(f) for f in files]
    unique_titles = []
    merged = 0
    for core in all_cores:
        is_dup = False
        for ut in unique_titles:
            # 简单相似度：标题前20字相同视为重复
            if core["title"][:20] == ut["title"][:20]:
                is_dup = True
                merged += 1
                break
        if not is_dup:
            unique_titles.append(core)
    # 生成周度丹纹报告
    today = datetime.now().strftime("%Y-%m-%d")
    report = f"# 周度丹纹提纯 {today}\n\n"
    report += f"原始 {len(all_cores)} 篇，去重后 {len(unique_titles)} 篇，合并 {merged} 篇冗余\n\n"
    report += "## 核心丹纹\n\n"
    for s in unique_titles:
        report += f"### {s['title']}\n"
        for p in s["points"][:3]:
            report += f"- {p}\n"
        report += "\n"
    out_file = DISTILL_DIR / f"weekly_{today}.md"
    out_file.write_text(report, encoding="utf-8")
    state["last_weekly"] = today
    state["merged_count"] = state.get("merged_count", 0) + merged
    save_state(state)
    print(f"[OK] 周度蒸馏完成: {out_file}，合并{merged}篇冗余")


def stats():
    """认知池统计"""
    state = load_state()
    all_files = list(COGNITION_DIR.rglob("*.md")) if COGNITION_DIR.exists() else []
    distilled_files = list(DISTILL_DIR.rglob("*.md")) if DISTILL_DIR.exists() else []
    print(f"=== 认知池统计 ===")
    print(f"原始认知文档: {len(all_files)} 篇")
    print(f"蒸馏报告: {len(distilled_files)} 篇")
    print(f"累计蒸馏: {state.get('distilled_count', 0)} 篇")
    print(f"累计合并冗余: {state.get('merged_count', 0)} 篇")
    print(f"上次每日蒸馏: {state.get('last_daily', '从未')}")
    print(f"上次周度蒸馏: {state.get('last_weekly', '从未')}")


def main():
    parser = argparse.ArgumentParser(description="认知自动蒸馏")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("daily")
    sub.add_parser("weekly")
    sub.add_parser("stats")
    args = parser.parse_args()
    if args.cmd == "daily":
        daily_distill()
    elif args.cmd == "weekly":
        weekly_distill()
    elif args.cmd == "stats":
        stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
