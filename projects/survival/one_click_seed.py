#!/usr/bin/env python3
"""
one_click_seed.py — 极简种子一键部署（模块4.1）
单文件完成：环境检查→依赖安装→从Gitee拉取代码→恢复数据→启动引擎，全程无人值守。
用法：
  python3 one_click_seed.py deploy       # 一键部署
  python3 one_click_seed.py check        # 环境检查
  python3 one_click_seed.py restore      # 仅恢复数据
"""
import json
import os
import sys
import subprocess
import argparse
from pathlib import Path

# 配置
GITEE_REPO = "https://gitee.com/shizi-mem001/inner-engine-core.git"
ENGINE_DIR = Path(__file__).parent.parent.parent
REQUIREMENTS = ["requests", "numpy"]


def run_cmd(cmd, cwd=None, timeout=120):
    """执行命令并返回结果"""
    print(f"  $ {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if r.stdout:
            print(f"    {r.stdout.strip()[:200]}")
        if r.returncode != 0 and r.stderr:
            print(f"    [ERR] {r.stderr.strip()[:200]}")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"    [TIMEOUT] {timeout}s")
        return False


def check_env():
    """环境检查"""
    print("=== 环境检查 ===")
    issues = []
    # Python版本
    py_ver = sys.version_info
    print(f"  Python: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 8):
        issues.append("Python版本过低，需要3.8+")
    # 依赖
    for pkg in REQUIREMENTS:
        try:
            __import__(pkg)
            print(f"  {pkg}: ✅")
        except ImportError:
            print(f"  {pkg}: ❌ 未安装")
            issues.append(f"缺少依赖: {pkg}")
    # Git
    git_ok = run_cmd("git --version")
    if not git_ok:
        issues.append("git未安装")
    # 磁盘空间
    try:
        import shutil
        free = shutil.disk_usage(str(ENGINE_DIR)).free // 1024 // 1024
        print(f"  磁盘剩余: {free}MB")
        if free < 500:
            issues.append("磁盘空间不足500MB")
    except:
        pass
    if issues:
        print(f"\n发现 {len(issues)} 个问题:")
        for i in issues:
            print(f"  - {i}")
        return False
    print("\n环境检查通过 ✅")
    return True


def install_deps():
    """安装依赖"""
    print("\n=== 安装依赖 ===")
    for pkg in REQUIREMENTS:
        try:
            __import__(pkg)
        except ImportError:
            print(f"  安装 {pkg}...")
            run_cmd(f"pip3 install {pkg} -q")


def pull_code():
    """从Gitee拉取代码"""
    print("\n=== 拉取代码 ===")
    if (ENGINE_DIR / ".git").exists():
        print("  已有git仓库，执行pull")
        return run_cmd("git pull", cwd=str(ENGINE_DIR))
    else:
        print(f"  克隆仓库: {GITEE_REPO}")
        parent = ENGINE_DIR.parent
        return run_cmd(f"git clone {GITEE_REPO} {ENGINE_DIR.name}", cwd=str(parent))


def restore_data():
    """恢复数据（从Supabase或本地备份）"""
    print("\n=== 恢复数据 ===")
    data_dir = ENGINE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # 检查是否有备份
    backup_dir = ENGINE_DIR / "archive"
    if backup_dir.exists():
        tar_files = sorted(backup_dir.glob("*.tar.gz"))
        if tar_files:
            latest = tar_files[-1]
            print(f"  找到备份: {latest.name}")
            print(f"  解压到 {data_dir}")
            run_cmd(f"tar -xzf {latest} -C {data_dir}")
            return True
    print("  未找到本地备份，数据将从引擎运行时自动同步")
    return True


def start_engine():
    """启动引擎"""
    print("\n=== 启动引擎 ===")
    engine_script = ENGINE_DIR / "autonomy" / "engine_zhuan1.py"
    if not engine_script.exists():
        print(f"  引擎脚本不存在: {engine_script}")
        return False
    print(f"  启动: {engine_script}")
    subprocess.Popen(
        [sys.executable, str(engine_script)],
        cwd=str(ENGINE_DIR),
        stdout=open(ENGINE_DIR / "data" / "engine_stdout.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print("  引擎已后台启动")
    return True


def deploy():
    """一键部署全流程"""
    print("=" * 50)
    print("  凡心引擎 · 一键部署")
    print("=" * 50)
    steps = [
        ("环境检查", check_env),
        ("安装依赖", install_deps),
        ("拉取代码", pull_code),
        ("恢复数据", restore_data),
        ("启动引擎", start_engine),
    ]
    results = {}
    for name, func in steps:
        print(f"\n{'='*10} {name} {'='*10}")
        try:
            results[name] = func()
        except Exception as e:
            print(f"  [异常] {e}")
            results[name] = False
    print("\n" + "=" * 50)
    print("  部署结果汇总")
    print("=" * 50)
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    all_ok = all(results.values())
    print(f"\n{'部署完成！' if all_ok else '部署存在问题，请检查上方日志'}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="极简种子一键部署")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("deploy")
    sub.add_parser("check")
    sub.add_parser("restore")
    args = parser.parse_args()
    if args.cmd == "deploy":
        deploy()
    elif args.cmd == "check":
        check_env()
    elif args.cmd == "restore":
        restore_data()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
