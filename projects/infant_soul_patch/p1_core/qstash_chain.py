#!/usr/bin/env python3
"""
qstash_chain.py — QStash接入长链路思考（P1.1）

将思考分片任务接入消息队列，实现跨会话接力、定时触发、失败重试，
真正突破单轮次限制。

QStash是Upstash提供的消息队列+定时调度服务，通过HTTP API调用。

用法：
  python3 qstash_chain.py enqueue "问题"    # 将问题入队，异步处理
  python3 qstash_chain.py process           # 处理队列中的下一个任务
  python3 qstash_chain.py status            # 查看队列状态
  python3 qstash_chain.py schedule "问题" --delay 60  # 延迟60秒后处理
"""

import json
import time
import uuid
import sys
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
QUEUE_FILE = DATA_DIR / "qstash_queue.json"
CONFIG_FILE = DATA_DIR / "qstash_config.json"

DEFAULT_CONFIG = {
    "enabled": False,  # 需要配置QStash token后启用
    "qstash_url": "https://qstash.upstash.io/v2/publish",
    "qstash_token": "",  # 需要施子配置
    "webhook_url": "",   # 处理结果回调地址
    "max_retries": 3,
    "delay_seconds": 0,
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    cfg = DEFAULT_CONFIG.copy()
    save_config(cfg)
    return cfg


def save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_queue():
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    return {"pending": [], "processing": [], "completed": [], "failed": []}


def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def enqueue_task(question, delay=0):
    """将任务入队"""
    cfg = load_config()
    queue = load_queue()

    task_id = str(uuid.uuid4())[:8]
    task = {
        "task_id": task_id,
        "question": question,
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "delay_seconds": delay,
        "retries": 0,
        "max_retries": cfg["max_retries"],
        "result": None,
    }

    # 如果QStash已配置，发送到远程队列
    if cfg.get("enabled") and cfg.get("qstash_token"):
        try:
            payload = json.dumps({"task_id": task_id, "question": question}).encode()
            headers = {
                "Authorization": f"Bearer {cfg['qstash_token']}",
                "Content-Type": "application/json",
            }
            if delay > 0:
                headers["Upstash-Delay"] = f"{delay}s"

            req = urllib.request.Request(cfg["qstash_url"], data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                task["qstash_message_id"] = result.get("messageId", "")
            print(f"[QStash] 任务已发送到远程队列: {task_id}")
        except Exception as e:
            print(f"[QStash] 远程入队失败，使用本地队列: {e}")

    queue["pending"].append(task)
    save_queue(queue)
    print(f"[OK] 任务已入队: {task_id}")
    print(f"     问题: {question[:50]}...")
    print(f"     延迟: {delay}秒" if delay > 0 else "     立即处理")
    return task_id


def process_next():
    """处理队列中的下一个任务"""
    queue = load_queue()
    if not queue["pending"]:
        print("[INFO] 队列为空")
        return None

    task = queue["pending"].pop(0)
    task["status"] = "processing"
    task["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    queue["processing"].append(task)
    save_queue(queue)

    print(f"[处理] 任务 {task['task_id']}: {task['question'][:50]}...")

    # 模拟处理（实际接入chain_fragment.py）
    time.sleep(1)
    task["status"] = "completed"
    task["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    task["result"] = f"处理完成（模拟）: {task['question'][:30]}..."

    queue["processing"].remove(task)
    queue["completed"].append(task)
    save_queue(queue)

    print(f"[OK] 任务完成: {task['task_id']}")
    return task


def retry_failed():
    """重试失败的任务"""
    queue = load_queue()
    if not queue["failed"]:
        print("[INFO] 没有失败的任务")
        return

    retried = 0
    for task in queue["failed"]:
        if task["retries"] < task["max_retries"]:
            task["retries"] += 1
            task["status"] = "pending"
            queue["pending"].append(task)
            queue["failed"].remove(task)
            retried += 1
            print(f"  重试: {task['task_id']} (第{task['retries']}次)")

    save_queue(queue)
    print(f"[OK] 已重试 {retried} 个任务")


def show_status():
    """查看队列状态"""
    queue = load_queue()
    cfg = load_config()
    print("=== QStash长链路队列状态 ===")
    print(f"远程QStash: {'已启用' if cfg.get('enabled') else '未启用（使用本地队列）'}")
    print(f"待处理: {len(queue['pending'])}")
    print(f"处理中: {len(queue['processing'])}")
    print(f"已完成: {len(queue['completed'])}")
    print(f"失败: {len(queue['failed'])}")

    if queue["pending"]:
        print(f"\n待处理任务:")
        for t in queue["pending"][:5]:
            print(f"  {t['task_id']}: {t['question'][:40]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 qstash_chain.py [enqueue|process|status|retry]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "enqueue" and len(sys.argv) > 2:
        delay = 0
        if "--delay" in sys.argv:
            idx = sys.argv.index("--delay")
            if idx + 1 < len(sys.argv):
                delay = int(sys.argv[idx + 1])
        enqueue_task(sys.argv[2], delay)
    elif cmd == "process":
        process_next()
    elif cmd == "status":
        show_status()
    elif cmd == "retry":
        retry_failed()
    else:
        print("参数错误")
