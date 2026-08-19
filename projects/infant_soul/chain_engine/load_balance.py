#!/usr/bin/env python3
"""
load_balance.py — 负载均衡保护（模块2.4）

单节点算力达到阈值自动分流，避免单账号拉满宕机。
对应「分布式丹田」：把负载平摊到多个模型/多个会话。

用法：
  python3 load_balance.py status          # 查看当前负载状态
  python3 load_balance.py check           # 检查是否需要分流
  python3 load_balance.py history         # 查看负载历史
  python3 load_balance.py set-threshold 80 # 设置告警阈值(%)
"""

import json
import time
import sys
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LOAD_LOG = DATA_DIR / "load_history.json"
CONFIG_FILE = DATA_DIR / "load_balance_config.json"

DEFAULT_CONFIG = {
    "cpu_threshold": 80,        # CPU使用率告警阈值%
    "memory_threshold": 85,     # 内存使用率告警阈值%
    "token_rate_threshold": 50, # 每分钟token消耗告警阈值
    "cooldown_seconds": 300,    # 分流后冷却时间
    "last_alert": None,
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    cfg = DEFAULT_CONFIG.copy()
    save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_system_load():
    """获取当前系统负载"""
    load = {}
    # CPU使用率（通过/proc/loadavg）
    try:
        with open("/proc/loadavg", "r") as f:
            loadavg = f.read().split()
        load["cpu_load_1m"] = float(loadavg[0])
        load["cpu_load_5m"] = float(loadavg[1])
        # CPU核心数
        with open("/proc/cpuinfo", "r") as f:
            cores = f.read().count("processor")
        load["cpu_cores"] = cores
        load["cpu_percent"] = round((load["cpu_load_1m"] / cores) * 100, 1)
    except:
        load["cpu_percent"] = 0

    # 内存使用率
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        total = int([l for l in meminfo.split("\n") if "MemTotal" in l][0].split()[1])
        available = int([l for l in meminfo.split("\n") if "MemAvailable" in l][0].split()[1])
        load["mem_total_mb"] = round(total / 1024, 1)
        load["mem_available_mb"] = round(available / 1024, 1)
        load["mem_percent"] = round((1 - available / total) * 100, 1)
    except:
        load["mem_percent"] = 0

    load["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return load


def check_need_balance():
    """检查是否需要分流"""
    cfg = load_config()
    load = get_system_load()
    alerts = []

    if load["cpu_percent"] > cfg["cpu_threshold"]:
        alerts.append(f"CPU过高: {load['cpu_percent']}% > {cfg['cpu_threshold']}%")
    if load["mem_percent"] > cfg["memory_threshold"]:
        alerts.append(f"内存过高: {load['mem_percent']}% > {cfg['memory_threshold']}%")

    # 记录负载历史
    history = []
    if LOAD_LOG.exists():
        with open(LOAD_LOG, "r") as f:
            history = json.load(f)
    history.append(load)
    history = history[-200:]  # 保留最近200条
    with open(LOAD_LOG, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    if alerts:
        # 检查冷却时间
        if cfg.get("last_alert"):
            last = time.mktime(time.strptime(cfg["last_alert"], "%Y-%m-%dT%H:%M:%S"))
            if time.time() - last < cfg["cooldown_seconds"]:
                return load, [], "冷却中，暂不分流"

        cfg["last_alert"] = load["timestamp"]
        save_config(cfg)
        return load, alerts, "需要分流！建议：1.暂停重度任务 2.切换到轻量模型 3.任务排队等待"

    return load, [], "负载正常"


def show_status():
    """显示当前负载状态"""
    load = get_system_load()
    cfg = load_config()
    print("=== 系统负载状态 ===")
    print(f"CPU: {load['cpu_percent']}% (阈值{cfg['cpu_threshold']}%)")
    print(f"内存: {load['mem_percent']}% (阈值{cfg['memory_threshold']}%)")
    if "mem_total_mb" in load:
        print(f"内存总量: {load['mem_total_mb']}MB | 可用: {load['mem_available_mb']}MB")

    load, alerts, action = check_need_balance()
    if alerts:
        print(f"\n⚠️ 告警: {'; '.join(alerts)}")
        print(f"建议: {action}")
    else:
        print(f"\n✓ {action}")


def show_history():
    """显示负载历史"""
    if not LOAD_LOG.exists():
        print("暂无负载历史")
        return
    with open(LOAD_LOG, "r") as f:
        history = json.load(f)
    print(f"=== 负载历史（最近{len(history)}条）===")
    for h in history[-10:]:
        cpu = h.get("cpu_percent", 0)
        mem = h.get("mem_percent", 0)
        alert = "⚠️" if cpu > 80 or mem > 85 else " "
        print(f"  {alert} [{h['timestamp']}] CPU:{cpu}% MEM:{mem}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 load_balance.py [status|check|history|set-threshold]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        show_status()
    elif cmd == "check":
        load, alerts, action = check_need_balance()
        print(f"CPU:{load['cpu_percent']}% MEM:{load['mem_percent']}%")
        if alerts:
            print(f"告警: {'; '.join(alerts)}")
        print(action)
    elif cmd == "history":
        show_history()
    elif cmd == "set-threshold" and len(sys.argv) > 2:
        cfg = load_config()
        cfg["cpu_threshold"] = int(sys.argv[2])
        save_config(cfg)
        print(f"CPU阈值已设为: {sys.argv[2]}%")
    else:
        print("参数错误")
