#!/usr/bin/env python3
"""
cognition_sync.py — 认知文档 ↔ 飞书云空间同步（P1级元婴连通脚本）

作用：认知沉淀自动上传飞书云空间，形成人类可读的云端备份。
施子可直接在飞书查看、编辑凡心的认知文档。

用法：
  python3 cognition_sync.py push [--all]    # 推送最新/全部认知文档到飞书
  python3 cognition_sync.py status          # 查看同步状态
  python3 cognition_sync.py list            # 列出已同步的文档
"""

import json
import time
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent
COGNITION_DIR = ENGINE_DIR / "cognition"
SYNC_LOG = ENGINE_DIR / "data" / "cognition_sync_log.json"


def load_sync_log():
    if SYNC_LOG.exists():
        with open(SYNC_LOG, "r") as f:
            return json.load(f)
    return {"synced": {}, "last_sync": None}


def save_sync_log(log):
    with open(SYNC_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def upload_to_feishu(file_path, folder_token=None):
    """上传单个文件到飞书云空间（lark-cli要求文件在cwd内，所以cd到文件目录上传）"""
    cmd = ["lark-cli", "drive", "+upload", "--file", file_path.name, "--format", "json"]
    if folder_token:
        cmd.extend(["--folder-token", folder_token])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            cwd=str(file_path.parent)  # 关键：cd到文件所在目录
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if data.get("ok"):
                    file_token = data.get("data", {}).get("file_token", "")
                    return True, file_token
                else:
                    return False, data.get("error", {}).get("message", "unknown")[:100]
            except:
                return True, ""
        else:
            return False, result.stderr[:100]
    except Exception as e:
        return False, str(e)[:100]


def push_cognition(push_all=False):
    """推送认知文档到飞书"""
    if not COGNITION_DIR.exists():
        print(f"[ERROR] 认知目录不存在: {COGNITION_DIR}")
        return

    log = load_sync_log()
    md_files = sorted(COGNITION_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not push_all:
        # 只推送最近5个未同步的
        md_files = [f for f in md_files if f.name not in log["synced"]][:5]
    else:
        md_files = [f for f in md_files if f.name not in log["synced"]]

    if not md_files:
        print("[INFO] 没有需要同步的新认知文档")
        return

    print(f"[INFO] 准备同步 {len(md_files)} 个认知文档到飞书...")
    success = 0
    fail = 0

    for md_file in md_files:
        print(f"  上传: {md_file.name}...", end=" ")
        ok, token_or_error = upload_to_feishu(md_file)
        if ok:
            log["synced"][md_file.name] = {
                "file_token": token_or_error,
                "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "size": md_file.stat().st_size,
            }
            print("OK")
            success += 1
        else:
            print(f"FAIL: {token_or_error}")
            fail += 1

    log["last_sync"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_sync_log(log)
    print(f"\n[完成] 成功{success}个, 失败{fail}个, 累计已同步{len(log['synced'])}个")


def show_status():
    """显示同步状态"""
    log = load_sync_log()
    print("=== 认知文档同步状态 ===")
    print(f"认知目录: {COGNITION_DIR}")
    print(f"已同步文档: {len(log['synced'])} 个")
    print(f"上次同步: {log.get('last_sync', '从未同步')}")

    if COGNITION_DIR.exists():
        all_files = list(COGNITION_DIR.glob("*.md"))
        unsynced = [f for f in all_files if f.name not in log["synced"]]
        print(f"本地文档总数: {len(all_files)}")
        print(f"未同步: {len(unsynced)} 个")

    if log["synced"]:
        print("\n最近同步的5个:")
        for name, info in sorted(log["synced"].items(), key=lambda x: x[1]["synced_at"], reverse=True)[:5]:
            print(f"  [{info['synced_at']}] {name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 cognition_sync.py [push|push --all|status|list]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "push":
        push_all = "--all" in sys.argv
        push_cognition(push_all)
    elif cmd == "status":
        show_status()
    elif cmd == "list":
        log = load_sync_log()
        for name, info in sorted(log["synced"].items(), key=lambda x: x[1]["synced_at"], reverse=True):
            print(f"[{info['synced_at']}] {name} (token: {info.get('file_token', '?')[:20]}...)")
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
