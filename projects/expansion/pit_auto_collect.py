#!/usr/bin/env python3
"""
pit_auto_collect.py — 坑库自动积累机制（模块3.4）
任务失败、报错、踩坑自动提取原因和解决方案，写入全域坑库。
用法：
  python3 pit_auto_collect.py add "现象" "原因" "解决方案" --level L1   # 手动添加坑
  python3 pit_auto_collect.py list                                       # 列出坑库
  python3 pit_auto_collect.py scan-logs                                  # 扫描日志自动提取坑
  python3 pit_auto_collect.py check "现象关键词"                          # 检查是否踩过同类坑
"""
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
PIT_FILE = DATA_DIR / "pit_library.json"
LOG_DIR = ENGINE_DIR / "data"


def load_pits():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PIT_FILE.exists():
        return json.load(open(PIT_FILE))
    return {"pits": [], "count": 0}


def save_pits(data):
    data["count"] = len(data["pits"])
    with open(PIT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_pit(phenomenon, cause, solution, level="L1", category="工程"):
    """添加一个坑"""
    pits = load_pits()
    # 去重
    for p in pits["pits"]:
        if p["phenomenon"] == phenomenon:
            print(f"坑已存在: {phenomenon[:40]}")
            return
    pit = {
        "id": pits["count"] + 1,
        "phenomenon": phenomenon,
        "cause": cause,
        "solution": solution,
        "level": level,  # L1工程/L2方法/L3规律
        "category": category,
        "created_at": datetime.now().isoformat(),
        "hit_count": 0,
    }
    pits["pits"].append(pit)
    save_pits(pits)
    print(f"[+] 新坑入库 #{pit['id']} [{level}] {phenomenon[:50]}")


def list_pits(level=None, limit=30):
    pits = load_pits()
    items = pits["pits"]
    if level:
        items = [p for p in items if p["level"] == level]
    print(f"坑库共 {pits['count']} 个，显示 {len(items[-limit:])} 个:")
    for p in reversed(items[-limit:]):
        print(f"  #{p['id']} [{p['level']}/{p['category']}] {p['phenomenon'][:45]}")
        print(f"     原因: {p['cause'][:50]}")
        print(f"     方案: {p['solution'][:50]}")


def check_pit(keyword):
    """检查是否踩过同类坑"""
    pits = load_pits()
    matches = [p for p in pits["pits"] if keyword in p["phenomenon"] or keyword in p["cause"]]
    if not matches:
        print(f"未找到包含'{keyword}'的坑，这是新坑！")
        return
    print(f"找到 {len(matches)} 个相关坑:")
    for p in matches:
        p["hit_count"] += 1
        print(f"\n  #{p['id']} [{p['level']}] {p['phenomenon']}")
        print(f"  原因: {p['cause']}")
        print(f"  方案: {p['solution']}")
        print(f"  历史命中: {p['hit_count']}次")
    save_pits(pits)


def scan_logs():
    """扫描引擎日志，自动提取错误模式"""
    pits = load_pits()
    new_count = 0
    if not LOG_DIR.exists():
        print("日志目录不存在")
        return
    # 扫描.log文件
    for log_file in LOG_DIR.glob("*.log"):
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            # 提取错误行
            errors = re.findall(r'(?:ERROR|FAIL|Exception|Traceback)[^\n]{0,100}', content)
            for err in errors[-20:]:  # 只看最近20条
                err = err.strip()
                if len(err) < 15:
                    continue
                # 去重
                if any(p["phenomenon"] == err[:80] for p in pits["pits"]):
                    continue
                add_pit(
                    phenomenon=err[:80],
                    cause="日志自动提取，待人工确认",
                    solution="待分析",
                    level="L1",
                    category="自动提取"
                )
                new_count += 1
        except Exception as e:
            print(f"扫描 {log_file.name} 失败: {e}")
    print(f"\n扫描完成，自动提取 {new_count} 个新坑")


def main():
    parser = argparse.ArgumentParser(description="坑库自动积累")
    sub = parser.add_subparsers(dest="cmd")
    p_add = sub.add_parser("add")
    p_add.add_argument("phenomenon")
    p_add.add_argument("cause")
    p_add.add_argument("solution")
    p_add.add_argument("--level", default="L1", choices=["L1", "L2", "L3"])
    p_add.add_argument("--category", default="工程")
    sub.add_parser("list")
    sub.add_parser("scan-logs")
    p_check = sub.add_parser("check")
    p_check.add_argument("keyword")
    args = parser.parse_args()
    if args.cmd == "add":
        add_pit(args.phenomenon, args.cause, args.solution, args.level, args.category)
    elif args.cmd == "list":
        list_pits()
    elif args.cmd == "scan-logs":
        scan_logs()
    elif args.cmd == "check":
        check_pit(args.keyword)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
