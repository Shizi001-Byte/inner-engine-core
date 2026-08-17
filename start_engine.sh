#!/bin/bash
# V7.3 单引擎IO并发版 - 办公模式一键启动+守护
ENGINE_DIR="/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/autonomy"
LOG_DIR="/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/logs"
PID_FILE="/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/data/engine.pid"

# 检查是否已运行
if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "引擎已在运行，PID: $(cat $PID_FILE)"
    exit 0
fi

# 环境自检
echo "[自检] 检查沙箱环境..."
python3 -c "import urllib.request; print('  Python环境OK')" || { echo "  Python环境异常"; exit 1; }

# 启动
cd "$ENGINE_DIR"
nohup python3 engine_zhuan1.py > "$LOG_DIR/daemon_zhuan1_stdout.log" 2>&1 &
echo $! > "$PID_FILE"
echo "[启动] V7.3引擎已启动，PID: $(cat $PID_FILE)"
echo "[日志] $LOG_DIR/daemon_zhuan1_stdout.log"
