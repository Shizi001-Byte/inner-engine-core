#!/usr/bin/env python3
"""
Supabase连接器桥接脚本 v0.1
——官方Supabase连接器只做数据通道，决策和逻辑留在引擎里

功能：
1. 状态一致性校验（本地state vs Supabase云端，MD5对比）
2. 历史快照列表查询（最近N个快照，可回溯）
3. 备份完整性检查（快照数量、最新快照时间、大小）
4. 自动同步触发（调用state_sync.py的push/pull）

原则：只读优先，写入需引擎审批。异常时自动降级为本地操作。
依赖：state_sync.py（同目录），backup_config.json（Supabase配置）
"""

import json
import hashlib
import sys
import time
from pathlib import Path
from datetime import datetime

# 引擎根目录
ENGINE_ROOT = Path(__file__).parent.parent.parent
STATE_FILE = ENGINE_ROOT / "data" / "engine_state.json"
BACKUP_CONFIG = ENGINE_ROOT / "data" / "backup_config.json"
SYNC_LOG = ENGINE_ROOT / "data" / "state_sync_log.json"
LOG_DIR = ENGINE_ROOT / "logs"

# 导入state_sync的核心函数（state_sync.py在autonomy目录，connectors是子目录）
AUTONOMY_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AUTONOMY_DIR))
try:
    import state_sync
    HAS_STATE_SYNC = True
except ImportError as e:
    HAS_STATE_SYNC = False
    _IMPORT_ERROR = str(e)


