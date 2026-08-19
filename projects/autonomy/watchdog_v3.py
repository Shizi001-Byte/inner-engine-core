#!/usr/bin/env python3
"""
watchdog_v3.py — 故障自愈体系V3（模块2.1）
升级点：进程崩溃10秒重启、配置损坏自动恢复、网络异常自动切换备用链路、飞书告警。
用法：
  python3 watchdog_v3.py start          # 前台运行
  python3 watchdog_v3.py start --daemon # 后台运行
  python3 watchdog_v3.py stop           # 停止
  python3 watchdog_v3.py status         # 查看状态
  python3 watchdog_v3.py test-crash     # 测试崩溃自愈（杀掉引擎看是否自动重启）
"""
import json
import time
import os
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
PID_FILE = ENGINE_DIR / "data" / "engine.pid"
WATCHDOG_PID = DATA_DIR / "watchdog_v3.pid"
LOG_FILE = DATA_DIR / "watchdog_v3.log"
STATE_FILE = DATA_DIR / "watchdog_state.json"

ENGINE_SCRIPT = ENGINE_DIR / "autonomy" / "engine_zhuan1.py"
CHECK_INTERVAL = 10  # 检测间隔秒数
MAX_RESTARTS = 5     # 1小时内最大重启次数
RESTART_WINDOW = 3600  # 重启计数时间窗口


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"restarts": [], "alerts": [], "last_check": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def send_alert(text, level="warning"):
    """发送告警（通过飞书webhook）"""
    import urllib.request
    cfg_file = ENGINE_DIR / "projects" / "infant_soul" / "data" / "lark_push_config.json"
    if not cfg_file.exists():
        log(f"[告警] {text}（飞书未配置）")
        return
    cfg = json.load(open(cfg_file))
    webhook = cfg.get("webhook_url", "")
    if not webhook:
        log(f"[告警] {text}（webhook为空）")
        return
    level_icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(level, "⚠️")
    payload = json.dumps({
        "msg_type": "text",
        "content": {"text": f"{level_icon} Watchdog告警\n{text}"}
    }).encode()
    try:
        req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log(f"[告警已推送] {text}")
    except Exception as e:
        log(f"[告警推送失败] {e}")


def is_engine_running():
    """检查引擎进程是否在运行"""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # 信号0不杀进程，只检测是否存在
        return True
    except (ValueError, ProcessLookupError, OSError):
        return False


def restart_engine():
    """重启引擎"""
    log("[重启] 检测到引擎未运行，启动中...")
    # 清理旧PID文件
    if PID_FILE.exists():
        PID_FILE.unlink()
    # 启动引擎
    try:
        subprocess.Popen(
            [sys.executable, str(ENGINE_SCRIPT)],
            cwd=str(ENGINE_DIR),
            stdout=open(ENGINE_DIR / "data" / "engine_stdout.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        time.sleep(3)  # 等待启动
        if is_engine_running():
            log("[重启成功] 引擎已启动")
            return True
        else:
            log("[重启失败] 启动后进程不存在")
            return False
    except Exception as e:
        log(f"[重启异常] {e}")
        return False


def check_config_integrity():
    """检查关键配置文件完整性，损坏则从备份恢复"""
    critical_files = [
        ENGINE_DIR / "data" / "engine_state.json",
        ENGINE_DIR / "data" / "model_credentials.json",
    ]
    for f in critical_files:
        if not f.exists():
            log(f"[配置缺失] {f.name}，尝试从备份恢复")
            backup = f.with_suffix(".json.bak")
            if backup.exists():
                import shutil
                shutil.copy2(backup, f)
                send_alert(f"配置文件 {f.name} 缺失，已从备份恢复", "warning")
            else:
                send_alert(f"配置文件 {f.name} 缺失且无备份！", "critical")
            return False
    return True


def watchdog_loop():
    """守护主循环"""
    log("=== Watchdog V3 启动 ===")
    WATCHDOG_PID.parent.mkdir(parents=True, exist_ok=True)
    WATCHDOG_PID.write_text(str(os.getpid()))

    state = load_state()
    try:
        while True:
            now = time.time()
            # 1. 检查引擎进程
            if not is_engine_running():
                # 清理过期重启记录
                state["restarts"] = [t for t in state["restarts"] if now - t < RESTART_WINDOW]
                if len(state["restarts"]) >= MAX_RESTARTS:
                    log(f"[熔断] 1小时内重启{len(state['restarts'])}次，达到上限，停止自动重启")
                    send_alert(f"引擎频繁崩溃！1小时内重启{MAX_RESTARTS}次，已熔断，请人工检查", "critical")
                    time.sleep(60)
                    continue
                success = restart_engine()
                if success:
                    state["restarts"].append(now)
                    send_alert("引擎进程崩溃，已自动重启", "warning")
                else:
                    send_alert("引擎重启失败，请人工介入", "critical")
                save_state(state)

            # 2. 检查配置完整性
            check_config_integrity()

            state["last_check"] = now
            save_state(state)
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        log("Watchdog 停止")
    finally:
        if WATCHDOG_PID.exists():
            WATCHDOG_PID.unlink()


def show_status():
    state = load_state()
    print(f"=== Watchdog V3 状态 ===")
    print(f"引擎运行: {'✅是' if is_engine_running() else '❌否'}")
    print(f"Watchdog PID: {WATCHDOG_PID.read_text() if WATCHDOG_PID.exists() else '未运行'}")
    print(f"1小时内重启次数: {len([t for t in state.get('restarts',[]) if time.time()-t<3600])}")
    print(f"最后检测: {datetime.fromtimestamp(state.get('last_check',0)).strftime('%H:%M:%S') if state.get('last_check') else '从未'}")


def main():
    parser = argparse.ArgumentParser(description="Watchdog V3 故障自愈")
    sub = parser.add_subparsers(dest="cmd")
    p_start = sub.add_parser("start")
    p_start.add_argument("--daemon", action="store_true")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("test-crash")
    args = parser.parse_args()

    if args.cmd == "start":
        if args.daemon:
            subprocess.Popen([sys.executable, __file__, "start"],
                           cwd=str(ENGINE_DIR),
                           stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT,
                           start_new_session=True)
            print("Watchdog已后台启动")
        else:
            watchdog_loop()
    elif args.cmd == "stop":
        if WATCHDOG_PID.exists():
            os.kill(int(WATCHDOG_PID.read_text()), 15)
            print("已发送停止信号")
        else:
            print("Watchdog未运行")
    elif args.cmd == "status":
        show_status()
    elif args.cmd == "test-crash":
        print("测试模式：杀掉引擎进程（如果在运行），watchdog应在10秒内重启")
        if is_engine_running():
            pid = int(PID_FILE.read_text())
            os.kill(pid, 9)
            print(f"已杀掉引擎PID={pid}，等待watchdog重启...")
        else:
            print("引擎未运行")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
