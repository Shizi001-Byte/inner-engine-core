#!/usr/bin/env python3
"""凡心引擎独立看门狗 - 每60秒检查引擎状态，挂了自动拉起"""
import os, time, json, subprocess
from datetime import datetime

ENGINE_DIR = "/sandboxdata/workspace/file/engine_v7_2"
PID_FILE = f"{ENGINE_DIR}/data/engine.pid"
STATE_FILE = f"{ENGINE_DIR}/data/engine_state.json"
LOG_FILE = f"{ENGINE_DIR}/logs/watchdog.log"
CHECK_INTERVAL = 60
MAX_RESTARTS = 100

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def is_engine_running():
    if not os.path.exists(PID_FILE):
        return False
    try:
        pid = int(open(PID_FILE).read().strip())
        return os.path.exists(f"/proc/{pid}")
    except:
        return False

def cleanup_zombie():
    """清理僵尸状态"""
    try:
        if os.path.exists(STATE_FILE):
            s = json.load(open(STATE_FILE))
            for k in list(s.keys()):
                if 'in_flight' in k:
                    s[k] = 0
            for ek in ['engine_a','engine_b','engine_c']:
                if ek in s and 'in_flight_tokens' in s[ek]:
                    s[ek]['in_flight_tokens'] = 0
            json.dump(s, open(STATE_FILE,'w'), indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"清理僵尸状态失败: {e}")

def start_engine():
    cleanup_zombie()
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    subprocess.Popen(
        ["python3", "autonomy/engine_zhuan1.py"],
        cwd=ENGINE_DIR,
        stdout=open(f"{ENGINE_DIR}/logs/daemon_zhuan1_stdout.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    log("引擎已拉起")

if __name__ == "__main__":
    log(f"看门狗启动 | 检查间隔{CHECK_INTERVAL}s")
    restarts = 0
    while restarts < MAX_RESTARTS:
        if not is_engine_running():
            restarts += 1
            log(f"引擎未运行，第{restarts}次拉起")
            start_engine()
            time.sleep(10)
        time.sleep(CHECK_INTERVAL)
    log("达到最大重启次数，看门狗退出")
