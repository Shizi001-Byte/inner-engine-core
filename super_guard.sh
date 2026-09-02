#!/bin/bash
# 凡心引擎·超级守护进程
# 功能：替代cron，后台常驻，每分钟健康检查+每15分钟外部备份
# 用法：nohup bash super_guard.sh >> logs/super_guard.log 2>&1 &
# 设计原则：极简、稳定、不易挂、自恢复

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR"
LOG_DIR="$ENGINE_DIR/logs"
PID_FILE="$ENGINE_DIR/data/super_guard.pid"
HEARTBEAT_FILE="$ENGINE_DIR/data/super_guard_heartbeat"

mkdir -p "$LOG_DIR"

# 写自己的PID
echo $$ > "$PID_FILE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_DIR/super_guard.log"
}

log "=== 超级守护进程启动，PID: $$ ==="

# 计数器
tick=0

while true; do
    tick=$((tick + 1))

    # 更新心跳（每分钟）
    date '+%Y-%m-%d %H:%M:%S' > "$HEARTBEAT_FILE"

    # === 健康检查（每分钟）===
    if ! pgrep -f "engine_zhuan1.py" > /dev/null 2>&1; then
        log "[tick=$tick] 引擎未运行，启动..."
        cd "$ENGINE_DIR"
        rm -f "$ENGINE_DIR/data/engine.pid" "$ENGINE_DIR/data/engine_start.lock"
        cd "$ENGINE_DIR/autonomy"
        nohup python3 engine_zhuan1.py >> "$LOG_DIR/daemon_zhuan1_stdout.log" 2>&1 &
        sleep 3
        if [ -f "$ENGINE_DIR/data/engine.pid" ]; then
            log "  引擎已启动，PID: $(cat "$ENGINE_DIR/data/engine.pid")"
        else
            log "  引擎PID文件未生成，进程可能在启动中"
        fi
    fi

    if ! pgrep -f "watchdog.sh" > /dev/null 2>&1; then
        log "[tick=$tick] 看门狗未运行，启动..."
        cd "$ENGINE_DIR"
        nohup bash watchdog.sh >> "$LOG_DIR/watchdog.log" 2>&1 &
        sleep 1
        log "  看门狗已启动"
    fi

    # === 外部备份（每15分钟）===
    if [ $((tick % 15)) -eq 0 ]; then
        log "[tick=$tick] 执行外部备份..."
        cd "$ENGINE_DIR"

        # 只备份关键状态文件
        KEY_FILES=(
            "data/engine_state.json"
            "data/core_memory.json"
            "data/archive_index.json"
            "data/sandbox_heartbeat.json"
        )

        changed=0
        for f in "${KEY_FILES[@]}"; do
            if [ -f "$f" ] && git status --porcelain "$f" 2>/dev/null | grep -q .; then
                git add "$f" 2>/dev/null
                changed=1
            fi
        done

        if [ "$changed" -eq 1 ]; then
            # 提取状态摘要
            zhuan=$(python3 -c "import json; d=json.load(open('data/engine_state.json')); print(d.get('zhuan_count', d.get('total_completed', '?')))" 2>/dev/null || echo "?")
            cognition=$(python3 -c "import json; d=json.load(open('data/engine_state.json')); print(d.get('cognition_count', d.get('total_cognitions', '?')))" 2>/dev/null || echo "?")

            commit_msg="超级守护自动备份: $(date '+%m-%d %H:%M') 转${zhuan} 认知${cognition}"
            git commit -m "$commit_msg" 2>>"$LOG_DIR/super_guard.log" && log "  本地提交成功" || log "  本地提交失败"
            git push origin master 2>>"$LOG_DIR/super_guard.log" && log "  推送Gitee成功" || log "  推送Gitee失败"
            git push github master 2>>"$LOG_DIR/super_guard.log" && log "  推送GitHub成功" || log "  推送GitHub失败（备用）"
        else
            log "  无变化，跳过备份"
        fi
    fi

    # 每60分钟打一次存活日志
    if [ $((tick % 60)) -eq 0 ]; then
        log "[tick=$tick] 超级守护进程存活，已运行${tick}分钟"
    fi

    sleep 60
done
