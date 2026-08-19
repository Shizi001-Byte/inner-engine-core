#!/usr/bin/env python3
"""
platform_abstraction.py — 平台无关化改造（模块4.4）
逐步剥离对特定模型厂商、云服务的强依赖，核心逻辑可适配任意同类服务。
用法：
  python3 platform_abstraction.py status       # 查看当前平台依赖
  python3 platform_abstraction.py migrate      # 生成迁移配置模板
  python3 platform_abstraction.py test <provider>  # 测试某平台适配
"""
import json
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
ABSTRACTION_FILE = DATA_DIR / "platform_abstraction.json"
CRED_FILE = ENGINE_DIR / "data" / "model_credentials.json"

# 支持的平台适配器
ADAPTERS = {
    "volcengine_ark": {
        "name": "火山引擎Ark",
        "api_base_pattern": "https://ark.{region}.volces.com/api/v3/chat/completions",
        "auth_type": "bearer",
        "models": ["glm-5-2-260617", "deepseek-v4-flash-ga-260731", "doubao-seed-2-1-turbo-260628"],
    },
    "openai_compatible": {
        "name": "OpenAI兼容接口",
        "api_base_pattern": "{base_url}/chat/completions",
        "auth_type": "bearer",
        "models": ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet"],
        "note": "任何OpenAI兼容的API都可适配",
    },
    "supabase": {
        "name": "Supabase",
        "type": "database+storage",
        "alternatives": ["任何PostgreSQL+S3兼容存储", "自建PostgreSQL+MinIO"],
    },
    "feishu": {
        "name": "飞书",
        "type": "notification+docs",
        "alternatives": ["钉钉", "企业微信", "Slack", "Telegram Bot"],
    },
    "gitee": {
        "name": "Gitee",
        "type": "git_hosting",
        "alternatives": ["GitHub", "GitLab", "自建Gitea"],
    },
}


def load_abstraction():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ABSTRACTION_FILE.exists():
        return json.load(open(ABSTRACTION_FILE))
    return {"current_platform": {}, "migration_readiness": {}, "last_check": None}


def save_abstraction(a):
    with open(ABSTRACTION_FILE, "w") as f:
        json.dump(a, f, indent=2, ensure_ascii=False)


def analyze_dependencies():
    """分析当前平台依赖"""
    print("=== 平台依赖分析 ===\n")
    abstraction = load_abstraction()
    deps = {}
    # 模型API
    if CRED_FILE.exists():
        creds = json.load(open(CRED_FILE))
        models = creds.get("models", {})
        api_bases = set()
        for m in models.values():
            base = m.get("api_base", "")
            if "volces.com" in base:
                api_bases.add("火山引擎Ark")
            elif "openai.com" in base:
                api_bases.add("OpenAI")
            else:
                api_bases.add("其他")
        deps["模型API"] = list(api_bases)
    # 数据库
    deps["数据库"] = ["Supabase (PostgreSQL+pgvector)"]
    # 通知
    deps["通知"] = ["飞书Webhook"]
    # 代码托管
    deps["代码托管"] = ["Gitee"]
    # 存储
    deps["对象存储"] = ["Supabase Storage"]
    abstraction["current_platform"] = deps
    abstraction["last_check"] = datetime.now().isoformat()
    for k, v in deps.items():
        print(f"  {k}: {', '.join(v)}")
    # 迁移就绪度评估
    print("\n=== 迁移就绪度 ===")
    readiness = {}
    for component, platforms in deps.items():
        # 检查是否有抽象层
        has_abstraction = component in ["模型API"]  # 模型API已有配置文件抽象
        readiness[component] = "✅可迁移" if has_abstraction else "⚠️需改造"
        print(f"  {component}: {readiness[component]}")
    abstraction["migration_readiness"] = readiness
    save_abstraction(abstraction)
    return abstraction


def generate_migration_config():
    """生成迁移配置模板"""
    print("=== 迁移配置模板 ===\n")
    template = {
        "model_provider": {
            "type": "openai_compatible",
            "api_base": "https://your-api-endpoint/v1",
            "api_key": "your-key",
            "models": {
                "heavy": "your-heavy-model",
                "mid": "your-mid-model",
                "light": "your-light-model",
            }
        },
        "database": {
            "type": "postgresql",
            "host": "your-host",
            "port": 5432,
            "database": "your-db",
            "user": "your-user",
            "password": "your-password",
            "vector_extension": "pgvector",
        },
        "notification": {
            "type": "webhook",
            "url": "https://your-webhook-url",
        },
        "git_hosting": {
            "type": "git",
            "remote": "https://your-git-host/repo.git",
        },
    }
    out_file = DATA_DIR / "migration_template.json"
    with open(out_file, "w") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
    print(json.dumps(template, indent=2, ensure_ascii=False))
    print(f"\n模板已保存: {out_file}")
    print("使用方法: 填入你的平台信息，引擎启动时读取此配置即可切换平台")


def test_adapter(provider):
    """测试某平台适配器"""
    if provider not in ADAPTERS:
        print(f"未知平台: {provider}")
        print(f"可用: {', '.join(ADAPTERS.keys())}")
        return
    adapter = ADAPTERS[provider]
    print(f"=== 适配器: {adapter['name']} ===")
    for k, v in adapter.items():
        print(f"  {k}: {v}")
    print(f"\n  状态: 适配器定义就绪，实际连通性测试需填入凭证后执行")


def main():
    parser = argparse.ArgumentParser(description="平台无关化改造")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status")
    sub.add_parser("migrate")
    p_test = sub.add_parser("test")
    p_test.add_argument("provider")
    args = parser.parse_args()
    if args.cmd == "status":
        analyze_dependencies()
    elif args.cmd == "migrate":
        generate_migration_config()
    elif args.cmd == "test":
        test_adapter(args.provider)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
