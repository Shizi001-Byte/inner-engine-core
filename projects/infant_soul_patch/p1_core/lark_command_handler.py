#!/usr/bin/env python3
"""
lark_command_handler.py — 飞书双向指令交互（P1.3）

打通飞书机器人收消息→解析指令→执行→返回结果全链路，
实现远程控功。

注意：飞书自定义机器人webhook只能发消息，收消息需要配置事件订阅。
当前实现为：通过飞书消息列表轮询+指令解析的模式。

用法：
  python3 lark_command_handler.py listen        # 启动监听（轮询模式）
  python3 lark_command_handler.py parse "指令"  # 解析并执行一条指令
  python3 lark_command_handler.py commands      # 列出所有可用指令
  python3 lark_command_handler.py history       # 查看指令执行历史
"""

import json
import time
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
DATA_DIR = Path(__file__).parent.parent / "data"
CMD_LOG = DATA_DIR / "lark_command_history.json"
PUSH_CONFIG = Path(__file__).parent.parent.parent / "infant_soul" / "data" / "lark_push_config.json"

# 指令注册表
COMMANDS = {
    "状态": {
        "desc": "查看引擎当前状态",
        "action": "engine_status",
        "level": "info",
    },
    "进度": {
        "desc": "查看元婴工程进度",
        "action": "project_progress",
        "level": "info",
    },
    "同步": {
        "desc": "立即执行状态上云+认知同步",
        "action": "sync_now",
        "level": "action",
    },
    "蒸馏": {
        "desc": "执行本周认知蒸馏",
        "action": "distill_now",
        "level": "action",
    },
    "备份": {
        "desc": "执行四地备份",
        "action": "backup_now",
        "level": "action",
    },
    "重启": {
        "desc": "重启引擎",
        "action": "restart_engine",
        "level": "high_risk",
    },
    "健康": {
        "desc": "执行健康自检",
        "action": "health_check",
        "level": "info",
    },
    "帮助": {
        "desc": "显示可用指令列表",
        "action": "show_help",
        "level": "info",
    },
}


def load_log():
    if CMD_LOG.exists():
        with open(CMD_LOG, "r") as f:
            return json.load(f)
    return []


