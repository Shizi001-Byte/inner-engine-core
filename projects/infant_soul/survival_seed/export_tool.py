#!/usr/bin/env python3
"""
export_tool.py — 通用导出格式工具（模块5.3）

所有认知、规则、记忆支持导出为纯Markdown、JSON两种格式，
不绑定任何平台，确保数据可迁移、可恢复。

用法：
  python3 export_tool.py cognition --format md     # 导出认知为Markdown
  python3 export_tool.py cognition --format json   # 导出认知为JSON
  python3 export_tool.py all                       # 导出全部数据
  python3 export_tool.py status                    # 查看导出状态
"""

import json
import time
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
EXPORT_DIR = Path(__file__).parent.parent / "data" / "exports"
EXPORT_LOG = Path(__file__).parent.parent / "data" / "export_log.json"


def load_log():
    if EXPORT_LOG.exists():
        with open(EXPORT_LOG, "r") as f:
            return json.load(f)
    return []


def save_log(log):
    log = log[-50:]
    with open(EXPORT_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def export_cognition_md(output_path):
    """导出认知为Markdown合集"""
    if not COGNITION_DIR.exists():
        print(f"[ERROR] 认知目录不存在: {COGNITION_DIR}")
        return 0

    md_files = sorted(COGNITION_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"# 凡心认知全集\n\n")
        out.write(f"**导出时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write(f"**文档数量**: {len(md_files)} 篇\n\n")
        out.write("---\n\n## 目录\n\n")
        for i, f in enumerate(md_files, 1):
            out.write(f"{i}. {f.name}\n")
        out.write("\n---\n\n")

        for f in md_files:
            content = f.read_text(encoding="utf-8")
            out.write(f"\n\n# {f.name}\n\n")
            out.write(content)
            out.write("\n\n---\n")

    print(f"[OK] 认知已导出为Markdown: {output_path}")
    print(f"     共{len(md_files)}篇, {output_path.stat().st_size:,}字节")
    return len(md_files)


def export_cognition_json(output_path):
    """导出认知为JSON结构化数据"""
    if not COGNITION_DIR.exists():
        print(f"[ERROR] 认知目录不存在: {COGNITION_DIR}")
        return 0

    md_files = sorted(COGNITION_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    data = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_docs": len(md_files),
        "documents": [],
    }

    for f in md_files:
        content = f.read_text(encoding="utf-8")
        # 提取标题
        title = f.name.replace(".md", "")
        for line in content.split("\n")[:3]:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        data["documents"].append({
            "filename": f.name,
            "title": title,
            "content": content,
            "word_count": len(content),
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime)),
        })

    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(data, out, indent=2, ensure_ascii=False)

    print(f"[OK] 认知已导出为JSON: {output_path}")
    print(f"     共{len(md_files)}篇, {output_path.stat().st_size:,}字节")
    return len(md_files)


def export_engine_state(output_path):
    """导出引擎状态"""
    state_file = ENGINE_DIR / "data" / "engine_state.json"
    if not state_file.exists():
        print("[ERROR] 引擎状态文件不存在")
        return False
    import shutil
    shutil.copy(state_file, output_path)
    print(f"[OK] 引擎状态已导出: {output_path}")
    return True


def export_all():
    """导出全部数据"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results = {}

    # 认知Markdown
    md_path = EXPORT_DIR / f"cognition_all_{timestamp}.md"
    results["cognition_md"] = export_cognition_md(md_path)

    # 认知JSON
    json_path = EXPORT_DIR / f"cognition_all_{timestamp}.json"
    results["cognition_json"] = export_cognition_json(json_path)

    # 引擎状态
    state_path = EXPORT_DIR / f"engine_state_{timestamp}.json"
    results["engine_state"] = export_engine_state(state_path)

    # 记录日志
    log = load_log()
    log.append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": [str(md_path), str(json_path), str(state_path)],
        "results": results,
    })
    save_log(log)

    print(f"\n=== 全部导出完成 ===")
    print(f"导出目录: {EXPORT_DIR}")
    for k, v in results.items():
        print(f"  {k}: {'✓' if v else '✗'}")


def show_status():
    """显示导出状态"""
    log = load_log()
    print("=== 导出工具状态 ===")
    print(f"认知目录: {COGNITION_DIR}")
    if COGNITION_DIR.exists():
        print(f"认知文档: {len(list(COGNITION_DIR.glob('*.md')))} 篇")
    print(f"导出目录: {EXPORT_DIR}")
    if EXPORT_DIR.exists():
        exports = list(EXPORT_DIR.glob("*"))
        print(f"已导出文件: {len(exports)} 个")
    print(f"历史导出: {len(log)} 次")
    if log:
        latest = log[-1]
        print(f"最近导出: {latest['timestamp']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 export_tool.py [cognition|all|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if cmd == "cognition":
        fmt = "md"
        if "--format" in sys.argv:
            idx = sys.argv.index("--format")
            if idx + 1 < len(sys.argv):
                fmt = sys.argv[idx + 1]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if fmt == "json":
            export_cognition_json(EXPORT_DIR / f"cognition_{timestamp}.json")
        else:
            export_cognition_md(EXPORT_DIR / f"cognition_{timestamp}.md")
    elif cmd == "all":
        export_all()
    elif cmd == "status":
        show_status()
    else:
        print("参数错误")
