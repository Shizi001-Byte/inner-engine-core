#!/bin/bash
# 凡心引擎·健康守卫（外层守护）
# 功能：每分钟检查引擎和看门狗进程，挂了自动重启
# 用法：由cron每分钟调用一次
# 设计原则：无状态、幂等、不依赖引擎内部机制

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR"
ENGINE_SCRIPT="autonomy/engine_zhuan1.py"
PID_FILE="$ENGINE_DIR/data/engine.pid"
LOG_DIR="$ENGINE_DIR/logs"
HEARTBEAT_FILE="$ENGINE_DIR/data/sandbox_heartbeat.json"
GUARD_LOG="$LOG_DIR/health_guard.log"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$GUARD_LOG"
}

# 检查进程是否存活
is_alive() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# 获取引擎PID
get_engine_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE" 2>/dev/null
    fi
}

# 检查是否有engine_zhuan1进程在跑（不依赖PID文件）
has_engine_process() {
    pgrep -f "engine_zhuan1.py" > /dev/null 2>&1
}

# 检查是否有watchdog在跑
has_watchdog_process() {
    pgrep -f "watchdog.sh" > /dev/null 2>&1
}

# 启动引擎
start_engine() {
    log "启动引擎..."
    cd "$ENGINE_DIR"
    rm -f "$PID_FILE" "$ENGINE_DIR/data/engine_start.lock"
    cd "$ENGINE_DIR/autonomy"
    nohup python3 engine_zhuan1.py >> "$LOG_DIR/daemon_zhuan1_stdout.log" 2>&1 &
    local new_pid=$!
    sleep 3
    if [ -f "$PID_FILE" ]; then
        local actual_pid=$(cat "$PID_FILE" 2>/dev/null)
        log "引擎已启动，PID: $actual_pid (引擎自写)"
    else
        echo "$new_pid" > "$PID_FILE"
        log "引擎已启动，PID: $new_pid (守卫兜底写)"
    fi
}

# 启动看门狗
start_watchdog() {
    log "启动看门狗..."
    cd "$ENGINE_DIR"
    nohup bash watchdog.sh >> "$LOG_DIR/watchdog.log" 2>&1 &
    log "看门狗已启动"
}

# 更新心跳文件
update_heartbeat() {
    cat > "$HEARTBEAT_FILE" << EOF
{
  "last_guard_check": "$(date '+%Y-%m-%d %H:%M:%S')",
  "engine_alive": $(has_engine_process && echo "true" || echo "false"),
  "watchdog_alive": $(has_watchdog_process && echo "true" || echo "false"),
  "guard_version": "1.0"
}
EOF
}

# 主逻辑
log "=== 健康检查开始 ==="

engine_needed_restart=false
watchdog_needed_restart=false

# 检查引擎
if has_engine_process; then
    log "引擎运行中"
else
    log "引擎未运行，需要重启"
    engine_needed_restart=true
fi

# 检查看门狗
if has_watchdog_process; then
    log "看门狗运行中"
else
    log "看门狗未运行，需要重启"
    watchdog_needed_restart=true
fi

# 执行重启
if [ "$engine_needed_restart" = true ]; then
    start_engine
fi

if [ "$watchdog_needed_restart" = true ]; then
    sleep 2
    start_watchdog
fi

# 更新心跳
update_heartbeat

log "=== 健康检查结束 ==="
