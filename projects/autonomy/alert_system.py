#!/usr/bin/env python3
"""
alert_system.py — 异常分级告警系统（模块2.4）
三级告警：info(日常通知)、warning(功能异常)、critical(核心故障)
不同级别推送不同频次，避免刷屏。
用法：
  python3 alert_system.py send <level> "消息"   # 发送告警
  python3 alert_system.py history                 # 查看告警历史
  python3 alert_system.py test                    # 测试三级告警
"""
import json
import time
import urllib.request
import argparse
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
ALERT_LOG = DATA_DIR / "alert_history.json"

# 告警级别配置
LEVELS = {
    "info": {"icon": "ℹ️", "cooldown": 3600, "name": "信息"},
    "warning": {"icon": "⚠️", "cooldown": 600, "name": "警告"},
    "critical": {"icon": "🚨", "cooldown": 0, "name": "严重"},
}


def load_lark_config():
    cfg_file = ENGINE_DIR / "projects" / "infant_soul" / "data" / "lark_push_config.json"
    if cfg_file.exists():
        return json.load(open(cfg_file))
    return {}


def push_to_lark(text):
    cfg = load_lark_config()
    webhook = cfg.get("webhook_url", "")
    if not webhook:
        return False
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except:
        return False


def load_history():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ALERT_LOG.exists():
        return json.load(open(ALERT_LOG))
    return {"alerts": [], "last_sent": {}}


def save_history(h):
    with open(ALERT_LOG, "w") as f:
        json.dump(h, f, indent=2, ensure_ascii=False)


def send_alert(level, message, force=False):
    """发送分级告警"""
    if level not in LEVELS:
        print(f"未知级别: {level}")
        return False
    cfg = LEVELS[level]
    history = load_history()
    now = time.time()

    # 冷却检查（critical不冷却）
    if not force and cfg["cooldown"] > 0:
        last = history["last_sent"].get(level, 0)
        if now - last < cfg["cooldown"]:
            print(f"[{cfg['name']}] 冷却中，跳过（距上次{int(now-last)}秒）")
            # 仍然记录但不推送
            history["alerts"].append({"level": level, "message": message, "time": now, "pushed": False})
            save_history(history)
            return False

    text = f"{cfg['icon']} [{cfg['name']}告警]\n{message}\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}"
    success = push_to_lark(text)

    history["alerts"].append({"level": level, "message": message, "time": now, "pushed": success})
    history["last_sent"][level] = now
    # 只保留最近100条
    history["alerts"] = history["alerts"][-100:]
    save_history(history)

    print(f"[{cfg['name']}] 告警{'推送成功' if success else '推送失败'}: {message[:50]}")
    return success


def show_history(limit=20):
    history = load_history()
    alerts = history["alerts"][-limit:]
    print(f"最近 {len(alerts)} 条告警:")
    for a in reversed(alerts):
        ts = datetime.fromtimestamp(a["time"]).strftime("%m-%d %H:%M")
        pushed = "✅" if a["pushed"] else "⏸️"
        print(f"  {ts} {pushed} [{a['level']}] {a['message'][:60]}")


def main():
    parser = argparse.ArgumentParser(description="异常分级告警系统")
    sub = parser.add_subparsers(dest="cmd")
    p_send = sub.add_parser("send")
    p_send.add_argument("level", choices=["info", "warning", "critical"])
    p_send.add_argument("message")
    p_send.add_argument("--force", action="store_true")
    sub.add_parser("history")
    sub.add_parser("test")
    args = parser.parse_args()

    if args.cmd == "send":
        send_alert(args.level, args.message, args.force)
    elif args.cmd == "history":
        show_history()
    elif args.cmd == "test":
        print("测试三级告警:")
        send_alert("info", "这是一条信息级测试告警", force=True)
        send_alert("warning", "这是一条警告级测试告警", force=True)
        send_alert("critical", "这是一条严重级测试告警", force=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
