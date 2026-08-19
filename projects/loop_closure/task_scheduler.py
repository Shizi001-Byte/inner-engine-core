#!/usr/bin/env python3
"""
task_scheduler.py — 统一任务调度中心（模块1.4）
管理所有定时任务（备份、自检、蒸馏、同步、轮询等），支持启停、优先级、失败重试、超时熔断。
替代零散的crontab，所有任务可视化管理。
用法：
  python3 task_scheduler.py start           # 启动调度器（前台）
  python3 task_scheduler.py start --daemon  # 后台启动
  python3 task_scheduler.py stop            # 停止调度器
  python3 task_scheduler.py status          # 查看任务状态
  python3 task_scheduler.py run <task_name> # 手动执行某个任务
  python3 task_scheduler.py list            # 列出所有任务
"""
import json
import time
import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
SCHEDULE_FILE = DATA_DIR / "scheduler_config.json"
STATE_FILE = DATA_DIR / "scheduler_state.json"
PID_FILE = DATA_DIR / "scheduler.pid"

# 默认任务配置
DEFAULT_TASKS = {
    "health_check": {
        "description": "全链路健康检查",
        "script": "python3 projects/infant_soul_patch/p2_ops/daily_health_check.py",
        "interval": 3600,       # 每小时
        "priority": 1,
        "max_retries": 2,
        "timeout": 120,
        "enabled": True,
    },
    "four_backup": {
        "description": "四地备份",
        "script": "python3 projects/infant_soul/survival_seed/multi_backup.py backup",
        "interval": 21600,      # 每6小时
        "priority": 2,
        "max_retries": 3,
        "timeout": 300,
        "enabled": True,
    },
    "lark_command_poll": {
        "description": "飞书指令轮询",
        "script": "python3 projects/loop_closure/lark_full_bidir.py poll --once",
        "interval": 30,         # 每30秒
        "priority": 1,
        "max_retries": 1,
        "timeout": 60,
        "enabled": True,
    },
    "chain_resume": {
        "description": "长链路断点续跑",
        "script": "python3 projects/loop_closure/long_chain_full.py resume-pending",
        "interval": 300,        # 每5分钟
        "priority": 2,
        "max_retries": 2,
        "timeout": 600,
        "enabled": True,
    },
    "cognition_distill": {
        "description": "认知蒸馏",
        "script": "python3 projects/infant_soul/cognition_distill/weekly_distill.py",
        "interval": 86400,      # 每天
        "priority": 3,
        "max_retries": 1,
        "timeout": 300,
        "enabled": False,       # 默认关闭，按需开启
    },
    "state_cloud_sync": {
        "description": "引擎状态上云",
        "script": "python3 autonomy/state_sync.py push",
        "interval": 600,        # 每10分钟
        "priority": 2,
        "max_retries": 2,
        "timeout": 60,
        "enabled": True,
    },
}


def load_config():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SCHEDULE_FILE.exists():
        with open(SCHEDULE_FILE) as f:
            return json.load(f)
    cfg = {"tasks": DEFAULT_TASKS, "created_at": datetime.now().isoformat()}
    save_config(cfg)
    return cfg


