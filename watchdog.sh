#!/bin/bash
# 凡心引擎看门狗：检测进程不存在则自动重启
# 用法：nohup bash watchdog.sh >> logs/watchdog.log 2>&1 &
# PIT-082修复：动态检测引擎目录，不再硬编码绝对路径
# 优先用环境变量ENGINE_DIR，否则用脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="${ENGINE_DIR:-$SCRIPT_DIR}"
ENGINE_SCRIPT="autonomy/engine_zhuan1.py"
PID_FILE="$ENGINE_DIR/data/engine.pid"
LOG_DIR="$ENGINE_DIR/logs"
MAX_RESTARTS=100
RESTART_INTERVAL=10
CRASH_WINDOW=600
CRASH_THRESHOLD=3
restart_count=0
crash_timestamps=()
cd "$ENGINE_DIR" || exit 1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 看门狗启动 | 引擎目录:$ENGINE_DIR"
while true; do
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            sleep 15
            continue
        fi
    fi
    now=$(date +%s)
    crash_timestamps=($(for t in "${crash_timestamps[@]}"; do
        [ $((now - t)) -lt $CRASH_WINDOW ] && echo "$t"
    done))
    crash_timestamps+=("$now")
    crash_in_window=${#crash_timestamps[@]}
    if [ "$crash_in_window" -ge "$CRASH_THRESHOLD" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 警告: 10分钟内崩溃${crash_in_window}次，自动降并发到2路"
        python3 -c "
import json
f = '$ENGINE_DIR/data/engine_state.json'
d = json.load(open(f))
d['concurrency_override'] = 2
json.dump(d, open(f,'w'), ensure_ascii=False, indent=2)
print('并发已降为2路')
" 2>/dev/null
    fi
    restart_count=$((restart_count + 1))
    if [ "$restart_count" -gt "$MAX_RESTARTS" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 达到最大重启次数$MAX_RESTARTS，看门狗退出"
        exit 1
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 引擎未运行，第${restart_count}次重启 | 10分钟内崩溃${crash_in_window}次"
    # P0修复：先删PID，启动引擎，等待引擎自己写PID，避免竞态
    rm -f "$PID_FILE"
    cd "$ENGINE_DIR"
    nohup python3 "$ENGINE_SCRIPT" >> "$LOG_DIR/daemon_zhuan1_stdout.log" 2>&1 &
    new_pid=$!
    sleep 3
    if [ -f "$PID_FILE" ]; then
        actual_pid=$(cat "$PID_FILE" 2>/dev/null)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 引擎已重启，PID:$actual_pid (引擎自写)"
    else
        echo "$new_pid" > "$PID_FILE"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 引擎已重启，PID:$new_pid (看门狗兜底写)"
    fi
    sleep "$RESTART_INTERVAL"
done
