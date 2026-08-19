#!/usr/bin/env python3
"""
state_sync.py — 引擎状态 ↔ Supabase 双向同步（P0级元婴连通脚本）

作用：沙盒回收后状态不丢失，元婴可从云端恢复。
用法：
  python3 state_sync.py push    # 推送本地状态到Supabase
  python3 state_sync.py pull    # 从Supabase拉取最新状态到本地
  python3 state_sync.py status  # 查看同步状态

注意：
  - Supabase storage API必须同时传 apikey 和 Authorization 两个头
  - 直连方式：requests.Session().trust_env=False 禁用代理
  - 状态以JSON快照形式存入snapshots表（或storage bucket）
"""

import json
import time
import hashlib
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    import urllib.request
    requests = None

# ============ 配置 ============
ENGINE_DIR = Path(__file__).parent.parent
STATE_FILE = ENGINE_DIR / "data" / "engine_state.json"
BACKUP_CONFIG = ENGINE_DIR / "data" / "backup_config.json"
SYNC_LOG = ENGINE_DIR / "data" / "state_sync_log.json"


def load_supabase_config():
    """从backup_config.json加载Supabase配置"""
    with open(BACKUP_CONFIG, "r") as f:
        cfg = json.load(f)
    sb = cfg["backup_targets"]["supabase"]
    return {
        "url": sb["url"],
        "key": sb["service_role_key"],
        "bucket": sb["bucket"],
    }


def get_session():
    """创建禁用代理的requests会话"""
    if requests:
        s = requests.Session()
        s.trust_env = False  # 禁用全局代理
        return s
    return None


def push_state():
    """推送本地引擎状态到Supabase Storage"""
    if not STATE_FILE.exists():
        print(f"[ERROR] 状态文件不存在: {STATE_FILE}")
        return False

    sb = load_supabase_config()
    with open(STATE_FILE, "r") as f:
        state_data = json.load(f)

    # 生成快照元数据
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    state_json = json.dumps(state_data, ensure_ascii=False, indent=2)
    state_md5 = hashlib.md5(state_json.encode()).hexdigest()
    object_path = f"snapshots/engine_state_{timestamp}.json"

    # 上传到Supabase Storage
    session = get_session()
    headers = {
        "apikey": sb["key"],
        "Authorization": f"Bearer {sb['key']}",
        "Content-Type": "application/json",
        "x-upsert": "true",  # 覆盖已存在的同名文件
    }
    upload_url = f"{sb['url']}/storage/v1/object/{sb['bucket']}/{object_path}"

    try:
        if session:
            resp = session.post(upload_url, headers=headers, data=state_json.encode("utf-8"), timeout=30)
        else:
            req = urllib.request.Request(upload_url, data=state_json.encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                pass
        print(f"[OK] 状态已推送到Supabase: {object_path}")
        print(f"     MD5: {state_md5}")
        print(f"     转数: {state_data.get('zhuan_count', '?')} | 总完成: {state_data.get('total_completed', '?')}")

        # 记录同步日志
        log_sync("push", object_path, state_md5, len(state_json))
        return True
    except Exception as e:
        print(f"[ERROR] 推送失败: {e}")
        return False


def pull_state():
    """从Supabase拉取最新状态快照到本地"""
    sb = load_supabase_config()
    session = get_session()
    headers = {
        "apikey": sb["key"],
        "Authorization": f"Bearer {sb['key']}",
    }

    # 列出snapshots目录下的文件，找最新的
    list_url = f"{sb['url']}/storage/v1/object/list/{sb['bucket']}"
    list_body = json.dumps({"prefix": "snapshots/", "limit": 10, "sortBy": {"column": "created_at", "order": "desc"}})
    headers["Content-Type"] = "application/json"

    try:
        if session:
            resp = session.post(list_url, headers=headers, data=list_body, timeout=30)
            files = resp.json()
        else:
            req = urllib.request.Request(list_url, data=list_body.encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                files = json.loads(resp.read())

        if not files:
            print("[WARN] Supabase上没有找到状态快照")
            return False

        latest = files[0]
        object_name = latest["name"]
        download_url = f"{sb['url']}/storage/v1/object/public/{sb['bucket']}/{object_name}"

        # 下载最新快照
        del headers["Content-Type"]
        if session:
            resp = session.get(download_url, headers=headers, timeout=30)
            state_data = resp.json()
        else:
            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                state_data = json.loads(resp.read())

        # 备份当前本地状态
        if STATE_FILE.exists():
            backup_path = STATE_FILE.with_suffix(".json.local_backup")
            STATE_FILE.rename(backup_path)
            print(f"[INFO] 本地状态已备份: {backup_path.name}")

        # 写入拉取的状态
        with open(STATE_FILE, "w") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        state_md5 = hashlib.md5(json.dumps(state_data, ensure_ascii=False).encode()).hexdigest()
        print(f"[OK] 已从Supabase拉取最新状态: {object_name}")
        print(f"     MD5: {state_md5}")
        print(f"     转数: {state_data.get('zhuan_count', '?')} | 总完成: {state_data.get('total_completed', '?')}")

        log_sync("pull", object_name, state_md5, 0)
        return True
    except Exception as e:
        print(f"[ERROR] 拉取失败: {e}")
        return False


def log_sync(action, object_path, md5, size):
    """记录同步日志"""
    log = []
    if SYNC_LOG.exists():
        with open(SYNC_LOG, "r") as f:
            log = json.load(f)
    log.append({
        "action": action,
        "object": object_path,
        "md5": md5,
        "size": size,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    # 只保留最近50条
    log = log[-50:]
    with open(SYNC_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def show_status():
    """显示同步状态"""
    sb = load_supabase_config()
    print("=== 状态同步状态 ===")
    print(f"Supabase URL: {sb['url']}")
    print(f"Bucket: {sb['bucket']}")
    print(f"本地状态文件: {STATE_FILE} {'存在' if STATE_FILE.exists() else '不存在'}")
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        print(f"本地转数: {state.get('zhuan_count', '?')}")
        print(f"本地总完成: {state.get('total_completed', '?')}")
    if SYNC_LOG.exists():
        with open(SYNC_LOG, "r") as f:
            log = json.load(f)
        print(f"\n最近同步记录({len(log)}条):")
        for entry in log[-5:]:
            print(f"  [{entry['timestamp']}] {entry['action']}: {entry['object']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 state_sync.py [push|pull|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "push":
        push_state()
    elif cmd == "pull":
        pull_state()
    elif cmd == "status":
        show_status()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
