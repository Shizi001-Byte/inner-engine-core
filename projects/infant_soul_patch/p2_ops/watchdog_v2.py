#!/usr/bin/env python3
"""
watchdog_v2.py — Watchdog增强版（P2.1）

进程监控+10秒自动重启+异常飞书告警，宕机即时通知。

用法：
  python3 watchdog_v2.py start       # 启动守护（后台运行）
  python3 watchdog_v2.py stop        # 停止守护
  python3 watchdog_v2.py status      # 查看守护状态
  python3 watchdog_v2.py check       # 手动检查一次引擎状态
  python3 watchdog_v2.py test-alert  # 测试飞书告警
"""

import json
import time
import subprocess
import sys
import os
import signal
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
ENGINE_SCRIPT = ENGINE_DIR / "autonomy" / "engine_zhuan1.py"
PID_FILE = ENGINE_DIR / "data" / "engine.pid"
WATCHDOG_PID = Path(__file__).parent.parent / "data" / "watchdog_v2.pid"
WATCHDOG_LOG = Path(__file__).parent.parent / "data" / "watchdog_v2.log"
PUSH_CONFIG = Path(__file__).parent.parent.parent / "infant_soul" / "data" / "lark_push_config.json"

CHECK_INTERVAL = 10  # 10秒检查一次
MAX_RESTARTS = 5     # 最大重启次数（1小时内）
RESTART_WINDOW = 3600  # 重启计数窗口1小时


def send_alert(message):
    """发送飞书告警"""
    if not PUSH_CONFIG.exists():
        return False
    with open(PUSH_CONFIG, "r") as f:
        cfg = json.load(f)
    webhook = cfg.get("webhook_url", "")
    if not webhook:
        return False

    import urllib.request
    payload = json.dumps({
        "msg_type": "text",
        "content": {"text": f"⚠️ [凡心引擎告警] {message}\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"}
    }).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("code") == 0
    except:
        return False


def is_engine_running():
    """检查引擎是否在运行"""
    if not PID_FILE.exists():
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # 发送信号0，检查进程是否存在
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def restart_engine():
    """重启引擎"""
    print(f"[{time.strftime('%H:%M:%S')}] 重启引擎...")
    # 移除旧PID文件（避免竞态bug）
    if PID_FILE.exists():
        PID_FILE.unlink()
    # 启动引擎
    log_file = ENGINE_DIR / "data" / f"watchdog_restart_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_file, "w") as f:
        proc = subprocess.Popen(
            ["python3", str(ENGINE_SCRIPT)],
            cwd=str(ENGINE_DIR),
            stdout=f, stderr=subprocess.STDOUT,
            start_new_session=True
        )
    time.sleep(3)
    if is_engine_running():
        print(f"[{time.strftime('%H:%M:%S')}] 引擎重启成功，PID: {proc.pid}")
        return True
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 引擎重启失败")
        return False


def check_once(restart_history):
    """检查一次引擎状态"""
    if is_engine_running():
        return True, restart_history

    print(f"[{time.strftime('%H:%M:%S')}] 检测到引擎未运行！")
    send_alert("引擎进程已退出，正在自动重启...")

    # 检查重启频率
    now = time.time()
    restart_history = [t for t in restart_history if now - t < RESTART_WINDOW]
    if len(restart_history) >= MAX_RESTARTS:
        msg = f"引擎1小时内重启{len(restart_history)}次，超过阈值{MAX_RESTARTS}，停止自动重启，请人工检查！"
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
        send_alert(msg)
        return False, restart_history

    success = restart_engine()
    if success:
        restart_history.append(now)
        send_alert("引擎已自动重启成功")
    else:
        send_alert("引擎自动重启失败，请人工检查！")
    return success, restart_history


def run_daemon():
    """运行守护进程"""
    print(f"Watchdog v2 启动，检查间隔: {CHECK_INTERVAL}秒")
    print(f"引擎脚本: {ENGINE_SCRIPT}")
    restart_history = []

    # 写入守护PID
    with open(WATCHDOG_PID, "w") as f:
        f.write(str(os.getpid()))

    try:
        while True:
            _, restart_history = check_once(restart_history)
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        print("\nWatchdog 已停止")
    finally:
        if WATCHDOG_PID.exists():
            WATCHDOG_PID.unlink()


def stop_daemon():
    """停止守护进程"""
    if not WATCHDOG_PID.exists():
        print("Watchdog未在运行")
        return
    with open(WATCHDOG_PID, "r") as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Watchdog已停止 (PID: {pid})")
    except ProcessLookupError:
        print("Watchdog进程不存在")
    if WATCHDOG_PID.exists():
        WATCHDOG_PID.unlink()


def show_status():
    """显示状态"""
    print("=== Watchdog v2 状态 ===")
    print(f"引擎运行: {'✓是' if is_engine_running() else '✗否'}")
    print(f"守护进程: {'✓运行中' if WATCHDOG_PID.exists() else '✗未运行'}")
    if WATCHDOG_PID.exists():
        with open(WATCHDOG_PID, "r") as f:
            print(f"守护PID: {f.read().strip()}")
    print(f"检查间隔: {CHECK_INTERVAL}秒")
    print(f"最大重启: {MAX_RESTARTS}次/小时")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 watchdog_v2.py [start|stop|status|check|test-alert]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start":
        run_daemon()
    elif cmd == "stop":
        stop_daemon()
    elif cmd == "status":
        show_status()
    elif cmd == "check":
        check_once([])
    elif cmd == "test-alert":
        if send_alert("这是一条测试告警，Watchdog v2连通正常"):
            print("测试告警发送成功")
        else:
            print("测试告警发送失败")
    else:
        print("参数错误")
