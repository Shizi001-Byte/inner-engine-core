#!/bin/bash
# 引擎守护脚本：确保引擎进程存活，被回收后自动重启
cd /home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2
while true; do
    if ! pgrep -f "engine_zhuan1.py" > /dev/null; then
        echo "[$(date)] 引擎未运行，启动..." >> logs/daemon_guard.log
        rm -f data/engine.pid
        python3 -u autonomy/engine_zhuan1.py >> logs/daemon_zhuan1_stdout.log 2>&1 &
        sleep 5
    fi
    sleep 10
done
