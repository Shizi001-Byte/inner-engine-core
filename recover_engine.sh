#!/bin/bash
# 凡心引擎·一键恢复脚本
# 功能：沙箱回收后，执行一个命令完整恢复引擎运行环境
# 用法：bash recover_engine.sh
# 设计原则：幂等、可重复执行、每步有验证

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR"
LOG_DIR="$ENGINE_DIR/logs"
RECOVER_LOG="$LOG_DIR/recover_$(date '+%Y%m%d_%H%M%S').log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$RECOVER_LOG"
}

log "=== 凡心引擎一键恢复开始 ==="
log "引擎目录: $ENGINE_DIR"

# 步骤1：检查Git仓库是否存在
log "[1/7] 检查Git仓库..."
if [ -d "$ENGINE_DIR/.git" ]; then
    log "  Git仓库存在"
else
    log "  Git仓库不存在，从Gitee克隆..."
    cd "$(dirname "$ENGINE_DIR")"
    git clone https://gitee.com/shizi-mem001/inner-engine-core.git engine_v7_2
    cd "$ENGINE_DIR"
    log "  克隆完成"
fi

# 步骤2：从Gitee拉取最新代码
log "[2/7] 从Gitee拉取最新代码..."
cd "$ENGINE_DIR"
git fetch origin 2>>"$RECOVER_LOG" || log "  fetch失败，继续使用本地版本"
git reset --hard origin/master 2>>"$RECOVER_LOG" || log "  reset失败，继续使用本地版本"
log "  代码已同步"

# 步骤3：配置Git双远程
log "[3/7] 配置Git双远程..."
git remote set-url origin https://gitee.com/shizi-mem001/inner-engine-core.git 2>/dev/null || true
if ! git remote | grep -q github; then
    git remote add github https://github.com/Shizi001-Byte/inner-engine-core.git 2>/dev/null || true
fi
log "  双远程配置完成"

# 步骤4：检查并恢复敏感配置
log "[4/7] 检查敏感配置..."
# 模型凭证
if [ ! -f "$ENGINE_DIR/data/model_credentials.json" ]; then
    log "  模型凭证缺失，从恢复档案重建..."
    mkdir -p "$ENGINE_DIR/data"
    cat > "$ENGINE_DIR/data/model_credentials.json" << 'EOF'
{
  "api_key": "YOUR_ARK_API_KEY",
  "api_base": "https://ark.cn-beijing.volces.com/api/v3",
  "models": {
    "A": {"name": "GLM-5.2", "model_id": "glm-5-2-260617", "tier": "heavy"},
    "B": {"name": "Seed-2.1-Turbo", "model_id": "doubao-seed-2-1-turbo-260628", "tier": "light", "endpoint": "/responses"},
    "C": {"name": "DeepSeek-V4-Flash", "model_id": "deepseek-v4-flash-ga-260731", "tier": "medium"}
  }
}
EOF
    log "  模型凭证已重建"
else
    log "  模型凭证存在"
fi

# 飞书配置
if [ ! -f "$ENGINE_DIR/projects/infant_soul/data/lark_push_config.json" ]; then
    log "  飞书配置缺失，重建..."
    mkdir -p "$ENGINE_DIR/projects/infant_soul/data"
    cat > "$ENGINE_DIR/projects/infant_soul/data/lark_push_config.json" << 'EOF'
{
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/1ed1cd06-9300-4712-89a3-11cba716e0e9",
  "enabled": true
}
EOF
    log "  飞书配置已重建"
else
    log "  飞书配置存在"
fi

# 步骤5：安装依赖
log "[5/7] 检查依赖..."
python3 -c "import urllib.request; import json; import os; import sys" 2>>"$RECOVER_LOG" && log "  核心依赖OK" || {
    log "  安装requests..."
    pip3 install requests 2>>"$RECOVER_LOG" || log "  pip安装失败，继续"
}

# 步骤6：设置cron健康守卫
log "[6/7] 设置cron健康守卫..."
# 先清理旧的cron任务（如果有）
crontab -l 2>/dev/null | grep -v "health_guard.sh" | grep -v "external_backup.sh" > /tmp/cron_tmp 2>/dev/null || true
# 添加健康守卫（每分钟）
echo "* * * * * /bin/bash $ENGINE_DIR/health_guard.sh >> $LOG_DIR/cron_health.log 2>&1" >> /tmp/cron_tmp
# 添加外部备份（每15分钟）
echo "*/15 * * * * /bin/bash $ENGINE_DIR/external_backup.sh >> $LOG_DIR/cron_backup.log 2>&1" >> /tmp/cron_tmp
crontab /tmp/cron_tmp
rm -f /tmp/cron_tmp
log "  cron已设置（健康守卫每分钟，外部备份每15分钟）"

# 步骤7：启动引擎和看门狗
log "[7/7] 启动引擎和看门狗..."
cd "$ENGINE_DIR"
rm -f "$ENGINE_DIR/data/engine.pid" "$ENGINE_DIR/data/engine_start.lock"

# 启动引擎
cd "$ENGINE_DIR/autonomy"
nohup python3 engine_zhuan1.py >> "$LOG_DIR/daemon_zhuan1_stdout.log" 2>&1 &
engine_pid=$!
log "  引擎启动中，PID: $engine_pid"

sleep 5

# 验证引擎
if [ -f "$ENGINE_DIR/data/engine.pid" ]; then
    actual_pid=$(cat "$ENGINE_DIR/data/engine.pid" 2>/dev/null)
    log "  引擎已确认运行，PID: $actual_pid"
else
    log "  引擎PID文件未生成，检查进程..."
    if pgrep -f "engine_zhuan1.py" > /dev/null 2>&1; then
        log "  引擎进程存在，PID文件延迟生成"
        echo "$engine_pid" > "$ENGINE_DIR/data/engine.pid"
    else
        log "  警告：引擎进程未找到，检查日志"
        tail -20 "$LOG_DIR/daemon_zhuan1_stdout.log" >> "$RECOVER_LOG" 2>/dev/null || true
    fi
fi

# 启动看门狗
cd "$ENGINE_DIR"
nohup bash watchdog.sh >> "$LOG_DIR/watchdog.log" 2>&1 &
log "  看门狗已启动"

sleep 2

# 启动健康守卫（立即执行一次）
/bin/bash "$ENGINE_DIR/health_guard.sh" 2>/dev/null || true
log "  健康守卫已执行一次"

log "=== 凡心引擎一键恢复完成 ==="
log "恢复日志: $RECOVER_LOG"
log "引擎日志: $LOG_DIR/daemon_zhuan1_stdout.log"
log ""
log "验证命令："
log "  pgrep -af engine_zhuan1    # 检查引擎进程"
log "  pgrep -af watchdog.sh       # 检查看门狗进程"
log "  crontab -l                  # 检查cron任务"
log "  tail -20 $LOG_DIR/engine_$(date '+%Y-%m-%d').log  # 查看引擎日志"
