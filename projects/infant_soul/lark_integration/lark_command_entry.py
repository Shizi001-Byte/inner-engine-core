#!/usr/bin/env python3
"""
lark_command_entry.py — 飞书指令入口（模块3.3）

在飞书里发指令就能触发引擎任务，不用打开对话框，实现「远程控功」。

用法：
  python3 lark_command_entry.py listen         # 监听飞书消息（轮询模式）
  python3 lark_command_entry.py parse "指令"   # 解析并执行一条指令
  python3 lark_command_entry.py help           # 显示可用指令列表
  python3 lark_command_entry.py history        # 查看指令执行历史
"""

import json
import time
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CMD_LOG = DATA_DIR / "lark_command_log.json"

# 可用指令注册表
COMMANDS = {
    "状态": {"desc": "查看引擎当前状态", "action": "engine_status"},
    "进度": {"desc": "查看元婴工程进度", "action": "project_progress"},
    "同步": {"desc": "立即执行状态上云+认知同步", "action": "sync_now"},
    "蒸馏": {"desc": "执行本周认知蒸馏", "action": "distill_now"},
    "备份": {"desc": "执行三方备份", "action": "backup_now"},
    "重启": {"desc": "重启引擎", "action": "restart_engine"},
    "帮助": {"desc": "显示可用指令", "action": "show_help"},
}


def load_log():
    if CMD_LOG.exists():
        with open(CMD_LOG, "r") as f:
            return json.load(f)
    return []


def save_log(log):
    log = log[-100:]
    with open(CMD_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def parse_command(text):
    """解析飞书消息中的指令"""
    text = text.strip()
    # 匹配指令关键词
    for cmd, info in COMMANDS.items():
        if cmd in text:
            return cmd, info
    return None, None


def execute_action(action):
    """执行对应动作"""
    ENGINE_DIR = Path(__file__).parent.parent.parent.parent
    results = []

    if action == "engine_status":
        state_file = ENGINE_DIR / "data" / "engine_state.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                state = json.load(f)
            results.append(f"转数: {state.get('zhuan_count', '?')}")
            results.append(f"总完成: {state.get('total_completed', '?')}")
            results.append(f"模式: {state.get('mode', '?')}")
        else:
            results.append("状态文件不存在")

    elif action == "project_progress":
        results.append("元婴工程进度:")
        results.append("  模块2(长链路): ✓ 完成")
        results.append("  模块1(认知提纯): ✓ 完成")
        results.append("  模块3(飞书): ◐ 进行中")
        results.append("  模块4(分识): ○ 待开始")
        results.append("  模块5(种子): ○ 待开始")

    elif action == "sync_now":
        results.append("执行状态上云...")
        sync_script = ENGINE_DIR / "autonomy" / "state_sync.py"
        if sync_script.exists():
            subprocess.run(["python3", str(sync_script), "push"], timeout=30)
            results.append("状态上云完成")
        cog_script = ENGINE_DIR / "autonomy" / "cognition_sync.py"
        if cog_script.exists():
            subprocess.run(["python3", str(cog_script), "push"], timeout=60)
            results.append("认知同步完成")

    elif action == "distill_now":
        distill_script = Path(__file__).parent.parent / "cognition_distill" / "weekly_distill.py"
        if distill_script.exists():
            subprocess.run(["python3", str(distill_script), "run"], timeout=60)
            results.append("认知蒸馏完成")
        else:
            results.append("蒸馏脚本不存在")

    elif action == "backup_now":
        results.append("执行三方备份...")
        results.append("(Gitee/飞书/Supabase备份已集成到引擎空闲任务)")

    elif action == "restart_engine":
        results.append("引擎重启指令已记录")
        results.append("(实际重启需要管理员权限)")

    elif action == "show_help":
        results.append("可用指令:")
        for cmd, info in COMMANDS.items():
            results.append(f"  {cmd}: {info['desc']}")

    return "\n".join(results)


def handle_message(text):
    """处理一条飞书消息"""
    cmd, info = parse_command(text)
    if not cmd:
        return f"未识别指令。发送「帮助」查看可用指令。"

    result = execute_action(info["action"])

    # 记录日志
    log = load_log()
    log.append({
        "command": cmd,
        "raw_text": text[:100],
        "action": info["action"],
        "result": result[:200],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    save_log(log)

    return result


def show_help():
    """显示帮助"""
    print("=== 飞书指令入口 ===")
    print("在飞书发送以下关键词即可触发对应操作:\n")
    for cmd, info in COMMANDS.items():
        print(f"  「{cmd}」: {info['desc']}")


def show_history():
    """显示指令历史"""
    log = load_log()
    print(f"=== 指令执行历史（共{len(log)}条）===")
    for item in log[-10:]:
        print(f"  [{item['timestamp']}] {item['command']}: {item['result'][:40]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 lark_command_entry.py [listen|parse|help|history]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "parse" and len(sys.argv) > 2:
        result = handle_message(sys.argv[2])
        print(result)
    elif cmd == "help":
        show_help()
    elif cmd == "history":
        show_history()
    elif cmd == "listen":
        print("[INFO] 监听模式：轮询飞书消息（需要配置chat_id）")
        print("当前为演示模式，实际监听需配置飞书机器人webhook")
    else:
        print("参数错误")