def save_config(cfg):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": {}, "run_count": {}, "fail_count": {}, "status": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def run_task(name, task_cfg):
    """执行单个任务"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 执行任务: {name} ({task_cfg['description']})")
    try:
        result = subprocess.run(
            task_cfg["script"], shell=True, cwd=str(ENGINE_DIR),
            capture_output=True, text=True, timeout=task_cfg.get("timeout", 300)
        )
        success = result.returncode == 0
        output = (result.stdout + result.stderr)[-500:]
        print(f"  结果: {'✅成功' if success else '❌失败'}")
        if not success:
            print(f"  输出: {output[:200]}")
        return success, output
    except subprocess.TimeoutExpired:
        print(f"  ⏰超时({task_cfg.get('timeout')}s)")
        return False, "timeout"
    except Exception as e:
        print(f"  ❌异常: {e}")
        return False, str(e)


def scheduler_loop():
    """调度器主循环"""
    cfg = load_config()
    state = load_state()
    print(f"=== 任务调度中心启动 ===")
    print(f"已配置 {len(cfg['tasks'])} 个任务")
    enabled = [n for n, t in cfg["tasks"].items() if t.get("enabled")]
    print(f"已启用 {len(enabled)} 个: {', '.join(enabled)}")

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    try:
        while True:
            now = time.time()
            for name, task in cfg["tasks"].items():
                if not task.get("enabled"):
                    continue
                last = state["last_run"].get(name, 0)
                interval = task.get("interval", 3600)
                if now - last >= interval:
                    # 执行任务（带重试）
                    max_retries = task.get("max_retries", 1)
                    for attempt in range(max_retries):
                        success, output = run_task(name, task)
                        state["run_count"][name] = state["run_count"].get(name, 0) + 1
                        if success:
                            state["last_run"][name] = now
                            state["status"][name] = "ok"
                            break
                        else:
                            state["fail_count"][name] = state["fail_count"].get(name, 0) + 1
                            state["status"][name] = "failed"
                            if attempt < max_retries - 1:
                                print(f"  重试 {attempt+1}/{max_retries}...")
                                time.sleep(5)
                    save_state(state)
            time.sleep(10)  # 调度粒度10秒
    except KeyboardInterrupt:
        print("\n调度器停止")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


def show_status():
    """显示任务状态"""
    cfg = load_config()
    state = load_state()
    print(f"{'任务名':<20} {'状态':<8} {'间隔':<10} {'上次运行':<20} {'成功/失败'}")
    print("-" * 80)
    for name, task in cfg["tasks"].items():
        enabled = "✅启用" if task.get("enabled") else "⏸️关闭"
        interval = f"{task.get('interval',0)}s"
        last_ts = state["last_run"].get(name, 0)
        last = datetime.fromtimestamp(last_ts).strftime("%m-%d %H:%M") if last_ts else "从未"
        ok = state["run_count"].get(name, 0)
        fail = state["fail_count"].get(name, 0)
        print(f"{name:<20} {enabled:<8} {interval:<10} {last:<20} {ok}/{fail}")


def list_tasks():
    """列出所有任务配置"""
    cfg = load_config()
    print(f"共 {len(cfg['tasks'])} 个任务:")
    for name, task in cfg["tasks"].items():
        print(f"\n  [{name}] {'启用' if task.get('enabled') else '关闭'}")
        print(f"    描述: {task.get('description','')}")
        print(f"    间隔: {task.get('interval',0)}秒")
        print(f"    优先级: {task.get('priority','?')}")
        print(f"    脚本: {task.get('script','')}")


def run_manual(task_name):
    """手动执行某个任务"""
    cfg = load_config()
    if task_name not in cfg["tasks"]:
        print(f"任务 {task_name} 不存在")
        return
    task = cfg["tasks"][task_name]
    success, output = run_task(task_name, task)
    print(f"\n最终结果: {'成功' if success else '失败'}")


def main():
    parser = argparse.ArgumentParser(description="统一任务调度中心")
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="启动调度器")
    p_start.add_argument("--daemon", action="store_true", help="后台运行")
    sub.add_parser("stop", help="停止调度器")
    sub.add_parser("status", help="查看状态")
    sub.add_parser("list", help="列出任务")
    p_run = sub.add_parser("run", help="手动执行任务")
    p_run.add_argument("task_name", help="任务名")

    args = parser.parse_args()

    if args.cmd == "start":
        if args.daemon:
            subprocess.Popen([sys.executable, __file__, "start"],
                             cwd=str(ENGINE_DIR),
                             stdout=open(DATA_DIR / "scheduler.log", "a"),
                             stderr=subprocess.STDOUT)
            print("调度器已后台启动")
        else:
            scheduler_loop()
    elif args.cmd == "stop":
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text())
            os.kill(pid, 15)
            print(f"已发送停止信号 (PID={pid})")
        else:
            print("调度器未运行")
    elif args.cmd == "status":
        show_status()
    elif args.cmd == "list":
        list_tasks()
    elif args.cmd == "run":
        run_manual(args.task_name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
