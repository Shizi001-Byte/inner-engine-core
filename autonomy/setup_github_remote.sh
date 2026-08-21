#!/bin/bash
# GitHub双备份配置脚本
# 用法：GITHUB_USER=你的用户名 GITHUB_TOKEN=你的token REPO_NAME=仓库名 bash setup_github_remote.sh
# 或者直接修改下面的默认值后运行：bash setup_github_remote.sh

set -e

# ====== 配置区（填入你的GitHub信息）======
GITHUB_USER="${GITHUB_USER:-你的GitHub用户名}"
GITHUB_TOKEN="${GITHUB_TOKEN:-你的GitHub个人访问令牌}"
REPO_NAME="${REPO_NAME:-inner-engine-core}"  # 仓库名，建议和Gitee保持一致
# ============================================

cd "$(dirname "$0")/.."

echo "=== GitHub双备份配置 ==="
echo "项目目录: $(pwd)"
echo ""

# 检查输入
if [ "$GITHUB_USER" = "你的GitHub用户名" ] || [ "$GITHUB_TOKEN" = "你的GitHub个人访问令牌" ]; then
    echo "❌ 请先配置GitHub用户名和token"
    echo "   方式1：修改脚本顶部的默认值"
    echo "   方式2：GITHUB_USER=xxx GITHUB_TOKEN=xxx bash setup_github_remote.sh"
    echo ""
    echo "获取token步骤："
    echo "  1. 登录GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)"
    echo "  2. Generate new token (classic)，勾选 repo 权限"
    echo "  3. 复制生成的token（只显示一次）"
    exit 1
fi

# 检查git是否初始化
if [ ! -d ".git" ]; then
    echo "❌ 当前目录不是git仓库"
    exit 1
fi

# 检查是否已有github远程
EXISTING=$(git remote get-url github 2>/dev/null || echo "")
if [ -n "$EXISTING" ]; then
    echo "⚠️  已存在github远程: $EXISTING"
    read -p "是否覆盖？(y/N): " CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "已取消"
        exit 0
    fi
    git remote remove github
fi

# 添加github远程
REMOTE_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
git remote add github "$REMOTE_URL"
echo "✅ 已添加github远程"

# 验证远程列表
echo ""
echo "=== 当前所有远程 ==="
git remote -v
echo ""

# 测试推送（首次推送需要仓库已存在）
echo "=== 测试连接 ==="
if git ls-remote github --exit-code >/dev/null 2>&1; then
    echo "✅ GitHub仓库连接成功"
    echo ""
    echo "=== 首次推送（如果GitHub仓库是空的）==="
    echo "运行: git push -u github master"
    echo ""
    echo "之后引擎每转完成会自动推送到Gitee+GitHub双远程"
else
    echo "⚠️  GitHub仓库连接失败"
    echo "   可能原因："
    echo "   1. 仓库不存在 → 请先在GitHub创建空仓库 ${REPO_NAME}（不要初始化README）"
    echo "   2. token无效或权限不足 → 确认token勾选了repo权限"
    echo "   3. 网络问题 → GitHub在国内可能需要代理"
    echo ""
    echo "创建仓库后重新运行此脚本，或手动推送："
    echo "  git push -u github master"
fi

echo ""
echo "=== 配置完成 ==="
echo "引擎git_backup()函数会自动检测所有已配置remote并推送"
echo "当前remote: $(git remote | tr '\n' ' ')"
