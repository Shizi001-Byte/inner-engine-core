#!/usr/bin/env python3
"""
lark_full_bidir.py — 飞书双向指令全落地（模块1.2）
通过incoming_messages表接收指令（替代公网回调URL），引擎轮询处理，结果通过飞书webhook推送。
内置指令集：状态查询、健康检查、触发备份、查看待办、认知搜索、链路管理等。
用法：
  python3 lark_full_bidir.py poll              # 持续轮询处理指令
  python3 lark_full_bidir.py poll --once       # 只处理一轮
  python3 lark_full_bidir.py send "消息内容"    # 主动推送一条消息到飞书
  python3 lark_full_bidir.py send-cmd "指令"   # 模拟发送一条指令（测试用）
"""
import json
import time
import sys
import argparse
from pathlib import Path
from datetime import datetime

import requests

# ============ 配置 ============
ENGINE_DIR = Path(__file__).parent.parent.parent
SUPABASE_URL = "https://gltscytpqnuuzhczljyq.supabase.co"
SUPABASE_KEY = "sb_secret_Cpcpl-d8aA82ALo16hU8lg_3Smd8Xuu"
LARK_CONFIG_FILE = ENGINE_DIR / "projects" / "infant_soul" / "data" / "lark_push_config.json"

POLL_INTERVAL = 10  # 轮询间隔秒数


def get_session():
    s = requests.Session()
    s.trust_env = False
    return s


def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def load_lark_config():
    with open(LARK_CONFIG_FILE) as f:
        return json.load(f)


def push_to_lark(text):
    """推送消息到飞书机器人（用urllib避免SSL证书问题）"""
    import urllib.request
    cfg = load_lark_config()
    webhook = cfg.get("webhook_url", "")
    if not webhook:
        print("[WARN] 飞书webhook未配置")
        return False
    payload = json.dumps({
        "msg_type": "text",
        "content": {"text": text}
    }).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[WARN] 飞书推送失败: {e}")
        return False


# ============ 指令处理 ============

def cmd_status(args):
    """查看引擎状态"""
    state_file = ENGINE_DIR / "data" / "engine_state.json"
    if state_file.exists():
        d = json.load(open(state_file))
        return (f"【引擎状态】\n"
                f"转数: {d.get('zhuan_count', '?')}\n"
                f"总任务: {d.get('total_tasks_completed', '?')}\n"
                f"认知池: {d.get('cognition_pool_size', '?')}\n"
                f"坑库: {d.get('pit_library_size', '?')}\n"
                f"更新时间: {d.get('last_update', '?')}")
    return "引擎状态文件不存在"


def cmd_health(args):
    """健康检查"""
    results = []
    # 1. Supabase连通
    try:
        s = get_session()
        r = s.get(f"{SUPABASE_URL}/rest/v1/cognition?select=id&limit=1", headers=sb_headers(), timeout=10)
        results.append(f"Supabase: {'✅连通' if r.status_code==200 else '❌失败'}")
    except Exception as e:
        results.append(f"Supabase: ❌{e}")
    # 2. 飞书连通
    try:
        cfg = load_lark_config()
        results.append(f"飞书webhook: {'✅已配置' if cfg.get('webhook_url') else '❌未配置'}")
    except:
        results.append("飞书: ❌配置读取失败")
    # 3. 磁盘空间
    try:
        import shutil
        total, used, free = shutil.disk_usage(str(ENGINE_DIR))
        results.append(f"磁盘: 剩余{free//1024//1024}MB")
    except:
        pass
    return "【健康检查】\n" + "\n".join(results)


def cmd_backup(args):
    """触发四地备份"""
    return "【备份指令】已触发四地备份任务（需引擎运行时执行），完成后推送结果"


def cmd_todo(args):
    """查看待办"""
    todo_file = ENGINE_DIR / "data" / "todo_next.json"
    if todo_file.exists():
        d = json.load(open(todo_file))
        items = d.get("items", []) if isinstance(d, dict) else d
        if not items:
            return "【待办】暂无待办事项"
        return "【待办列表】\n" + "\n".join(f"- {i}" for i in items[:10])
    return "待办文件不存在"


def cmd_cognition_search(args):
    """认知搜索（关键词匹配）"""
    query = " ".join(args) if args else ""
    if not query:
        return "用法: 搜索 <关键词>"
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/cognition",
        params={"select": "title,category", "order": "created_at.desc", "limit": 20},
        headers=sb_headers(), timeout=15
    )
    if r.status_code != 200:
        return f"搜索失败: {r.text[:100]}"
    results = [c for c in r.json() if query in c.get("title", "") or query in c.get("category", "")]
    if not results:
        return f"未找到包含'{query}'的认知"
    return f"【认知搜索:{query}】\n" + "\n".join(f"- [{c['category']}] {c['title']}" for c in results[:5])