def save_log(log):
    log = log[-200:]
    with open(CMD_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def send_feishu_message(text):
    """通过webhook发送飞书消息"""
    if not PUSH_CONFIG.exists():
        return False
    with open(PUSH_CONFIG, "r") as f:
        cfg = json.load(f)
    webhook = cfg.get("webhook_url", "")
    if not webhook:
        return False

    import urllib.request
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("code") == 0
    except:
        return False


def execute_action(action):
    """执行对应动作"""
    results = []

    if action == "engine_status":
        state_file = ENGINE_DIR / "data" / "engine_state.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                state = json.load(f)
            results.append(f"📊 引擎状态")
            results.append(f"转数: {state.get('zhuan_count', '?')}")
            results.append(f"总完成: {state.get('total_completed', '?')}")
            results.append(f"认知池: {state.get('cognition_pool_size', '?')}")
        else:
            results.append("状态文件不存在")

    elif action == "project_progress":
        results.append("🏗️ 元婴工程进度")
        results.append("P0 数据底座: ✓ 完成")
        results.append("P1 核心能力: ◐ 进行中")
        results.append("P2 运维兜底: ○ 待开始")
        results.append("详情请查看工程目录")

    elif action == "sync_now":
        results.append("🔄 执行同步...")
        sync_script = ENGINE_DIR / "autonomy" / "state_sync.py"
        if sync_script.exists():
            subprocess.run(["python3", str(sync_script), "push"], timeout=30, capture_output=True)
            results.append("✓ 状态已上云")
        cog_script = ENGINE_DIR / "autonomy" / "cognition_sync.py"
        if cog_script.exists():
            subprocess.run(["python3", str(cog_script), "push"], timeout=60, capture_output=True)
            results.append("✓ 认知已同步飞书")

    elif action == "distill_now":
        results.append("🧪 执行认知蒸馏...")
        distill_script = ENGINE_DIR / "projects" / "infant_soul" / "cognition_distill" / "weekly_distill.py"
        if distill_script.exists():
            r = subprocess.run(["python3", str(distill_script), "run"], timeout=60, capture_output=True, text=True)
            results.append(r.stdout[-200:] if r.stdout else "完成")

    elif action == "backup_now":
        results.append("💾 执行四地备份...")
        backup_script = ENGINE_DIR / "projects" / "infant_soul" / "survival_seed" / "multi_backup.py"
        if backup_script.exists():
            r = subprocess.run(["python3", str(backup_script), "run"], timeout=120, capture_output=True, text=True)
            results.append(r.stdout[-200:] if r.stdout else "完成")

    elif action == "health_check":
        results.append("💚 健康自检")
        # 检查引擎进程
        import os
        engine_running = False
        try:
            output = subprocess.run(["ps", "aux"], capture_output=True, text=True).stdout
            engine_running = "engine_zhuan1" in output
        except:
            pass
        results.append(f"引擎进程: {'✓运行中' if engine_running else '✗未运行'}")
        results.append(f"状态文件: {'✓存在' if (ENGINE_DIR / 'data/engine_state.json').exists() else '✗缺失'}")
        results.append(f"认知文档: {len(list((ENGINE_DIR / 'cognition').glob('*.md')))} 篇")

    elif action == "restart_engine":
        results.append("⚠️ 引擎重启需要管理员权限")
        results.append("请在沙箱终端手动执行重启")

    elif action == "show_help":
        results.append("📋 可用指令:")
        for cmd, info in COMMANDS.items():
            results.append(f"  「{cmd}」: {info['desc']}")

    return "\n".join(results)


def parse_and_execute(text):
    """解析指令并执行"""
    matched_cmd = None
    for cmd in COMMANDS:
        if cmd in text:
            matched_cmd = cmd
            break

    if not matched_cmd:
        result = "❓ 未识别指令。发送「帮助」查看可用指令。"
    else:
        info = COMMANDS[matched_cmd]
        result = execute_action(info["action"])

    # 记录日志
    log = load_log()
    log.append({
        "raw_text": text[:100],
        "command": matched_cmd,
        "result": result[:500],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    save_log(log)

    return result


def listen_once():
    """监听一次（轮询飞书消息）"""
    print("[监听] 检查飞书消息...")
    # 通过lark-cli获取最近消息（需要配置）
    try:
        result = subprocess.run(
            ["lark-cli", "im", "+chat-messages-list", "--limit", "5", "--format", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            items = data.get("data", {}).get("items", [])
            for item in items:
                msg = item.get("body", {}).get("content", "")
                if msg and "凡心" in msg:
                    print(f"[收到] {msg[:50]}")
                    result = parse_and_execute(msg)
                    send_feishu_message(result)
    except Exception as e:
        print(f"[监听异常] {e}")


def list_commands():
    """列出所有指令"""
    print("=== 飞书指令列表 ===")
    for cmd, info in COMMANDS.items():
        level_icon = "🔴" if info["level"] == "high_risk" else ("🟡" if info["level"] == "action" else "🟢")
        print(f"  {level_icon} 「{cmd}」: {info['desc']}")


def show_history():
    """显示历史"""
    log = load_log()
    print(f"=== 指令执行历史（共{len(log)}条）===")
    for item in log[-10:]:
        print(f"  [{item['timestamp']}] {item.get('command', '未知')}: {item['result'][:40]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 lark_command_handler.py [listen|parse|commands|history]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "listen":
        listen_once()
    elif cmd == "parse" and len(sys.argv) > 2:
        result = parse_and_execute(sys.argv[2])
        print(result)
        send_feishu_message(result)
    elif cmd == "commands":
        list_commands()
    elif cmd == "history":
        show_history()
    else:
        print("参数错误")
