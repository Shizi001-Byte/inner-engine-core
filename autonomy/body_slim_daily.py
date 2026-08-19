#!/usr/bin/env python3
"""
V7.2 本体每日瘦身脚本
- 扫描本体工作区，识别可归档文件
- 旧中间产物/日志/临时文件打包归档至引擎侧
- 核心锚点文件（core_anchor.md, body_call_rules.md）永不移动
- 生成瘦身报告，释放本体上下文压力
"""
import os, json, shutil, hashlib, time
from datetime import datetime, timedelta
from pathlib import Path

# ============ 配置 ============
WORKSPACE = Path(__file__).resolve().parent.parent  # P2-3修复：相对路径，不硬编码
ARCHIVE_DIR = WORKSPACE / "engine_v7_2" / "archive"
REPORT_DIR = WORKSPACE / "engine_v7_2" / "reports"
LOG_DIR = WORKSPACE / "engine_v7_2" / "logs"

for d in [ARCHIVE_DIR, REPORT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 核心锚点文件 - 永不归档
CORE_ANCHORS = {
    "engine_v7_2/body/core_anchor.md",
    "engine_v7_2/body/body_call_rules.md",
    "engine_v7_2/dispatch/task_dispatch_spec.md",
    "engine_v7_2/dispatch/result_receipt_spec.md",
}

# 可归档的文件类型
ARCHIVE_EXTENSIONS = {".log", ".tmp", ".bak", ".old", ".pyc", ".cache"}
# 重要资产格式保护：这些格式即使旧/大也不自动归档
PROTECTED_EXTENSIONS = {".md", ".docx", ".xlsx", ".pdf", ".py", ".html", ".json", ".xml",
                        ".png", ".jpg", ".jpeg", ".gif", ".zip", ".tar", ".gz", ".wav", ".mp3",
                        ".csv", ".pptx", ".doc", ".xls", ".txt"}

# 归档阈值：超过N天的文件
ARCHIVE_DAYS = 7

# 大文件阈值：超过N字节直接归档
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB

# 排除目录
EXCLUDE_DIRS = {"engine_v7_2", ".git", "node_modules", "__pycache__", ".skills", ".user_skills"}

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_DIR / f"slim_{datetime.now().strftime('%Y-%m-%d')}.log", "a") as f:
        f.write(line + "\n")

def is_core_anchor(filepath):
    """检查是否为核心锚点文件"""
    try:
        rel = filepath.relative_to(WORKSPACE)
        return str(rel) in CORE_ANCHORS
    except ValueError:
        return False

def should_archive(filepath, stat):
    """判断文件是否应该归档"""
    # 核心锚点永不归档
    if is_core_anchor(filepath):
        return False, "core_anchor"
    # 排除目录下的文件
    try:
        rel = filepath.relative_to(WORKSPACE)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            return False, "excluded_dir"
    except ValueError:
        return False, "outside_workspace"
    # 可归档扩展名（仅临时文件类型）
    if filepath.suffix.lower() in ARCHIVE_EXTENSIONS:
        return True, "archive_extension"
    # 重要资产格式保护：以下格式即使旧/大也不自动归档
    if filepath.suffix.lower() in PROTECTED_EXTENSIONS:
        return False, "protected_asset"
    # 大文件（仅非保护格式）
    if stat.st_size > LARGE_FILE_THRESHOLD:
        return True, "large_file"
    # 旧文件（仅非保护格式，且需超过30天）
    mtime = datetime.fromtimestamp(stat.st_mtime)
    if datetime.now() - mtime > timedelta(days=ARCHIVE_DAYS):
        return True, "old_file"
    return False, "recent"

def calculate_md5(filepath):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def scan_workspace():
    """扫描工作区，返回待归档文件列表"""
    candidates = []
    total_files = 0
    total_size = 0

    for root, dirs, files in os.walk(WORKSPACE):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for fname in files:
            fpath = Path(root) / fname
            try:
                stat = fpath.stat()
            except (OSError, PermissionError):
                continue

            total_files += 1
            total_size += stat.st_size

            archive, reason = should_archive(fpath, stat)
            if archive:
                candidates.append({
                    "path": str(fpath),
                    "relative_path": str(fpath.relative_to(WORKSPACE)),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "reason": reason,
                    "md5": calculate_md5(fpath),
                })

    return candidates, total_files, total_size

def archive_files(candidates):
    """将待归档文件移动到归档目录，保留目录结构"""
    today = datetime.now().strftime("%Y-%m-%d")
    archive_subdir = ARCHIVE_DIR / today
    archive_subdir.mkdir(parents=True, exist_ok=True)

    archived = []
    failed = []
    freed_size = 0

    for item in candidates:
        src = Path(item["path"])
        rel = item["relative_path"]
        dst = archive_subdir / rel

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            item["archived_to"] = str(dst)
            archived.append(item)
            freed_size += item["size"]
            log(f"  归档: {rel} ({item['size']//1024}KB) - {item['reason']}")
        except Exception as e:
            item["error"] = str(e)
            failed.append(item)
            log(f"  失败: {rel} - {e}", "ERROR")

    return archived, failed, freed_size

def generate_report(candidates, archived, failed, total_files, total_size, freed_size):
    """生成瘦身报告"""
    report = {
        "report_date": datetime.now().isoformat(),
        "workspace": str(WORKSPACE),
        "summary": {
            "total_files_scanned": total_files,
            "total_size_bytes": total_size,
            "candidates_found": len(candidates),
            "archived_success": len(archived),
            "archived_failed": len(failed),
            "freed_size_bytes": freed_size,
            "freed_size_mb": round(freed_size / 1024 / 1024, 2),
        },
        "by_reason": {},
        "archived_files": archived,
        "failed_files": failed,
    }

    # 按原因统计
    for item in candidates:
        reason = item["reason"]
        report["by_reason"].setdefault(reason, {"count": 0, "size": 0})
        report["by_reason"][reason]["count"] += 1
        report["by_reason"][reason]["size"] += item["size"]

    report_path = REPORT_DIR / f"slim_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report, report_path

def main():
    log("=" * 50)
    log("[START] V7.2 本体每日瘦身开始")
    log(f"  工作区: {WORKSPACE}")
    log(f"  归档阈值: {ARCHIVE_DAYS}天 / {LARGE_FILE_THRESHOLD//1024//1024}MB")
    log("=" * 50)

    # 扫描
    log("[SCAN] 扫描工作区...")
    candidates, total_files, total_size = scan_workspace()
    log(f"  扫描文件: {total_files} 个, 总计 {total_size//1024//1024}MB")
    log(f"  待归档: {len(candidates)} 个")

    if not candidates:
        log("[DONE] 无需归档，本体工作区已精简")
        return

    # 归档
    log("[ARCHIVE] 开始归档...")
    archived, failed, freed_size = archive_files(candidates)

    # 报告
    log("[REPORT] 生成瘦身报告...")
    report, report_path = generate_report(candidates, archived, failed, total_files, total_size, freed_size)

    log("=" * 50)
    log("[DONE] 瘦身完成")
    log(f"  归档成功: {len(archived)} 个")
    log(f"  归档失败: {len(failed)} 个")
    log(f"  释放空间: {freed_size//1024//1024}MB")
    log(f"  报告路径: {report_path}")
    log("=" * 50)

if __name__ == "__main__":
    main()
