#!/usr/bin/env python3
"""
full_health_check.py — 全链路健康巡检（模块2.3）
检测：数据库连通性、模型API可用性、飞书推送状态、备份完整性、磁盘空间、引擎进程。
用法：
  python3 full_health_check.py          # 执行巡检并输出报告
  python3 full_health_check.py --push   # 巡检后推送飞书报告
"""
import json
import time
import shutil
import os
import argparse
from pathlib import Path
from datetime import datetime

import requests

ENGINE_DIR = Path(__file__).parent.parent.parent
SUPABASE_URL = "https://gltscytpqnuuzhczljyq.supabase.co"
SUPABASE_KEY = "sb_secret_Cpcpl-d8aA82ALo16hU8lg_3Smd8Xuu"
CRED_FILE = ENGINE_DIR / "data" / "model_credentials.json"
LARK_CFG = ENGINE_DIR / "projects" / "infant_soul" / "data" / "lark_push_config.json"
PID_FILE = ENGINE_DIR / "data" / "engine.pid"
REPORT_FILE = Path(__file__).parent / "data" / "health_report.json"


def get_session():
    s = requests.Session()
    s.trust_env = False
    return s


def check_supabase():
    """检查Supabase连通性"""
    try:
        s = get_session()
        r = s.get(f"{SUPABASE_URL}/rest/v1/cognition?select=id&limit=1",
                  headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=10)
        return {"name": "Supabase数据库", "ok": r.status_code == 200, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"name": "Supabase数据库", "ok": False, "detail": str(e)[:100]}


def check_models():
    """检查模型API可用性"""
    results = []
    if not CRED_FILE.exists():
        return [{"name": "模型API", "ok": False, "detail": "凭证文件不存在"}]
    creds = json.load(open(CRED_FILE))
    for name, m in creds.get("models", {}).items():
        if m.get("status") != "active":
            results.append({"name": f"模型-{name}", "ok": False, "detail": f"状态:{m.get('status')}"})
            continue
        try:
            s = get_session()
            r = s.post(m["api_base"], headers={
                "Authorization": f"Bearer {m['api_key']}",
                "Content-Type": "application/json"
            }, json={"model": m["model_id"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}, timeout=15)
            results.append({"name": f"模型-{name}", "ok": r.status_code == 200, "detail": f"HTTP {r.status_code}"})
        except Exception as e:
            results.append({"name": f"模型-{name}", "ok": False, "detail": str(e)[:80]})
    return results


def check_lark():
    """检查飞书推送"""
    try:
        if not LARK_CFG.exists():
            return {"name": "飞书推送", "ok": False, "detail": "配置文件不存在"}
        cfg = json.load(open(LARK_CFG))
        webhook = cfg.get("webhook_url", "")
        if not webhook:
            return {"name": "飞书推送", "ok": False, "detail": "webhook未配置"}
        import urllib.request
        payload = json.dumps({"msg_type": "text", "content": {"text": "健康检查测试消息"}}).encode()
        req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"name": "飞书推送", "ok": resp.status == 200, "detail": f"HTTP {resp.status}"}
    except Exception as e:
        return {"name": "飞书推送", "ok": False, "detail": str(e)[:80]}


def check_disk():
    """检查磁盘空间"""
    try:
        total, used, free = shutil.disk_usage(str(ENGINE_DIR))
        free_mb = free // 1024 // 1024
        ok = free_mb > 500  # 剩余500MB以上为正常
        return {"name": "磁盘空间", "ok": ok, "detail": f"剩余{free_mb}MB"}
    except Exception as e:
        return {"name": "磁盘空间", "ok": False, "detail": str(e)[:80]}


def check_engine():
    """检查引擎进程"""
    if not PID_FILE.exists():
        return {"name": "引擎进程", "ok": False, "detail": "PID文件不存在（引擎未运行）"}
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return {"name": "引擎进程", "ok": True, "detail": f"PID={pid} 运行中"}
    except (ValueError, ProcessLookupError, OSError):
        return {"name": "引擎进程", "ok": False, "detail": "PID文件存在但进程已退出"}


def check_backup():
    """检查备份完整性"""
    try:
        backup_dir = ENGINE_DIR / "archive"
        if not backup_dir.exists():
            return {"name": "本地备份", "ok": False, "detail": "备份目录不存在"}
        tar_files = list(backup_dir.rglob("*.tar.gz"))
        ok = len(tar_files) > 0
        return {"name": "本地备份", "ok": ok, "detail": f"{len(tar_files)}个备份包"}
    except Exception as e:
        return {"name": "本地备份", "ok": False, "detail": str(e)[:80]}


def run_checks():
    """执行全部检查"""
    print(f"=== 全链路健康巡检 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    checks = []
    checks.append(check_supabase())
    checks.extend(check_models())
    checks.append(check_lark())
    checks.append(check_disk())
    checks.append(check_engine())
    checks.append(check_backup())

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)
    report = {
        "time": datetime.now().isoformat(),
        "passed": passed,
        "total": total,
        "checks": checks,
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    for c in checks:
        icon = "✅" if c["ok"] else "❌"
        print(f"  {icon} {c['name']}: {c['detail']}")
    print(f"\n结果: {passed}/{total} 项通过")
    return report


def push_report(report):
    """推送报告到飞书"""
    import urllib.request
    if not LARK_CFG.exists():
        print("飞书未配置，跳过推送")
        return
    cfg = json.load(open(LARK_CFG))
    webhook = cfg.get("webhook_url", "")
    lines = [f"【健康巡检报告】{datetime.now().strftime('%m-%d %H:%M')}"]
    lines.append(f"通过率: {report['passed']}/{report['total']}")
    for c in report["checks"]:
        icon = "✅" if c["ok"] else "❌"
        lines.append(f"{icon} {c['name']}: {c['detail']}")
    text = "\n".join(lines)
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print("报告已推送飞书")
    except Exception as e:
        print(f"推送失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="全链路健康巡检")
    parser.add_argument("--push", action="store_true", help="推送报告到飞书")
    args = parser.parse_args()
    report = run_checks()
    if args.push:
        push_report(report)


if __name__ == "__main__":
    main()
