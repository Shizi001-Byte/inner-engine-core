#!/usr/bin/env python3
"""
persona_collab.py — 分识深度协同机制（模块3.3）
复杂任务自动拆解为多步，分派不同分识并行执行，结果汇总校验。
用法：
  python3 persona_collab.py task "任务描述"     # 启动分识协同任务
  python3 persona_collab.py status              # 查看协同任务状态
  python3 persona_collab.py list-personas       # 列出可用分识
"""
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
TASK_FILE = DATA_DIR / "collab_tasks.json"

# 分识定义
PERSONAS = {
    "凡心": {"role": "主控/决策", "specialty": ["方向判断", "任务拆解", "结果汇总"], "model": "A_heavy"},
    "教授": {"role": "深度推演", "specialty": ["技术分析", "架构设计", "逻辑校验"], "model": "A_heavy"},
    "观尘子": {"role": "运维/审核", "specialty": ["代码审查", "状态监控", "完整性校验"], "model": "C_mid"},
    "星卷": {"role": "创作/IP", "specialty": ["内容创作", "世界观构建", "叙事设计"], "model": "A_heavy"},
    "安安": {"role": "档案/记忆", "specialty": ["资料检索", "档案管理", "记忆整合"], "model": "C_mid"},
}


def load_tasks():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TASK_FILE.exists():
        return json.load(open(TASK_FILE))
    return {"tasks": []}


def save_tasks(t):
    with open(TASK_FILE, "w") as f:
        json.dump(t, f, indent=2, ensure_ascii=False)


def decompose_task(description):
    """拆解任务为多步（基于规则，后续可升级为模型拆解）"""
    steps = [
        {"step": 1, "persona": "安安", "action": "检索相关资料和历史认知", "status": "pending"},
        {"step": 2, "persona": "教授", "action": f"深度分析: {description[:50]}", "status": "pending"},
        {"step": 3, "persona": "观尘子", "action": "审查方案可行性和风险", "status": "pending"},
        {"step": 4, "persona": "凡心", "action": "汇总结果，形成最终方案", "status": "pending"},
    ]
    return steps


def start_collab(description):
    """启动协同任务"""
    tasks = load_tasks()
    task_id = f"collab_{int(time.time())}"
    steps = decompose_task(description)
    task = {
        "id": task_id,
        "description": description,
        "steps": steps,
        "status": "running",
        "created_at": datetime.now().isoformat(),
        "results": {},
    }
    tasks["tasks"].append(task)
    save_tasks(tasks)
    print(f"[协同任务] {task_id}")
    print(f"  任务: {description}")
    print(f"  拆解为 {len(steps)} 步:")
    for s in steps:
        print(f"    步骤{s['step']}: {s['persona']} - {s['action'][:40]}")
    print(f"\n  提示: 各分识执行结果需通过引擎主循环写入results字段")
    return task_id


def update_step(task_id, step_num, result, status="completed"):
    """更新某步结果"""
    tasks = load_tasks()
    for t in tasks["tasks"]:
        if t["id"] == task_id:
            for s in t["steps"]:
                if s["step"] == step_num:
                    s["status"] = status
                    t["results"][str(step_num)] = result
                    save_tasks(tasks)
                    print(f"[更新] {task_id} 步骤{step_num}: {status}")
                    return
    print(f"任务 {task_id} 或步骤 {step_num} 不存在")


def show_status(task_id=None):
    tasks = load_tasks()
    if task_id:
        for t in tasks["tasks"]:
            if t["id"] == task_id:
                print(f"=== {t['id']} ===")
                print(f"任务: {t['description']}")
                print(f"状态: {t['status']}")
                for s in t["steps"]:
                    icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(s["status"], "?")
                    print(f"  {icon} 步骤{s['step']}: {s['persona']} - {s['action'][:40]}")
                return
        print(f"任务 {task_id} 不存在")
    else:
        print(f"共 {len(tasks['tasks'])} 个协同任务:")
        for t in tasks["tasks"][-10:]:
            done = sum(1 for s in t["steps"] if s["status"] == "completed")
            print(f"  {t['id']}: {done}/{len(t['steps'])}完成 - {t['description'][:40]}")


def list_personas():
    print("=== 可用分识 ===")
    for name, info in PERSONAS.items():
        print(f"  {name} ({info['role']}): {', '.join(info['specialty'])}")


def main():
    parser = argparse.ArgumentParser(description="分识深度协同")
    sub = parser.add_subparsers(dest="cmd")
    p_task = sub.add_parser("task")
    p_task.add_argument("description")
    sub.add_parser("status")
    sub.add_parser("list-personas")
    p_update = sub.add_parser("update")
    p_update.add_argument("task_id")
    p_update.add_argument("step", type=int)
    p_update.add_argument("result")
    args = parser.parse_args()
    if args.cmd == "task":
        start_collab(args.description)
    elif args.cmd == "status":
        show_status()
    elif args.cmd == "list-personas":
        list_personas()
    elif args.cmd == "update":
        update_step(args.task_id, args.step, args.result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
