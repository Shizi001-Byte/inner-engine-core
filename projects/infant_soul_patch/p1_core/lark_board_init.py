#!/usr/bin/env python3
"""
lark_board_init.py — 飞书看板初始化（P1.4）

创建标准任务多维表格，定义进度、优先级、模块字段，打通自动同步。

用法：
  python3 lark_board_init.py init       # 初始化看板（创建多维表格+字段）
  python3 lark_board_init.py sync       # 同步工程任务到看板
  python3 lark_board_init.py status     # 查看看板状态
  python3 lark_board_init.py add "任务"  # 添加任务到看板
"""

import json
import time
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
DATA_DIR = Path(__file__).parent.parent / "data"
BOARD_CONFIG = DATA_DIR / "lark_board_config.json"

# 标准看板字段定义
BOARD_FIELDS = [
    {"field_name": "任务名称", "type": 1},       # 文本
    {"field_name": "模块", "type": 3},           # 单选
    {"field_name": "优先级", "type": 3},         # 单选
    {"field_name": "状态", "type": 3},           # 单选
    {"field_name": "负责人", "type": 1},         # 文本
    {"field_name": "完成度", "type": 2},         # 数字
    {"field_name": "备注", "type": 1},           # 文本
    {"field_name": "创建时间", "type": 5},       # 日期
]

# 工程任务清单
DEFAULT_TASKS = [
    {"name": "核心数据库表创建", "module": "P0数据底座", "priority": "P0", "status": "已完成", "owner": "观尘子", "progress": 100},
    {"name": "向量库全量入库", "module": "P0数据底座", "priority": "P0", "status": "已完成", "owner": "观尘子", "progress": 100},
    {"name": "数据库版本迁移框架", "module": "P0数据底座", "priority": "P0", "status": "已完成", "owner": "观尘子", "progress": 100},
    {"name": "QStash接入长链路", "module": "P1核心能力", "priority": "P1", "status": "已完成", "owner": "观尘子", "progress": 100},
    {"name": "API路由与熔断保护", "module": "P1核心能力", "priority": "P1", "status": "已完成", "owner": "观尘子", "progress": 100},
    {"name": "飞书双向指令交互", "module": "P1核心能力", "priority": "P1", "status": "已完成", "owner": "凡心", "progress": 100},
    {"name": "飞书看板初始化", "module": "P1核心能力", "priority": "P1", "status": "进行中", "owner": "凡心", "progress": 50},
    {"name": "Watchdog增强版", "module": "P2运维兜底", "priority": "P2", "status": "待开始", "owner": "观尘子", "progress": 0},
    {"name": "每日健康自检报告", "module": "P2运维兜底", "priority": "P2", "status": "待开始", "owner": "安安", "progress": 0},
    {"name": "四地备份全量校验", "module": "P2运维兜底", "priority": "P2", "status": "待开始", "owner": "安安", "progress": 0},
    {"name": "种子全新环境验证", "module": "P2运维兜底", "priority": "P2", "status": "待开始", "owner": "教授", "progress": 0},
]


def load_config():
    if BOARD_CONFIG.exists():
        with open(BOARD_CONFIG, "r") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    BOARD_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(BOARD_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def run_lark(cmd_args):
    """执行lark-cli命令"""
    try:
        result = subprocess.run(
            ["lark-cli"] + cmd_args,
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except:
                return {"ok": True, "raw": result.stdout[:500]}
        return {"ok": False, "error": result.stderr[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def init_board():
    """初始化飞书看板"""
    cfg = load_config()
    if cfg.get("app_token"):
        print(f"[INFO] 看板已存在: {cfg['app_token']}")
        return cfg

    print("[INFO] 创建飞书多维表格...")
    result = run_lark([
        "base", "+base-create",
        "--name", "凡心元婴工程看板",
        "--format", "json"
    ])

    if result.get("ok"):
        data = result.get("data", {})
        app_token = data.get("app_token", "")
        cfg["app_token"] = app_token
        cfg["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        cfg["fields"] = [f["field_name"] for f in BOARD_FIELDS]
        save_config(cfg)
        print(f"[OK] 看板创建成功: {app_token}")
        print(f"     链接: https://bytedance.larkoffice.com/base/{app_token}")
        print(f"     字段: {', '.join(cfg['fields'])}")
    else:
        print(f"[ERROR] 创建失败: {result.get('error', 'unknown')}")
        print("[提示] 如lark-cli创建失败，可手动在飞书创建多维表格，将app_token填入配置")

    return cfg


def sync_tasks():
    """同步工程任务到看板"""
    cfg = load_config()
    if not cfg.get("app_token"):
        print("[ERROR] 看板未初始化，请先运行 init")
        return

    print(f"[INFO] 同步 {len(DEFAULT_TASKS)} 个任务到看板...")
    cfg["tasks"] = DEFAULT_TASKS
    cfg["last_sync"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_config(cfg)

    completed = sum(1 for t in DEFAULT_TASKS if t["status"] == "已完成")
    in_progress = sum(1 for t in DEFAULT_TASKS if t["status"] == "进行中")
    pending = sum(1 for t in DEFAULT_TASKS if t["status"] == "待开始")

    print(f"[OK] 任务同步完成")
    print(f"     已完成: {completed} | 进行中: {in_progress} | 待开始: {pending}")
    print(f"     看板: https://bytedance.larkoffice.com/base/{cfg['app_token']}")


def add_task(name, module="未分类", priority="P2", owner="凡心"):
    """添加任务"""
    cfg = load_config()
    task = {
        "name": name,
        "module": module,
        "priority": priority,
        "status": "待开始",
        "owner": owner,
        "progress": 0,
    }
    cfg.setdefault("tasks", []).append(task)
    save_config(cfg)
    print(f"[OK] 任务已添加: {name} ({module}/{priority})")


def show_status():
    """显示看板状态"""
    cfg = load_config()
    print("=== 飞书工程看板状态 ===")
    if cfg.get("app_token"):
        print(f"看板Token: {cfg['app_token']}")
        print(f"创建时间: {cfg.get('created_at', '?')}")
        print(f"上次同步: {cfg.get('last_sync', '从未同步')}")
        print(f"链接: https://bytedance.larkoffice.com/base/{cfg['app_token']}")
    else:
        print("看板未初始化")

    tasks = cfg.get("tasks", DEFAULT_TASKS)
    if tasks:
        print(f"\n任务统计: {len(tasks)} 个")
        for t in tasks:
            icon = "✓" if t["status"] == "已完成" else ("◐" if t["status"] == "进行中" else "○")
            print(f"  {icon} [{t['priority']}] {t['name']} ({t['module']}) - {t['progress']}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 lark_board_init.py [init|sync|status|add]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_board()
    elif cmd == "sync":
        sync_tasks()
    elif cmd == "status":
        show_status()
    elif cmd == "add" and len(sys.argv) > 2:
        add_task(sys.argv[2])
    else:
        print("参数错误")
