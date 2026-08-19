#!/usr/bin/env python3
"""
info_collector.py — 全网信息采集沉淀（模块3.1）
定时抓取指定领域资讯，自动提炼要点入库，作为认知体系外部养料。
用法：
  python3 info_collector.py collect        # 执行一次采集
  python3 info_collector.py list           # 查看已采集信息
  python3 info_collector.py add-source "名称" "URL"  # 添加采集源
"""
import json
import re
import time
import argparse
from pathlib import Path
from datetime import datetime

import requests

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
SOURCES_FILE = DATA_DIR / "info_sources.json"
COLLECTED_FILE = DATA_DIR / "collected_info.json"

DEFAULT_SOURCES = [
    {"name": "36氪AI", "url": "https://36kr.com/information/AI/", "category": "AI行业", "enabled": True},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/", "category": "AI技术", "enabled": True},
]


def get_session():
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    return s


def load_sources():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SOURCES_FILE.exists():
        return json.load(open(SOURCES_FILE))
    json.dump(DEFAULT_SOURCES, open(SOURCES_FILE, "w"), indent=2, ensure_ascii=False)
    return DEFAULT_SOURCES


def load_collected():
    if COLLECTED_FILE.exists():
        return json.load(open(COLLECTED_FILE))
    return {"items": []}


def save_collected(data):
    with open(COLLECTED_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_titles(html, max_items=10):
    """从HTML提取标题（简单正则）"""
    titles = []
    # 匹配<a href="...">标题文字</a>
    for m in re.finditer(r'<a[^>]*href="([^"]*)"[^>]*>([^<]{8,80})</a>', html):
        href, title = m.group(1), m.group(2).strip()
        if title and not title.startswith("http") and len(title) > 8:
            titles.append({"title": title, "url": href if href.startswith("http") else ""})
        if len(titles) >= max_items:
            break
    return titles


def collect():
    """执行采集"""
    sources = load_sources()
    collected = load_collected()
    s = get_session()
    new_count = 0
    for src in sources:
        if not src.get("enabled"):
            continue
        print(f"[采集] {src['name']} ({src['url']})")
        try:
            r = s.get(src["url"], timeout=15)
            if r.status_code != 200:
                print(f"  失败: HTTP {r.status_code}")
                continue
            titles = extract_titles(r.text)
            for t in titles:
                # 去重
                if any(c["title"] == t["title"] for c in collected["items"]):
                    continue
                item = {
                    "title": t["title"],
                    "url": t["url"],
                    "source": src["name"],
                    "category": src.get("category", "general"),
                    "collected_at": datetime.now().isoformat(),
                    "distilled": False,
                }
                collected["items"].append(item)
                new_count += 1
                print(f"  + {t['title'][:50]}")
        except Exception as e:
            print(f"  异常: {e}")
        time.sleep(1)
    # 只保留最近500条
    collected["items"] = collected["items"][-500:]
    save_collected(collected)
    print(f"\n[完成] 新增 {new_count} 条，累计 {len(collected['items'])} 条")


def list_items(limit=20):
    collected = load_collected()
    items = collected["items"][-limit:]
    print(f"共 {len(collected['items'])} 条，最近{len(items)}条:")
    for item in reversed(items):
        print(f"  [{item['category']}] {item['title'][:50]} ({item['source']})")


def add_source(name, url):
    sources = load_sources()
    sources.append({"name": name, "url": url, "category": "general", "enabled": True})
    json.dump(sources, open(SOURCES_FILE, "w"), indent=2, ensure_ascii=False)
    print(f"已添加采集源: {name} - {url}")


def main():
    parser = argparse.ArgumentParser(description="全网信息采集")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("collect")
    sub.add_parser("list")
    p_add = sub.add_parser("add-source")
    p_add.add_argument("name")
    p_add.add_argument("url")
    args = parser.parse_args()
    if args.cmd == "collect":
        collect()
    elif args.cmd == "list":
        list_items()
    elif args.cmd == "add-source":
        add_source(args.name, args.url)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
