#!/bin/bash
# 凡心引擎·外部备份脚本
# 功能：不依赖引擎内部机制，由cron每15分钟自动备份关键状态到Gitee
# 设计原则：增量、轻量、只备份关键文件、失败不影响引擎运行

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR"
LOG_DIR="$ENGINE_DIR/logs"
BACKUP_LOG="$LOG_DIR/external_backup.log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$BACKUP_LOG"
}

log "=== 外部备份开始 ==="

cd "$ENGINE_DIR"

# 检查Git仓库
if [ ! -d ".git" ]; then
    log "错误：Git仓库不存在，跳过备份"
    exit 1
fi

# 只备份关键状态文件（不备份大文件和日志）
KEY_FILES=(
    "data/engine_state.json"
    "data/core_memory.json"
    "data/archive_index.json"
    "data/sandbox_heartbeat.json"
    "data/model_credentials.json"
    "data/backup_config.json"
)

# 检查哪些文件有变化
changed_files=()
for f in "${KEY_FILES[@]}"; do
    if [ -f "$f" ]; then
        # 用git status检查是否有变化
        if git status --porcelain "$f" 2>/dev/null | grep -q .; then
            changed_files+=("$f")
        fi
    fi
done

if [ ${#changed_files[@]} -eq 0 ]; then
    log "无变化，跳过备份"
    log "=== 外部备份结束（无变化）==="
    exit 0
fi

log "发现 ${#changed_files[@]} 个文件有变化: ${changed_files[*]}"

# 生成状态摘要（用于commit message）
state_summary=""
if [ -f "data/engine_state.json" ]; then
    # 提取关键信息
    zhuan=$(python3 -c "import json; d=json.load(open('data/engine_state.json')); print(d.get('zhuan_count', d.get('total_completed', '?')))" 2>/dev/null || echo "?")
    cognition=$(python3 -c "import json; d=json.load(open('data/engine_state.json')); print(d.get('cognition_count', d.get('total_cognitions', '?')))" 2>/dev/null || echo "?")
    pit=$(python3 -c "import json; d=json.load(open('data/engine_state.json')); print(d.get('pit_count', d.get('total_pits', '?')))" 2>/dev/null || echo "?")
    state_summary="转${zhuan} 认知${cognition} 坑${pit}"
fi

commit_msg="外部自动备份: $(date '+%Y-%m-%d %H:%M') ${state_summary}"

# 添加变化的文件
for f in "${changed_files[@]}"; do
    git add "$f" 2>>"$BACKUP_LOG" || log "  添加失败: $f"
done

# 提交
if git commit -m "$commit_msg" 2>>"$BACKUP_LOG"; then
    log "  本地提交成功: $commit_msg"
else
    log "  本地提交失败或无变化"
fi

# 推送到Gitee（主备份）
if git push origin master 2>>"$BACKUP_LOG"; then
    log "  推送到Gitee成功"
else
    log "  推送到Gitee失败，将在下次重试"
fi

# 推送到GitHub（备用，失败不影响）
if git push github master 2>>"$BACKUP_LOG"; then
    log "  推送到GitHub成功"
else
    log "  推送到GitHub失败（备用，不影响）"
fi

log "=== 外部备份结束 ==="
