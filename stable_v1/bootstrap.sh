#!/bin/bash
# 凡心引擎冷启动入口 - 沙箱重启后自动恢复
ENGINE_DIR="/sandboxdata/workspace/file/engine_v7_2"
PID_FILE="$ENGINE_DIR/data/engine.pid"
STATE_FILE="$ENGINE_DIR/data/engine_state.json"
LOG_FILE="$ENGINE_DIR/logs/bootstrap.log"

cd "$ENGINE_DIR" || exit 1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 冷启动开始 ===" >> "$LOG_FILE"

# 1. 清理僵尸PID
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
        echo "清理僵尸PID: $OLD_PID" >> "$LOG_FILE"
        rm -f "$PID_FILE"
        # 清零in_flight
        python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    for k in list(s.keys()):
        if 'in_flight' in k:
            s[k] = 0
    for ek in ['engine_a','engine_b','engine_c']:
        if ek in s:
            s[ek]['in_flight_tokens'] = 0
    json.dump(s, open('$STATE_FILE','w'), indent=2, ensure_ascii=False)
    print('in_flight已清零')
except Exception as e:
    print(f'清零失败: {e}')
" >> "$LOG_FILE" 2>&1
    fi
fi

# 2. 启动看门狗
if ! pgrep -f "watchdog_daemon.py" > /dev/null; then
    nohup python3 "$ENGINE_DIR/stable_v1/watchdog_daemon.py" >> "$ENGINE_DIR/logs/watchdog.log" 2>&1 &
    echo "看门狗已启动 PID: $!" >> "$LOG_FILE"
fi

# 3. 启动引擎
if ! pgrep -f "engine_zhuan1.py" > /dev/null; then
    rm -f "$PID_FILE"
    nohup python3 autonomy/engine_zhuan1.py >> logs/daemon_zhuan1_stdout.log 2>&1 &
    echo "引擎已启动 PID: $!" >> "$LOG_FILE"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 冷启动完成 ===" >> "$LOG_FILE"
