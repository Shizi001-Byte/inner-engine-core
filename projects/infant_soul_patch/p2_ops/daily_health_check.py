#!/usr/bin/env python3
"""
daily_health_check.py — 每日健康自检报告（P2.2）

每日凌晨自动检测引擎、数据库、飞书、模型API四路状态，
生成报告推送飞书。

用法：
  python3 daily_health_check.py run       # 执行健康自检并推送报告
  python3 daily_health_check.py status    # 查看最近一次自检结果
  python3 daily_health_check.py history   # 查看自检历史
"""

import json
import time
import subprocess
import sys
import os
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
DATA_DIR = Path(__file__).parent.parent / "data"
HEALTH_LOG = DATA_DIR / "health_check_history.json"
PUSH_CONFIG = Path(__file__).parent.parent.parent / "infant_soul" / "data" / "lark_push_config.json"


def send_report(text):
    """推送报告到飞书"""
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


def check_engine():
    """检查引擎状态"""
    result = {"name": "引擎进程", "status": "unknown", "detail": ""}
    pid_file = ENGINE_DIR / "data" / "engine.pid"
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            result["status"] = "ok"
            result["detail"] = f"PID {pid} 运行中"
        except:
            result["status"] = "error"
            result["detail"] = "PID文件存在但进程不存在"
    else:
        result["status"] = "error"
        result["detail"] = "PID文件不存在"

    # 检查状态文件
    state_file = ENGINE_DIR / "data" / "engine_state.json"
    if state_file.exists():
        with open(state_file, "r") as f:
            state = json.load(f)
        result["zhuan"] = state.get("zhuan_count", "?")
        result["total"] = state.get("total_completed", "?")
    return result


def check_database():
    """检查Supabase数据库"""
    result = {"name": "Supabase数据库", "status": "unknown", "detail": ""}
    backup_config = ENGINE_DIR / "data" / "backup_config.json"
    if not backup_config.exists():
        result["status"] = "error"
        result["detail"] = "配置文件不存在"
        return result

    with open(backup_config, "r") as f:
        cfg = json.load(f)
    sb = cfg["backup_targets"]["supabase"]
    url = sb["url"]
    key = sb["service_role_key"]

    import urllib.request
    try:
        req = urllib.request.Request(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result["status"] = "ok"
            result["detail"] = "连接正常"
    except Exception as e:
        result["status"] = "warning"
        result["detail"] = f"连接异常: {str(e)[:50]}"
    return result


def check_feishu():
    """检查飞书连通性"""
    result = {"name": "飞书机器人", "status": "unknown", "detail": ""}
    if not PUSH_CONFIG.exists():
        result["status"] = "error"
        result["detail"] = "webhook未配置"
        return result
    with open(PUSH_CONFIG, "r") as f:
        cfg = json.load(f)
    if cfg.get("webhook_url"):
        result["status"] = "ok"
        result["detail"] = "webhook已配置"
    else:
        result["status"] = "error"
        result["detail"] = "webhook为空"
    return result


def check_models():
    """检查模型API状态"""
    result = {"name": "模型API", "status": "unknown", "detail": ""}
    cred_file = ENGINE_DIR / "data" / "model_credentials.json"
    if not cred_file.exists():
        result["status"] = "error"
        result["detail"] = "凭据文件不存在"
        return result
    with open(cred_file, "r") as f:
        cred = json.load(f)
    models = cred.get("models", {})
    active = [k for k, v in models.items() if v.get("status") == "active"]
    suspended = [k for k, v in models.items() if v.get("status") != "active"]
    result["status"] = "ok" if active else "error"
    result["detail"] = f"活跃: {len(active)}, 停用: {len(suspended)}"
    result["active_models"] = active
    return result


def check_disk():
    """检查磁盘空间"""
    result = {"name": "磁盘空间", "status": "unknown", "detail": ""}
    try:
        stat = os.statvfs(str(ENGINE_DIR))
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        usage = (1 - free / total) * 100
        result["total_gb"] = round(total / 1024**3, 1)
        result["free_gb"] = round(free / 1024**3, 1)
        result["usage_percent"] = round(usage, 1)
        result["status"] = "ok" if usage < 90 else "warning"
        result["detail"] = f"已用{usage:.1f}%, 剩余{free/1024**3:.1f}GB"
    except Exception as e:
        result["status"] = "error"
        result["detail"] = str(e)[:50]
    return result


def run_health_check():
    """执行完整健康自检"""
    print("=== 每日健康自检 ===")
    checks = [
        check_engine(),
        check_database(),
        check_feishu(),
        check_models(),
        check_disk(),
    ]

    # 生成报告
    report_lines = ["💚 凡心引擎每日健康自检报告", f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    all_ok = True
    for c in checks:
        icon = "✅" if c["status"] == "ok" else ("⚠️" if c["status"] == "warning" else "❌")
        report_lines.append(f"{icon} {c['name']}: {c['detail']}")
        if c["status"] != "ok":
            all_ok = False

    # 引擎详细信息
    engine = checks[0]
    if "zhuan" in engine:
        report_lines.append(f"\n📊 引擎修为: 第{engine['zhuan']}转, 累计完成{engine['total']}任务")

    report_lines.append(f"\n总体状态: {'✅ 全部正常' if all_ok else '⚠️ 存在异常项'}")
    report = "\n".join(report_lines)

    print(report)

    # 记录历史
    history = []
    if HEALTH_LOG.exists():
        with open(HEALTH_LOG, "r") as f:
            history = json.load(f)
    history.append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "all_ok": all_ok,
        "checks": checks,
    })
    history = history[-30:]
    with open(HEALTH_LOG, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    # 推送飞书
    if send_report(report):
        print("\n✅ 报告已推送飞书")
    else:
        print("\n⚠️ 飞书推送失败")

    return all_ok


def show_status():
    """显示最近一次自检结果"""
    if not HEALTH_LOG.exists():
        print("暂无自检记录")
        return
    with open(HEALTH_LOG, "r") as f:
        history = json.load(f)
    latest = history[-1]
    print(f"=== 最近自检 ({latest['timestamp']}) ===")
    print(f"总体: {'✅正常' if latest['all_ok'] else '⚠️异常'}")
    for c in latest["checks"]:
        icon = "✅" if c["status"] == "ok" else ("⚠️" if c["status"] == "warning" else "❌")
        print(f"  {icon} {c['name']}: {c['detail']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 daily_health_check.py [run|status|history]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "run":
        run_health_check()
    elif cmd == "status":
        show_status()
    elif cmd == "history":
        if HEALTH_LOG.exists():
            with open(HEALTH_LOG, "r") as f:
                history = json.load(f)
            print(f"共{len(history)}次自检记录")
            for h in history[-5:]:
                icon = "✅" if h["all_ok"] else "⚠️"
                print(f"  {icon} {h['timestamp']}")
    else:
        print("参数错误")
