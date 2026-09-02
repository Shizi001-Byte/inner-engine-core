#!/bin/bash
# V7.3 单引擎IO并发版 - 办公模式一键启动+守护
# P1-8修复：加flock原子保护，避免多实例同时启动
# P0修复：不提前写PID，让引擎自己写，避免竞态自杀
# PIT-082修复：动态检测引擎目录，不再硬编码绝对路径
# 脚本所在目录即为引擎根目录
ENGINE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="${ENGINE_ROOT}/autonomy"
LOG_DIR="${ENGINE_ROOT}/logs"
PID_FILE="${ENGINE_ROOT}/data/engine.pid"
LOCK_FILE="${ENGINE_ROOT}/data/engine_start.lock"

# P1-8：flock互斥，确保只有一个启动实例
exec 200>"$LOCK_FILE"
flock -n 200 || { echo "另一个启动操作正在进行，退出"; exit 1; }

# 检查是否已运行
if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "引擎已在运行，PID: $(cat $PID_FILE)"
    exit 0
fi

# 环境自检
echo "[自检] 检查沙箱环境..."
python3 -c "import urllib.request; print('  Python环境OK')" || { echo "  Python环境异常"; exit 1; }

# 启动（不提前写PID，让引擎自己写）
cd "$ENGINE_DIR"
rm -f "$PID_FILE"
nohup python3 engine_zhuan1.py > "$LOG_DIR/daemon_zhuan1_stdout.log" 2>&1 &
new_pid=$!

# 等待引擎自己写PID文件
sleep 3
if [ -f "$PID_FILE" ]; then
    actual_pid=$(cat "$PID_FILE" 2>/dev/null)
    echo "[启动] V7.3引擎已启动，PID: $actual_pid (引擎自写)"
else
    # 兜底：引擎没写PID则手动写
    echo "$new_pid" > "$PID_FILE"
    echo "[启动] V7.3引擎已启动，PID: $new_pid (脚本兜底写)"
fi
echo "[日志] $LOG_DIR/daemon_zhuan1_stdout.log"

# 释放锁
flock -u 200