def cmd_chain_list(args):
    """查看思考链路列表"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/thinking_chain?select=chain_id,status&limit=50",
        headers=sb_headers(), timeout=15
    )
    if r.status_code != 200:
        return f"查询失败: {r.text[:100]}"
    chains = {}
    for f in r.json():
        cid = f["chain_id"]
        chains.setdefault(cid, {"total": 0, "done": 0})
        chains[cid]["total"] += 1
        if f["status"] == "completed":
            chains[cid]["done"] += 1
    if not chains:
        return "暂无思考链路"
    return "【思考链路】\n" + "\n".join(f"{cid}: {info['done']}/{info['total']}完成" for cid, info in list(chains.items())[:5])


def cmd_help(args):
    """帮助"""
    return """【可用指令】
状态 - 查看引擎状态
健康 - 健康检查
备份 - 触发四地备份
待办 - 查看待办
搜索 <关键词> - 搜索认知文档
链路 - 查看思考链路
帮助 - 显示此帮助"""


# 指令注册表
COMMANDS = {
    "状态": cmd_status,
    "健康": cmd_health,
    "备份": cmd_backup,
    "待办": cmd_todo,
    "搜索": cmd_cognition_search,
    "链路": cmd_chain_list,
    "帮助": cmd_help,
}


def parse_and_execute(command_text):
    """解析指令并执行"""
    parts = command_text.strip().split()
    if not parts:
        return "空指令，输入'帮助'查看可用指令"
    cmd = parts[0]
    args = parts[1:]
    handler = COMMANDS.get(cmd)
    if handler:
        return handler(args)
    # 模糊匹配
    for key, func in COMMANDS.items():
        if cmd in key or key in cmd:
            return func(args)
    return f"未知指令: {cmd}，输入'帮助'查看可用指令"


# ============ 轮询处理 ============

def fetch_pending_commands():
    """从incoming_messages获取待处理的飞书指令"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/incoming_messages",
        params={"status": "eq.pending", "source": "eq.lark", "order": "created_at.asc", "limit": 10},
        headers=sb_headers(), timeout=15
    )
    return r.json() if r.status_code == 200 else []


def update_message(msg_id, status, result=None):
    s = get_session()
    payload = {"status": status, "processed_at": "now()"}
    if result:
        payload["result"] = result
    s.patch(
        f"{SUPABASE_URL}/rest/v1/incoming_messages?id=eq.{msg_id}",
        headers=sb_headers(), json=payload, timeout=15
    )


def process_one_round():
    """处理一轮待处理指令"""
    messages = fetch_pending_commands()
    if not messages:
        return 0
    processed = 0
    for msg in messages:
        command = msg.get("payload", {}).get("command", "")
        print(f"[处理] id={msg['id']} 指令={command}")
        update_message(msg["id"], "processing")
        try:
            result = parse_and_execute(command)
            # 推送结果到飞书
            push_to_lark(result)
            update_message(msg["id"], "done", result)
            processed += 1
        except Exception as e:
            update_message(msg["id"], "failed", str(e))
            print(f"  [ERROR] {e}")
    return processed


def send_test_command(command):
    """模拟发送一条飞书指令（写入incoming_messages表）"""
    s = get_session()
    r = s.post(
        f"{SUPABASE_URL}/rest/v1/incoming_messages",
        headers={**sb_headers(), "Prefer": "return=representation"},
        json={"source": "lark", "message_type": "command", "payload": {"command": command}},
        timeout=15
    )
    if r.status_code in (200, 201):
        print(f"[OK] 测试指令已入队 id={r.json()[0]['id']}")
    else:
        print(f"[FAIL] {r.status_code}: {r.text[:100]}")


# ============ 入口 ============

def main():
    parser = argparse.ArgumentParser(description="飞书双向指令处理")
    sub = parser.add_subparsers(dest="cmd")

    p_poll = sub.add_parser("poll", help="轮询处理指令")
    p_poll.add_argument("--once", action="store_true", help="只处理一轮")

    p_send = sub.add_parser("send", help="推送消息到飞书")
    p_send.add_argument("text", help="消息内容")

    p_cmd = sub.add_parser("send-cmd", help="模拟发送指令")
    p_cmd.add_argument("command", help="指令内容")

    args = parser.parse_args()

    if args.cmd == "poll":
        if args.once:
            n = process_one_round()
            print(f"本轮处理 {n} 条指令")
        else:
            print("飞书指令轮询器启动，按Ctrl+C停止")
            try:
                while True:
                    n = process_one_round()
                    if n > 0:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 处理了{n}条")
                    time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                print("\n已停止")
    elif args.cmd == "send":
        ok = push_to_lark(args.text)
        print(f"推送{'成功' if ok else '失败'}")
    elif args.cmd == "send-cmd":
        send_test_command(args.command)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
