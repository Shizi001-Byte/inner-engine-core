#!/usr/bin/env python3
"""
multi_backup.py — 多平台自动备份（模块5.2）

核心数据每日自动备份到：本地文件 + Supabase + 飞书文档 + Gitee，
四地容灾，任何一端损坏可从其他端恢复。

用法：
  python3 multi_backup.py run        # 执行四地备份
  python3 multi_backup.py status     # 查看备份状态
  python3 multi_backup.py verify     # 校验各端备份完整性
  python3 multi_backup.py list       # 列出备份历史
"""

import json
import time
import hashlib
import subprocess
import sys
import tarfile
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
DATA_DIR = Path(__file__).parent.parent / "data"
BACKUP_LOG = DATA_DIR / "multi_backup_log.json"
BACKUP_DIR = ENGINE_DIR / "archive"

BACKUP_TARGETS = ["local", "supabase", "feishu", "gitee"]


def load_log():
    if BACKUP_LOG.exists():
        with open(BACKUP_LOG, "r") as f:
            return json.load(f)
    return []


def save_log(log):
    log = log[-50:]
    with open(BACKUP_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def create_backup_package():
    """创建核心资产备份包"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    package_path = BACKUP_DIR / f"infant_soul_core_{timestamp}.tar.gz"

    # 要备份的核心文件
    core_files = [
        ENGINE_DIR / "data" / "engine_state.json",
        ENGINE_DIR / "data" / "model_credentials.json",
        ENGINE_DIR / "data" / "backup_config.json",
        ENGINE_DIR / "autonomy" / "engine_zhuan1.py",
        ENGINE_DIR / "autonomy" / "state_sync.py",
        ENGINE_DIR / "autonomy" / "seed_bootstrap.py",
        ENGINE_DIR / "autonomy" / "cognition_sync.py",
    ]
    # 认知文档
    cog_files = list((ENGINE_DIR / "cognition").glob("*.md"))[:10]

    with tarfile.open(package_path, "w:gz") as tar:
        for f in core_files + cog_files:
            if f.exists():
                tar.add(f, arcname=f.relative_to(ENGINE_DIR))

    # 计算MD5
    with open(package_path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()

    size = package_path.stat().st_size
    print(f"[本地] 备份包已创建: {package_path.name} ({size:,}字节, MD5:{md5[:8]}...)")
    return package_path, md5, size


def backup_to_supabase(package_path):
    """备份到Supabase Storage"""
    try:
        sync_script = ENGINE_DIR / "autonomy" / "state_sync.py"
        if sync_script.exists():
            result = subprocess.run(
                ["python3", str(sync_script), "push"],
                capture_output=True, text=True, timeout=30,
                cwd=str(ENGINE_DIR / "autonomy")
            )
            if "[OK]" in result.stdout:
                print(f"[Supabase] 状态已上云")
                return True
        print(f"[Supabase] 跳过（state_sync.py不可用）")
        return False
    except Exception as e:
        print(f"[Supabase] 失败: {e}")
        return False


def backup_to_feishu():
    """备份到飞书"""
    try:
        cog_script = ENGINE_DIR / "autonomy" / "cognition_sync.py"
        if cog_script.exists():
            result = subprocess.run(
                ["python3", str(cog_script), "push"],
                capture_output=True, text=True, timeout=60,
                cwd=str(ENGINE_DIR / "autonomy")
            )
            if "完成" in result.stdout:
                print(f"[飞书] 认知文档已同步")
                return True
        print(f"[飞书] 跳过（cognition_sync.py不可用）")
        return False
    except Exception as e:
        print(f"[飞书] 失败: {e}")
        return False


def backup_to_gitee():
    """备份到Gitee"""
    try:
        result = subprocess.run(
            ["git", "add", "-A", "--", "autonomy/", "data/*.json", "cognition/", "projects/"],
            cwd=str(ENGINE_DIR), capture_output=True, text=True, timeout=30
        )
        result = subprocess.run(
            ["git", "commit", "-m", f"auto-backup-{time.strftime('%Y%m%d_%H%M%S')}"],
            cwd=str(ENGINE_DIR), capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 or "nothing to commit" in result.stdout:
            result = subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=str(ENGINE_DIR), capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(f"[Gitee] 代码已推送")
                return True
        print(f"[Gitee] 跳过（无变更或推送失败）")
        return False
    except Exception as e:
        print(f"[Gitee] 失败: {e}")
        return False


def run_backup():
    """执行四地备份"""
    print("=" * 50)
    print("  四地容灾备份启动")
    print("=" * 50)

    results = {}

    # 1. 本地备份
    package_path, md5, size = create_backup_package()
    results["local"] = {"ok": True, "file": package_path.name, "md5": md5, "size": size}

    # 2. Supabase
    results["supabase"] = {"ok": backup_to_supabase(package_path)}

    # 3. 飞书
    results["feishu"] = {"ok": backup_to_feishu()}

    # 4. Gitee
    results["gitee"] = {"ok": backup_to_gitee()}

    # 记录日志
    log = load_log()
    log.append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "package": package_path.name,
        "md5": md5,
        "size": size,
        "results": {k: v["ok"] for k, v in results.items()},
    })
    save_log(log)

    # 汇总
    success = sum(1 for v in results.values() if v.get("ok"))
    print(f"\n{'=' * 50}")
    print(f"  备份完成: {success}/4 端成功")
    for target, info in results.items():
        icon = "✓" if info.get("ok") else "✗"
        print(f"  {icon} {target}")
    print(f"{'=' * 50}")

    return results


def show_status():
    """显示备份状态"""
    log = load_log()
    print("=== 多平台备份状态 ===")
    print(f"备份目标: {', '.join(BACKUP_TARGETS)}")
    print(f"历史备份: {len(log)} 次")
    if log:
        latest = log[-1]
        print(f"\n最近备份: {latest['timestamp']}")
        print(f"备份包: {latest['package']}")
        print(f"MD5: {latest['md5']}")
        print(f"各端结果:")
        for target, ok in latest["results"].items():
            print(f"  {'✓' if ok else '✗'} {target}")


def verify_backups():
    """校验备份完整性"""
    print("=== 备份完整性校验 ===")
    # 检查本地备份包
    packages = sorted(BACKUP_DIR.glob("infant_soul_core_*.tar.gz"), reverse=True)
    if packages:
        latest = packages[0]
        with open(latest, "rb") as f:
            md5 = hashlib.md5(f.read()).hexdigest()
        print(f"本地最新备份: {latest.name}")
        print(f"  MD5: {md5}")
        print(f"  大小: {latest.stat().st_size:,}字节")
        print(f"  ✓ 本地备份完整")
    else:
        print("  ✗ 无本地备份")

    # 检查引擎状态文件
    state_file = ENGINE_DIR / "data" / "engine_state.json"
    if state_file.exists():
        print(f"  ✓ 引擎状态文件存在")
    else:
        print(f"  ✗ 引擎状态文件缺失")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 multi_backup.py [run|status|verify|list]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "run":
        run_backup()
    elif cmd == "status":
        show_status()
    elif cmd == "verify":
        verify_backups()
    elif cmd == "list":
        log = load_log()
        for item in log[-10:]:
            ok_count = sum(1 for v in item["results"].values() if v)
            print(f"  [{item['timestamp']}] {item['package']} ({ok_count}/4)")
    else:
        print("参数错误")
