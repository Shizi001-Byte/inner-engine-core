import os
#!/usr/bin/env python3
"""
message_poller.py — 入站消息轮询处理器（替代公网IP方案）
定时轮询Supabase的incoming_messages表，处理pending状态的消息。
支持QStash定时任务、飞书指令、手动触发等多种来源。
用法：
  python3 message_poller.py          # 前台运行，持续轮询
  python3 message_poller.py --once   # 只处理一次
  python3 message_poller.py --send "来源" "类型" '{"key":"value"}'  # 手动发一条测试消息
"""
import json
import time
import sys
from pathlib import Path

import requests

ENGINE_DIR = Path(__file__).parent.parent.parent
SUPABASE_URL = "https://gltscytpqnuuzhczljyq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")  # P0修复：不从代码硬编码，防止泄露到git
POLL_INTERVAL = 10  # 轮询间隔秒数


def get_session():
    s = requests.Session()
    s.trust_env = False
    return s


def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def fetch_pending_messages(limit=10):
    """获取待处理消息"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/incoming_messages",
        params={
            "status": "eq.pending",
            "order": "created_at.asc",
            "limit": limit,
        },
        headers=get_headers(),
        timeout=15,
    )
    if r.status_code == 200:
        return r.json()
    return []


def update_message(msg_id, status, result=None):
    """更新消息状态"""
    s = get_session()
    payload = {"status": status, "processed_at": "now()"}
    if result:
        payload["result"] = result
    s.patch(
        f"{SUPABASE_URL}/rest/v1/incoming_messages?id=eq.{msg_id}",
        headers=get_headers(),
        json=payload,
        timeout=15,
    )


def send_message(source, message_type, payload_dict):
    """手动发送一条消息到入站队列（测试用）"""
    s = get_session()
    r = s.post(
        f"{SUPABASE_URL}/rest/v1/incoming_messages",
        headers={**get_headers(), "Prefer": "return=representation"},
        json={
            "source": source,
            "message_type": message_type,
            "payload": payload_dict,
        },
        timeout=15,
    )
    if r.status_code in (200, 201):
        msg = r.json()[0]
        print(f"[OK] 消息已入队 id={msg['id']}")
        return msg["id"]
    else:
        print(f"[FAIL] {r.status_code}: {r.text[:200]}")
        return None


def process_message(msg):
    """处理单条消息（根据来源和类型分发）"""
    source = msg.get("source", "")
    msg_type = msg.get("message_type", "")
    payload = msg.get("payload", {})

    print(f"[处理] id={msg['id']} source={source} type={msg_type}")

    # 根据消息类型执行对应动作
    if msg_type == "engine_command":
        command = payload.get("command", "")
        result = f"引擎指令已接收: {command}"
        # 这里可以接入实际的引擎指令执行逻辑
    elif msg_type == "health_check":
        result = "引擎状态正常"
    elif msg_type == "cognition_query":
        query = payload.get("query", "")
        result = f"认知查询: {query}（待接入向量搜索）"
    else:
        result = f"已处理: {source}/{msg_type}"

    print(f"  结果: {result}")
    return result


def run_once():
    """处理一轮待处理消息"""
    messages = fetch_pending_messages()
    if not messages:
        return 0

    processed = 0
    for msg in messages:
        # 标记为processing
        update_message(msg["id"], "processing")
        try:
            result = process_message(msg)
            update_message(msg["id"], "done", result)
            processed += 1
        except Exception as e:
            update_message(msg["id"], "failed", str(e))
            print(f"  [ERROR] {e}")

    return processed


def main():
    if "--send" in sys.argv:
        idx = sys.argv.index("--send")
        if idx + 3 < len(sys.argv):
            source = sys.argv[idx + 1]
            msg_type = sys.argv[idx + 2]
            payload = json.loads(sys.argv[idx + 3])
            send_message(source, msg_type, payload)
        else:
            print("用法: --send <来源> <类型> '<json payload>'")
        return

    if "--once" in sys.argv:
        count = run_once()
        print(f"本轮处理 {count} 条消息")
        return

    # 持续轮询模式
    print("=== 入站消息轮询器启动 ===")
    print(f"轮询间隔: {POLL_INTERVAL}秒")
    print("按 Ctrl+C 停止")
    try:
        while True:
            count = run_once()
            if count > 0:
                print(f"[{time.strftime('%H:%M:%S')}] 处理了 {count} 条消息")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n轮询器已停止")


if __name__ == "__main__":
    main()
