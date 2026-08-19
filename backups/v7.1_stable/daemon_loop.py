#!/usr/bin/env python3
"""
观尘子引擎 V7.1 - 后台守护运行模式
非交互式自动循环执行任务队列，无任务时自动补充巡检任务。
用法: python3 daemon_loop.py [--interval 2] [--max-tasks 0]
"""
import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保能导入引擎包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import EngineV71

# ============================================================
# 配置
# ============================================================
LOG_FILE = Path(__file__).resolve().parent / "daemon.log"
PID_FILE = Path(__file__).resolve().parent / "daemon.pid"
TASK_TYPES_FOR_REFILL = [
    "health_check",
    "status_report",
    "example_compute",
    "example_hello",
]
REFILL_BATCH_SIZE = 5  # 每次补充的任务数
MAX_TOTAL_TASKS = 200  # 队列最大任务数，防止无限增长

_running = True


def _signal_handler(signum, frame):
    global _running
    _log(f"收到信号 {signum}，准备优雅退出...")
    _running = False


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [DAEMON] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _refill_tasks(engine, current_pending: int):
    """队列任务不足时自动补充巡检任务"""
    if current_pending >= REFILL_BATCH_SIZE:
        return 0
    to_add = min(REFILL_BATCH_SIZE - current_pending, MAX_TOTAL_TASKS)
    if to_add <= 0:
        return 0
    added = 0
    for i in range(to_add):
        task_type = TASK_TYPES_FOR_REFILL[i % len(TASK_TYPES_FOR_REFILL)]
        name = f"自动巡检-{task_type}-{datetime.now().strftime('%H%M%S')}-{i}"
        try:
            task = engine.submit_task(
                task_type,
                name=name,
                description=f"守护进程自动补充的{task_type}任务",
            )
            if task:
                added += 1
        except Exception as e:
            _log(f"补充任务失败 [{task_type}]: {e}")
    if added > 0:
        _log(f"自动补充了 {added} 个巡检任务")
    return added


def main():
    parser = argparse.ArgumentParser(description="观尘子引擎后台守护模式")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔秒数")
    parser.add_argument("--max-tasks", type=int, default=0, help="最多执行多少个任务后退出(0=无限)")
    parser.add_argument("--refill", action="store_true", default=True, help="无任务时自动补充")
    args = parser.parse_args()

    # 信号处理
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # PID文件
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    _log("=" * 60)
    _log("观尘子引擎 V7.1 守护进程启动")
    _log(f"PID={os.getpid()}, 轮询间隔={args.interval}s, 最大任务数={args.max_tasks or '无限'}")

    # 初始化引擎
    _log("正在初始化引擎...")
    engine = EngineV71(config_path=args.config)
    if not engine.initialize():
        _log("引擎初始化失败，退出")
        sys.exit(1)
    _log(f"引擎初始化成功，版本={engine.VERSION}")

    status = engine.get_status()
    _log(f"已加载插件: {status.get('loaded_plugins', [])}")
    _log(f"已注册任务类型: {list(engine.task_scheduler._handlers.keys())}")

    executed = 0
    idle_cycles = 0

    try:
        while _running:
            if args.max_tasks > 0 and executed >= args.max_tasks:
                _log(f"已达到最大任务数 {args.max_tasks}，退出")
                break

            # 取下一个任务
            task = engine.task_scheduler.get_next_task()
            if task is None:
                idle_cycles += 1
                # 统计当前pending数
                stats = engine.task_scheduler.get_queue_stats()
                pending = stats.get("pending", 0)
                if args.refill and pending < REFILL_BATCH_SIZE:
                    _refill_tasks(engine, pending)
                # 空闲时打印一次状态
                if idle_cycles % 30 == 1:
                    _log(f"空闲中... 队列统计: {json.dumps(stats, ensure_ascii=False)}")
                time.sleep(args.interval)
                continue

            idle_cycles = 0
            # 执行任务
            _log(f"开始执行: task_id={task.id}, type={task.type}, name={task.name}")
            t0 = time.time()
            ok = engine.task_scheduler.execute_task(task)
            elapsed = time.time() - t0
            if ok:
                executed += 1
                _log(f"任务完成: {task.id} [{task.type}] 耗时={elapsed:.2f}s (累计执行={executed})")
            else:
                _log(f"任务失败: {task.id} [{task.type}] 错误={task.error_message}")

            # 短暂休息
            time.sleep(0.5)

    except Exception as e:
        _log(f"守护进程异常: {e}")
        import traceback
        _log(traceback.format_exc())
    finally:
        _log("守护进程正在关闭...")
        try:
            engine.shutdown()
        except Exception:
            pass
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except Exception:
            pass
        _log(f"守护进程已退出，累计执行任务={executed}")
        _log("=" * 60)


if __name__ == "__main__":
    main()
