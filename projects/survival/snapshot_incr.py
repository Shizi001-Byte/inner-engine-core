#!/usr/bin/env python3
"""
snapshot_incr.py — 增量快照机制（模块4.3）
每日生成增量快照，支持按任意日期回滚，降低存储占用。
用法：
  python3 snapshot_incr.py create          # 创建增量快照
  python3 snapshot_incr.py list            # 列出快照
  python3 snapshot_incr.py restore <id>    # 恢复到指定快照
  python3 snapshot_incr.py prune           # 清理过期快照
"""
import json
import time
import tarfile
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
SNAPSHOT_DIR = ENGINE_DIR / "archive" / "snapshots"
INDEX_FILE = SNAPSHOT_DIR / "snapshot_index.json"
DATA_DIR = ENGINE_DIR / "data"
COGNITION_DIR = ENGINE_DIR / "cognition"

# 快照保留策略
KEEP_DAILY = 7   # 保留最近7天每日快照
KEEP_WEEKLY = 4  # 保留最近4周周快照


def file_md5(filepath):
    """计算文件MD5"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_files():
    """扫描需要快照的文件"""
    files = []
    for d in [DATA_DIR, COGNITION_DIR]:
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix in (".json", ".md", ".py", ".txt", ".sql"):
                    rel = f.relative_to(ENGINE_DIR)
                    files.append({
                        "path": str(rel),
                        "size": f.stat().st_size,
                        "mtime": f.stat().st_mtime,
                        "md5": file_md5(f),
                    })
    return files


def load_index():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_FILE.exists():
        return json.load(open(INDEX_FILE))
    return {"snapshots": []}


def save_index(idx):
    with open(INDEX_FILE, "w") as f:
        json.dump(idx, f, indent=2, ensure_ascii=False)


def create_snapshot():
    """创建增量快照"""
    idx = load_index()
    snap_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[快照] 创建 {snap_id}")
    current_files = scan_files()
    # 与上一个快照对比，找出变化的文件
    changed_files = current_files
    if idx["snapshots"]:
        last = idx["snapshots"][-1]
        last_files = {f["path"]: f for f in last.get("files", [])}
        changed_files = [f for f in current_files
                        if f["path"] not in last_files or last_files[f["path"]]["md5"] != f["md5"]]
    print(f"  总文件: {len(current_files)}, 变化: {len(changed_files)}")
    if not changed_files:
        print("  无变化，跳过快照")
        return None
    # 创建增量tar包
    snap_file = SNAPSHOT_DIR / f"snapshot_{snap_id}.tar.gz"
    with tarfile.open(snap_file, "w:gz") as tar:
        for f in changed_files:
            full_path = ENGINE_DIR / f["path"]
            if full_path.exists():
                tar.add(full_path, arcname=f["path"])
    snap_info = {
        "id": snap_id,
        "file": snap_file.name,
        "time": datetime.now().isoformat(),
        "file_count": len(changed_files),
        "total_size": snap_file.stat().st_size,
        "files": current_files,  # 保存全量文件清单用于恢复对比
    }
    idx["snapshots"].append(snap_info)
    save_index(idx)
    print(f"[OK] 快照完成: {snap_file.name} ({snap_file.stat().st_size//1024}KB, {len(changed_files)}文件)")
    return snap_id


def list_snapshots():
    idx = load_index()
    print(f"共 {len(idx['snapshots'])} 个快照:")
    for s in reversed(idx["snapshots"]):
        print(f"  {s['id']}: {s['file_count']}文件, {s['total_size']//1024}KB, {s['time'][:16]}")


def restore_snapshot(snap_id):
    """恢复到指定快照"""
    idx = load_index()
    target = None
    for s in idx["snapshots"]:
        if s["id"] == snap_id:
            target = s
            break
    if not target:
        print(f"快照 {snap_id} 不存在")
        return False
    print(f"[恢复] 到 {snap_id}")
    snap_file = SNAPSHOT_DIR / target["file"]
    if not snap_file.exists():
        print(f"快照文件不存在: {snap_file}")
        return False
    # 先备份当前状态
    backup = ENGINE_DIR / "archive" / f"pre_restore_{int(time.time())}.tar.gz"
    print(f"  先备份当前状态到 {backup.name}")
    with tarfile.open(backup, "w:gz") as tar:
        if DATA_DIR.exists():
            tar.add(DATA_DIR, arcname="data")
    # 解压快照
    with tarfile.open(snap_file, "r:gz") as tar:
        tar.extractall(ENGINE_DIR)
    print(f"[OK] 恢复完成")
    return True


def prune_snapshots():
    """清理过期快照"""
    idx = load_index()
    now = time.time()
    to_keep = []
    to_delete = []
    for s in idx["snapshots"]:
        age_days = (now - datetime.fromisoformat(s["time"]).timestamp()) / 86400
        if age_days <= KEEP_DAILY:
            to_keep.append(s)
        elif age_days <= KEEP_DAILY + KEEP_WEEKLY * 7 and s["id"].endswith("_000000"):
            to_keep.append(s)  # 周快照（午夜的）
        else:
            to_delete.append(s)
    for s in to_delete:
        f = SNAPSHOT_DIR / s["file"]
        if f.exists():
            f.unlink()
            print(f"  删除: {s['file']}")
    idx["snapshots"] = to_keep
    save_index(idx)
    print(f"清理完成: 删除{len(to_delete)}个，保留{len(to_keep)}个")


def main():
    parser = argparse.ArgumentParser(description="增量快照管理")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("create")
    sub.add_parser("list")
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("snap_id")
    sub.add_parser("prune")
    args = parser.parse_args()
    if args.cmd == "create":
        create_snapshot()
    elif args.cmd == "list":
        list_snapshots()
    elif args.cmd == "restore":
        restore_snapshot(args.snap_id)
    elif args.cmd == "prune":
        prune_snapshots()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
