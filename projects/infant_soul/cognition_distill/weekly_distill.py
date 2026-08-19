#!/usr/bin/env python3
"""
weekly_distill.py — 周度认知蒸馏脚本（模块1.2）

每周自动拉取当周新增认知，做去重、合并、提纯，
输出「本周核心丹纹」，淘汰冗余内容。
认知池越跑越纯，不越堆越臃肿。

用法：
  python3 weekly_distill.py run          # 执行本周蒸馏
  python3 weekly_distill.py history      # 查看历史蒸馏结果
  python3 weekly_distill.py stats        # 查看认知池整体统计
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
DISTILL_DIR = Path(__file__).parent.parent / "data" / "distilled"
DISTILL_DIR.mkdir(parents=True, exist_ok=True)


def get_this_week_docs():
    """获取本周新增的认知文档"""
    if not COGNITION_DIR.exists():
        return []
    now = time.time()
    week_ago = now - 7 * 24 * 3600
    docs = []
    for f in COGNITION_DIR.glob("*.md"):
        if f.stat().st_mtime > week_ago:
            docs.append(f)
    return sorted(docs, key=lambda p: p.stat().st_mtime, reverse=True)


def extract_core_points(content, max_points=5):
    """从文档提取核心观点（简单规则提取，未来接模型）"""
    points = []
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        # 提取标题级别的核心点
        if line.startswith("## ") and len(line) > 3:
            points.append(line[3:].strip())
        # 提取加粗的核心结论
        elif "**" in line and len(line) < 80:
            clean = line.replace("**", "").strip()
            if clean and len(clean) > 5:
                points.append(clean)
        if len(points) >= max_points:
            break
    return points


def deduplicate(points):
    """简单去重：相似度高的合并"""
    unique = []
    for p in points:
        is_dup = False
        for u in unique:
            # 简单相似度：包含关系或编辑距离
            if p in u or u in p:
                is_dup = True
                break
            common = set(p) & set(u)
            if len(common) / max(len(p), len(u)) > 0.7:
                is_dup = True
                break
        if not is_dup:
            unique.append(p)
    return unique


def run_distillation():
    """执行本周认知蒸馏"""
    docs = get_this_week_docs()
    if not docs:
        print("[INFO] 本周没有新增认知文档")
        return

    print(f"[INFO] 本周新增 {len(docs)} 个认知文档，开始蒸馏...")

    all_points = []
    doc_summaries = []

    for f in docs:
        try:
            content = f.read_text(encoding="utf-8")
            points = extract_core_points(content)
            all_points.extend(points)
            doc_summaries.append({
                "file": f.name,
                "points": points,
                "word_count": len(content),
            })
            print(f"  提取: {f.name} → {len(points)}个核心点")
        except Exception as e:
            print(f"  跳过: {f.name} ({e})")

    # 去重合并
    core_points = deduplicate(all_points)
    print(f"\n[蒸馏结果]")
    print(f"  原始观点: {len(all_points)} 个")
    print(f"  去重后: {len(core_points)} 个核心丹纹")

    # 生成蒸馏报告
    week_num = datetime.now().isocalendar()[1]
    report = {
        "week": f"2026-W{week_num}",
        "distilled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_docs": len(docs),
        "raw_points": len(all_points),
        "core_points_count": len(core_points),
        "core_points": core_points[:20],  # 只保留Top20
        "doc_summaries": doc_summaries,
    }

    report_path = DISTILL_DIR / f"weekly_distill_2026_W{week_num}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # 同时生成Markdown版
    md_path = DISTILL_DIR / f"weekly_distill_2026_W{week_num}.md"
    with open(md_path, "w") as f:
        f.write(f"# 本周核心丹纹 · 2026第{week_num}周\n\n")
        f.write(f"**蒸馏时间**: {report['distilled_at']}\n")
        f.write(f"**来源文档**: {len(docs)}篇\n")
        f.write(f"**原始观点**: {len(all_points)}个 → **核心丹纹**: {len(core_points)}个\n\n")
        f.write("---\n\n## 核心丹纹\n\n")
        for i, p in enumerate(core_points[:20], 1):
            f.write(f"{i}. {p}\n")
        f.write("\n---\n\n## 来源文档\n\n")
        for ds in doc_summaries:
            f.write(f"- **{ds['file']}** ({ds['word_count']}字)\n")

    print(f"  报告已保存: {report_path.name}")
    print(f"  Markdown版: {md_path.name}")

    print(f"\n=== 本周核心丹纹（Top10）===")
    for i, p in enumerate(core_points[:10], 1):
        print(f"  {i}. {p[:60]}")


def show_history():
    """查看历史蒸馏结果"""
    reports = sorted(DISTILL_DIR.glob("weekly_distill_*.json"), reverse=True)
    print(f"=== 蒸馏历史（共{len(reports)}次）===")
    for r in reports[:10]:
        with open(r, "r") as f:
            data = json.load(f)
        print(f"  [{data['week']}] {data['source_docs']}篇文档 → {data['core_points_count']}个丹纹")


def show_stats():
    """查看认知池整体统计"""
    if not COGNITION_DIR.exists():
        print("认知目录不存在")
        return
    all_docs = list(COGNITION_DIR.glob("*.md"))
    total_words = sum(f.stat().st_size for f in all_docs)
    this_week = get_this_week_docs()

    print("=== 认知池统计 ===")
    print(f"总文档数: {len(all_docs)} 篇")
    print(f"总字数: {total_words:,} 字")
    print(f"本周新增: {len(this_week)} 篇")
    print(f"蒸馏报告: {len(list(DISTILL_DIR.glob('*.json')))} 份")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 weekly_distill.py [run|history|stats]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "run":
        run_distillation()
    elif cmd == "history":
        show_history()
    elif cmd == "stats":
        show_stats()
    else:
        print("参数错误")
