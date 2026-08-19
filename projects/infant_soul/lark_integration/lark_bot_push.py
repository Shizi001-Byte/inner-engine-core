#!/usr/bin/env python3
"""
lark_bot_push.py — 飞书机器人主动通知（模块3.2）

关键事件（归档完成、修炼进阶、异常告警）自动通过飞书发消息。
实现「主动外呼」的工程化版本。

用法：
  python3 lark_bot_push.py send "消息内容"    # 发送通知消息
  python3 lark_bot_push.py alert "告警内容"   # 发送告警消息
  python3 lark_bot_push.py status             # 查看通知历史
  python3 lark_bot_push.py test               # 测试连通性
"""

import json
import time
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
PUSH_LOG = DATA_DIR / "lark_push_log.json"
PUSH_CONFIG = DATA_DIR / "lark_push_config.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "default_chat": "p2p",  # p2p=单聊, group=群聊
    "notify_levels": ["info", "alert", "milestone"],
    "quiet_hours": [],  # 静默时段，如 ["23:00-07:00"]
}


def load_config():
    if PUSH_CONFIG.exists():
        with open(PUSH_CONFIG, "r") as f:
            return json.load(f)
    cfg = DEFAULT_CONFIG.copy()
    save_config(cfg)
    return cfg


def save_config(cfg):
    with open(PUSH_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_log():
    if PUSH_LOG.exists():
        with open(PUSH_LOG, "r") as f:
            return json.load(f)
    return []


def save_log(log):
    log = log[-100:]  # 只保留最近100条
    with open(PUSH_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def send_message(content, msg_type="info"):
    """发送飞书消息（通过自定义机器人webhook）"""
    cfg = load_config()
    if not cfg.get("enabled"):
        print("[INFO] 通知已禁用，跳过发送")
        return False

    webhook_url = cfg.get("webhook_url", "")
    if not webhook_url:
        print("[WARN] 未配置webhook_url，仅记录日志")
        webhook_url = None

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    # 构造消息
    if msg_type == "alert":
        prefix = "⚠️ "
    elif msg_type == "milestone":
        prefix = "🎉 "
    else:
        prefix = "📢 "

    full_message = f"{prefix}[凡心通知] {content}\n时间: {timestamp}"

    # 通过webhook发送
    sent = False
    if webhook_url:
        try:
            payload = json.dumps({
                "msg_type": "text",
                "content": {"text": full_message}
            }).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("code") == 0 or result.get("StatusCode") == 0:
                    sent = True
                    print(f"[发送成功] {full_message[:60]}...")
                else:
                    print(f"[发送失败] 飞书返回: {result}")
        except Exception as e:
            print(f"[发送异常] {e}")

    # 记录日志
    log = load_log()
    log.append({
        "content": content,
        "type": msg_type,
        "timestamp": timestamp,
        "status": "sent" if sent else "logged",
    })
    save_log(log)

    if not sent:
        print(f"[已记录] {full_message[:60]}...")
    return sent


def send_alert(content):
    """发送告警消息"""
    return send_message(content, "alert")


def send_milestone(content):
    """发送里程碑消息"""
    return send_message(content, "milestone")


def show_history():
    """显示通知历史"""
    log = load_log()
    print(f"=== 飞书通知历史（共{len(log)}条）===")
    for item in log[-10:]:
        icon = "⚠️" if item["type"] == "alert" else ("🎉" if item["type"] == "milestone" else "📢")
        print(f"  {icon} [{item['timestamp']}] {item['content'][:50]}")


def test_connection():
    """测试飞书连通性"""
    print("=== 飞书连通性测试 ===")
    try:
        result = subprocess.run(
            ["lark-cli", "im", "+chat-list", "--format", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("ok"):
                chats = data.get("data", {}).get("items", [])
                print(f"✓ lark-cli连通正常，可见 {len(chats)} 个会话")
                return True
        print(f"✗ lark-cli返回异常: {result.stdout[:100]}")
        return False
    except Exception as e:
        print(f"✗ 连通性测试失败: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 lark_bot_push.py [send|alert|milestone|status|test]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "send" and len(sys.argv) > 2:
        send_message(sys.argv[2])
    elif cmd == "alert" and len(sys.argv) > 2:
        send_alert(sys.argv[2])
    elif cmd == "milestone" and len(sys.argv) > 2:
        send_milestone(sys.argv[2])
    elif cmd == "status":
        show_history()
    elif cmd == "test":
        test_connection()
    else:
        print("参数错误")