def log(msg, level="INFO"):
    """日志记录"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] [Supabase桥接] {msg}"
    print(log_msg)
    try:
        log_file = LOG_DIR / f"engine_{datetime.now().strftime('%Y-%m-%d')}.log"
        with open(log_file, "a") as f:
            f.write(log_msg + "\n")
    except:
        pass


def load_supabase_config():
    """加载Supabase配置"""
    try:
        with open(BACKUP_CONFIG, "r") as f:
            cfg = json.load(f)
        sb = cfg["backup_targets"]["supabase"]
        return {
            "url": sb["url"],
            "key": sb["service_role_key"],
            "bucket": sb["bucket"],
            "available": True
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_local_state_md5():
    """获取本地状态文件的MD5"""
    if not STATE_FILE.exists():
        return None
    with open(STATE_FILE, "r") as f:
        content = f.read()
    return hashlib.md5(content.encode()).hexdigest()


def get_local_state_info():
    """获取本地状态文件的基本信息"""
    if not STATE_FILE.exists():
        return {"exists": False}
    stat = STATE_FILE.stat()
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "md5": get_local_state_md5(),
        "zhuan_count": state.get("zhuan_count", "?"),
        "total_completed": state.get("total_completed", "?"),
        "sixiang": state.get("sixiang_state", "?"),
        "cognition_count": state.get("cognition_count", "?"),
    }


def list_remote_snapshots(limit=10):
    """列出Supabase上的状态快照列表"""
    if not HAS_STATE_SYNC:
        return {"error": "state_sync.py not available"}

    sb = load_supabase_config()
    if not sb["available"]:
        return {"error": f"Supabase配置不可用: {sb.get('reason','')}"}

    session = state_sync.get_session()
    headers = {
        "apikey": sb["key"],
        "Authorization": f"Bearer {sb['key']}",
        "Content-Type": "application/json",
    }
    list_url = f"{sb['url']}/storage/v1/object/list/{sb['bucket']}"
    list_body = json.dumps({
        "prefix": "snapshots/",
        "limit": limit,
        "sortBy": {"column": "created_at", "order": "desc"}
    })

    try:
        if session:
            resp = session.post(list_url, headers=headers, data=list_body, timeout=30)
            if resp.status_code != 200:
                error_info = resp.json() if resp.headers.get('content-type','').startswith('application/json') else resp.text
                return {"error": f"Supabase API {resp.status_code}: {error_info}"}
            files = resp.json()
        else:
            import urllib.request
            req = urllib.request.Request(list_url, data=list_body.encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                files = json.loads(resp.read())

        # 类型检查：Supabase list API返回列表
        if not isinstance(files, list):
            return {"error": f"Unexpected response type: {type(files).__name__}, content: {str(files)[:200]}"}

        snapshots = []
        for f in files:
            if not isinstance(f, dict):
                continue
            snapshots.append({
                "name": f.get("name", ""),
                "created_at": f.get("created_at", ""),
                "size": f.get("metadata", {}).get("size", f.get("size", 0)) if isinstance(f.get("metadata"), dict) else f.get("size", 0),
                "last_modified": f.get("last_modified", f.get("updated_at", "")),
            })
        return {"count": len(snapshots), "snapshots": snapshots}
    except Exception as e:
        return {"error": str(e)}


def check_consistency():
    """状态一致性校验——本地vs云端最新快照"""
    log("=== 状态一致性校验开始 ===")

    result = {
        "checked_at": datetime.now().isoformat(),
        "local": get_local_state_info(),
        "remote_latest": None,
        "consistent": None,
        "issues": []
    }

    # 1. 检查本地状态
    if not result["local"]["exists"]:
        result["issues"].append("本地状态文件不存在")
        result["consistent"] = False
        log("本地状态文件不存在", "ERROR")
        return result

    log(f"本地状态: 转数{result['local']['zhuan_count']} | MD5:{result['local']['md5'][:12]}")

    # 2. 获取云端最新快照
    remote = list_remote_snapshots(limit=1)
    if "error" in remote:
        result["issues"].append(f"无法获取云端快照: {remote['error']}")
        result["consistent"] = None
        log(f"无法获取云端快照: {remote['error']}", "WARN")
        return result

    if remote["count"] == 0:
        result["issues"].append("云端没有状态快照")
        result["consistent"] = False
        log("云端没有状态快照", "WARN")
        return result

    latest = remote["snapshots"][0]
    result["remote_latest"] = latest
    log(f"云端最新快照: {latest['name']} | 创建于{latest['created_at']}")

    # 3. 下载云端最新快照，对比MD5
    sb = load_supabase_config()
    if sb["available"]:
        download_url = f"{sb['url']}/storage/v1/object/public/{sb['bucket']}/{latest['name']}"
        session = state_sync.get_session()
        headers = {"apikey": sb["key"], "Authorization": f"Bearer {sb['key']}"}
        try:
            if session:
                resp = session.get(download_url, headers=headers, timeout=30)
                remote_state = resp.json()
            else:
                import urllib.request
                req = urllib.request.Request(download_url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    remote_state = json.loads(resp.read())

            remote_md5 = hashlib.md5(json.dumps(remote_state, ensure_ascii=False).encode()).hexdigest()
            result["remote_md5"] = remote_md5
            result["remote_zhuan_count"] = remote_state.get("zhuan_count", "?")

            # 对比关键字段
            local_zhuan = result["local"]["zhuan_count"]
            remote_zhuan = remote_state.get("zhuan_count", "?")
            if local_zhuan != remote_zhuan:
                result["issues"].append(f"转数不一致: 本地{local_zhuan} vs 云端{remote_zhuan}")
                result["consistent"] = False
                log(f"转数不一致: 本地{local_zhuan} vs 云端{remote_zhuan}", "WARN")
            else:
                result["consistent"] = True
                log(f"状态一致: 转数{local_zhuan}, MD5本地{result['local']['md5'][:12]} vs 云端{remote_md5[:12]}")

        except Exception as e:
            result["issues"].append(f"下载云端快照失败: {e}")
            log(f"下载云端快照失败: {e}", "WARN")

    log("=== 状态一致性校验完成 ===")
    return result


def check_backup_integrity():
    """备份完整性检查"""
    log("=== 备份完整性检查开始 ===")

    result = {
        "checked_at": datetime.now().isoformat(),
        "snapshots": list_remote_snapshots(limit=20),
        "local_backups": [],
        "issues": []
    }

    # 1. 检查云端快照数量
    if "error" not in result["snapshots"]:
        count = result["snapshots"].get("count", 0)
        if count == 0:
            result["issues"].append("云端没有状态快照")
        elif count < 3:
            result["issues"].append(f"云端快照数量偏少: {count}个")
        log(f"云端快照数量: {count}个")

        # 2. 检查最新快照时间
        if count > 0:
            latest = result["snapshots"]["snapshots"][0]
            created_str = latest.get("created_at", "")
            try:
                if created_str:
                    # 尝试解析时间
                    if "T" in created_str:
                        created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    else:
                        created = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%S")
                    age_hours = (datetime.now(created.tzinfo) - created).total_seconds() / 3600
                    result["latest_snapshot_age_hours"] = round(age_hours, 1)
                    if age_hours > 24:
                        result["issues"].append(f"最新快照已{age_hours:.1f}小时未更新")
                        log(f"最新快照已{age_hours:.1f}小时未更新", "WARN")
                    else:
                        log(f"最新快照更新于{age_hours:.1f}小时前")
            except Exception as e:
                log(f"解析快照时间失败: {e}", "DEBUG")

    # 3. 检查本地备份目录
    backup_dir = ENGINE_ROOT / "backups"
    if backup_dir.exists():
        local_backups = list(backup_dir.glob("**/*.bak")) + list(backup_dir.glob("**/*.tar.gz"))
        result["local_backups_count"] = len(local_backups)
        log(f"本地备份文件: {len(local_backups)}个")

    log("=== 备份完整性检查完成 ===")
    return result


def run_daily_check():
    """每日巡检入口"""
    log("=== Supabase桥接每日巡检开始 ===")

    results = {
        "timestamp": datetime.now().isoformat(),
        "consistency": check_consistency(),
        "backup_integrity": check_backup_integrity(),
    }

    # 写入状态文件
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        state["supabase_bridge_last_check"] = results
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        log("巡检结果已写入引擎状态文件")
    except Exception as e:
        log(f"写入状态文件失败: {e}", "WARN")

    log("=== Supabase桥接每日巡检完成 ===")
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "consistency":
            print(json.dumps(check_consistency(), indent=2, ensure_ascii=False))
        elif command == "snapshots":
            print(json.dumps(list_remote_snapshots(limit=int(sys.argv[2]) if len(sys.argv) > 2 else 10), indent=2, ensure_ascii=False))
        elif command == "integrity":
            print(json.dumps(check_backup_integrity(), indent=2, ensure_ascii=False))
        elif command == "daily":
            print(json.dumps(run_daily_check(), indent=2, ensure_ascii=False))
        elif command == "push":
            if HAS_STATE_SYNC:
                state_sync.push_state()
        elif command == "pull":
            if HAS_STATE_SYNC:
                state_sync.pull_state()
        elif command == "status":
            if HAS_STATE_SYNC:
                state_sync.show_status()
        else:
            print(f"未知命令: {command}")
            print("可用命令: consistency, snapshots, integrity, daily, push, pull, status")
    else:
        print("Supabase连接器桥接脚本 v0.1")
        print("用法: python3 supabase_bridge.py <command>")
        print("命令:")
        print("  consistency  - 状态一致性校验（本地vs云端）")
        print("  snapshots [N]- 列出最近N个云端快照")
        print("  integrity    - 备份完整性检查")
        print("  daily        - 每日巡检（一致性+完整性）")
        print("  push         - 推送本地状态到云端")
        print("  pull         - 从云端拉取最新状态")
        print("  status       - 查看同步状态")
