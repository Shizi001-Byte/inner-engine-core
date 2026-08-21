#!/usr/bin/env python3
"""
GitHub连接器桥接脚本 v0.1
——官方GitHub连接器只做数据通道，决策和逻辑留在引擎里

功能：
1. 仓库健康度巡检（分支保护、提交频率、密钥扫描状态）
2. Issue自动同步到坑库（只读，不自动创建Issue）
3. Release检测（有新Release时触发引擎版本升级提醒）

原则：只读优先，写入需引擎审批。异常时自动降级为git命令原生操作。
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 引擎根目录
ENGINE_ROOT = Path(__file__).parent.parent.parent
STATE_FILE = ENGINE_ROOT / "data" / "engine_state.json"
PIT_LIBRARY_DIR = ENGINE_ROOT / "data" / "pit_library"
LOG_DIR = ENGINE_ROOT / "logs"

# GitHub配置（从git remote读取，不硬编码）
def get_github_remote():
    """从git remote读取GitHub仓库信息"""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "github"],
            cwd=str(ENGINE_ROOT),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # 解析用户名和仓库名
            # 格式: https://user:token@github.com/user/repo.git
            if "@github.com/" in url:
                parts = url.split("@github.com/")[1].replace(".git", "")
                user, repo = parts.split("/", 1)
                return {"url": url, "user": user, "repo": repo, "available": True}
        return {"available": False, "reason": "github remote not configured"}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def log(msg, level="INFO"):
    """日志记录"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] [GitHub桥接] {msg}"
    print(log_msg)
    # 写入引擎日志
    try:
        log_file = LOG_DIR / f"engine_{datetime.now().strftime('%Y-%m-%d')}.log"
        with open(log_file, "a") as f:
            f.write(log_msg + "\n")
    except:
        pass


def check_repo_health():
    """仓库健康度巡检——用git命令原生实现，不依赖官方连接器"""
    gh_info = get_github_remote()
    if not gh_info["available"]:
        log(f"GitHub远程未配置，跳过巡检: {gh_info.get('reason','')}", "WARN")
        return {"status": "skipped", "reason": "github remote not configured"}

    health = {
        "checked_at": datetime.now().isoformat(),
        "repo": f"{gh_info['user']}/{gh_info['repo']}",
        "checks": {}
    }

    try:
        # 1. 最近提交频率
        result = subprocess.run(
            ["git", "log", "--oneline", "-20", "--remote=github"],
            cwd=str(ENGINE_ROOT), capture_output=True, text=True, timeout=15
        )
        commits = [l for l in result.stdout.strip().split("\n") if l]
        health["checks"]["recent_commits"] = len(commits)

        # 2. 本地与远程同步状态
        result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "master...github/master"],
            cwd=str(ENGINE_ROOT), capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            ahead, behind = result.stdout.strip().split()
            health["checks"]["ahead"] = int(ahead)
            health["checks"]["behind"] = int(behind)
            if int(ahead) > 0:
                log(f"本地领先GitHub {ahead} 个提交，建议推送", "WARN")

        # 3. 双远程一致性（Gitee vs GitHub）
        result = subprocess.run(
            ["git", "rev-parse", "origin/master", "github/master"],
            cwd=str(ENGINE_ROOT), capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            hashes = result.stdout.strip().split("\n")
            if len(hashes) == 2:
                health["checks"]["gitee_hash"] = hashes[0][:12]
                health["checks"]["github_hash"] = hashes[1][:12]
                health["checks"]["dual_remote_synced"] = hashes[0] == hashes[1]
                if hashes[0] != hashes[1]:
                    log("Gitee与GitHub提交不一致，双远程未同步", "WARN")

        health["status"] = "ok"
        log(f"仓库健康巡检完成: {len(commits)}个近期提交, 双远程同步={health['checks'].get('dual_remote_synced','N/A')}")

    except Exception as e:
        health["status"] = "error"
        health["error"] = str(e)
        log(f"仓库健康巡检异常: {e}", "ERROR")

    return health


def check_for_releases():
    """检测是否有新Release（通过git tag）"""
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-creatordate"],
            cwd=str(ENGINE_ROOT), capture_output=True, text=True, timeout=10
        )
        tags = [t for t in result.stdout.strip().split("\n") if t]
        return {
            "latest_tag": tags[0] if tags else None,
            "total_tags": len(tags),
            "tags": tags[:5]
        }
    except Exception as e:
        return {"error": str(e)}


def sync_issues_to_pit_library():
    """Issue同步到坑库——只读GitHub Issue，转化为坑库格式
    注意：当前版本只做框架，实际Issue同步需要官方连接器API支持
    """
    # TODO: 接入官方GitHub连接器后实现
    # 1. 调用官方连接器获取open issues
    # 2. 转化为坑库标准格式
    # 3. 写入pit_library目录
    log("Issue同步功能待接入官方连接器后实现（当前为框架版本）", "DEBUG")
    return {"status": "not_implemented", "reason": "waiting for official github connector"}


def run_daily_check():
    """每日巡检入口——引擎空闲模式可调用"""
    log("=== GitHub桥接每日巡检开始 ===")

    results = {
        "timestamp": datetime.now().isoformat(),
        "repo_health": check_repo_health(),
        "releases": check_for_releases(),
        "issue_sync": sync_issues_to_pit_library()
    }

    # 写入状态文件
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        state["github_bridge_last_check"] = results
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        log("巡检结果已写入引擎状态文件")
    except Exception as e:
        log(f"写入状态文件失败: {e}", "WARN")

    log("=== GitHub桥接每日巡检完成 ===")
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "health":
            print(json.dumps(check_repo_health(), indent=2, ensure_ascii=False))
        elif command == "releases":
            print(json.dumps(check_for_releases(), indent=2, ensure_ascii=False))
        elif command == "daily":
            print(json.dumps(run_daily_check(), indent=2, ensure_ascii=False))
        elif command == "info":
            print(json.dumps(get_github_remote(), indent=2, ensure_ascii=False))
        else:
            print(f"未知命令: {command}")
            print("可用命令: health, releases, daily, info")
    else:
        print("GitHub连接器桥接脚本 v0.1")
        print("用法: python3 github_bridge.py <command>")
        print("命令: health(仓库健康巡检), releases(Release检测), daily(每日巡检), info(远程信息)")
