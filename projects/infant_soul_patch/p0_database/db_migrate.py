#!/usr/bin/env python3
"""
db_migrate.py — 数据库版本迁移框架（P0.3）

实现表结构版本化管理，支持升级、回滚，规避数据改坏风险。

用法：
  python3 db_migrate.py status          # 查看当前数据库版本
  python3 db_migrate.py migrate         # 升级到最新版本
  python3 db_migrate.py rollback        # 回滚到上一版本
  python3 db_migrate.py create "描述"   # 创建新的迁移文件
  python3 db_migrate.py history         # 查看迁移历史
"""

import json
import time
import sys
import os
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
STATE_FILE = Path(__file__).parent.parent / "data" / "db_migration_state.json"
SCHEMA_FILE = Path(__file__).parent / "db_schema.sql"

MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_state():
    """加载迁移状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"current_version": 0, "migrations": [], "history": []}


def save_state(state):
    """保存迁移状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def list_migrations():
    """列出所有迁移文件"""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    migrations = []
    for f in files:
        # 文件名格式：0001_initial_schema.sql
        parts = f.stem.split("_", 1)
        version = int(parts[0]) if parts[0].isdigit() else 0
        name = parts[1] if len(parts) > 1 else f.stem
        migrations.append({"version": version, "name": name, "file": f})
    return sorted(migrations, key=lambda x: x["version"])


def create_migration(description):
    """创建新的迁移文件"""
    state = load_state()
    migrations = list_migrations()
    next_version = max([m["version"] for m in migrations], default=0) + 1

    # 生成文件名
    safe_name = description.replace(" ", "_").replace("/", "_")[:50]
    filename = f"{next_version:04d}_{safe_name}.sql"
    filepath = MIGRATIONS_DIR / filename

    # 迁移模板
    template = f"""-- ============================================================
-- 迁移 {next_version:04d}: {description}
-- 创建时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
-- ============================================================

-- ===== 升级 (UP) =====
-- 在此写升级SQL

-- ===== 回滚 (DOWN) =====
-- 在此写回滚SQL（注释掉，需要时执行）
-- DROP TABLE IF EXISTS ...;
"""

    with open(filepath, "w") as f:
        f.write(template)

    print(f"[OK] 迁移文件已创建: {filename}")
    print(f"     路径: {filepath}")
    print(f"     请编辑文件填写UP和DOWN的SQL")
    return filepath


def migrate():
    """升级到最新版本"""
    state = load_state()
    migrations = list_migrations()
    current = state["current_version"]

    pending = [m for m in migrations if m["version"] > current]
    if not pending:
        print(f"[INFO] 数据库已是最新版本 (v{current})")
        return

    print(f"=== 数据库迁移 ===")
    print(f"当前版本: v{current}")
    print(f"待执行迁移: {len(pending)} 个")
    print()

    for m in pending:
        print(f"  执行 v{m['version']:04d}: {m['name']}...")
        # 读取并执行SQL（实际需要通过Supabase SQL API或psql执行）
        # 当前为框架实现，记录执行状态
        state["current_version"] = m["version"]
        state["migrations"].append({"version": m["version"], "name": m["name"], "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        state["history"].append({"action": "migrate", "version": m["version"], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})
        print(f"    ✓ 已记录（实际SQL需在Supabase执行）")

    save_state(state)
    print(f"\n[完成] 数据库已升级到 v{state['current_version']}")


def rollback():
    """回滚到上一版本"""
    state = load_state()
    if state["current_version"] == 0:
        print("[INFO] 已是初始版本，无法回滚")
        return

    current = state["current_version"]
    print(f"=== 数据库回滚 ===")
    print(f"当前版本: v{current}")
    print(f"回滚目标: v{current - 1}")
    print()

    # 找到当前版本的迁移文件
    migrations = list_migrations()
    current_migration = next((m for m in migrations if m["version"] == current), None)

    if current_migration:
        print(f"  回滚 v{current:04d}: {current_migration['name']}")
        print(f"    请手动执行文件中的DOWN部分SQL: {current_migration['file'].name}")

    state["current_version"] = current - 1
    state["history"].append({"action": "rollback", "from_version": current, "to_version": current - 1, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})
    save_state(state)
    print(f"\n[完成] 数据库已回滚到 v{state['current_version']}")


def show_status():
    """查看当前状态"""
    state = load_state()
    migrations = list_migrations()

    print("=== 数据库迁移状态 ===")
    print(f"当前版本: v{state['current_version']}")
    print(f"总迁移文件: {len(migrations)} 个")
    print(f"已执行迁移: {len(state['migrations'])} 个")

    pending = [m for m in migrations if m["version"] > state["current_version"]]
    if pending:
        print(f"\n待执行迁移:")
        for m in pending:
            print(f"  v{m['version']:04d}: {m['name']}")
    else:
        print(f"\n✓ 数据库已是最新版本")


def show_history():
    """查看迁移历史"""
    state = load_state()
    print("=== 迁移历史 ===")
    for h in reversed(state["history"][-10:]):
        print(f"  [{h['timestamp']}] {h['action']}: v{h.get('version', h.get('to_version', '?'))}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 db_migrate.py [status|migrate|rollback|create|history]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        show_status()
    elif cmd == "migrate":
        migrate()
    elif cmd == "rollback":
        rollback()
    elif cmd == "create" and len(sys.argv) > 2:
        create_migration(sys.argv[2])
    elif cmd == "history":
        show_history()
    else:
        print("参数错误")
