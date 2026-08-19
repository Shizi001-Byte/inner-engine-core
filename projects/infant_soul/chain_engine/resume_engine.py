#!/usr/bin/env python3
"""
resume_engine.py — 断点续跑机制（模块2.2）

沙箱回收、会话中断后，下次启动自动从本地链路文件读取上一步结论，
接续推理，不重头再来。
解决：长链路思考被中断后全部丢失的问题。

用法：
  python3 resume_engine.py check              # 检查是否有未完成的链路
  python3 resume_engine.py resume <chain_id>  # 恢复指定链路
  python3 resume_engine.py resume-all         # 恢复所有未完成链路
  python3 resume_engine.py snapshot <chain_id> # 手动保存快照
"""

import json
import time
import sys
from pathlib import Path

CHAIN_DIR = Path(__file__).parent.parent / "data" / "chains"
SNAPSHOT_DIR = Path(__file__).parent.parent / "data" / "snapshots"
RESUME_LOG = Path(__file__).parent.parent / "data" / "resume_log.json"

SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path):
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def check_interrupted():
    """检查所有未完成的链路"""
    if not CHAIN_DIR.exists():
        return []
    interrupted = []
    for chain_file in CHAIN_DIR.glob("*.json"):
        chain = load_json(chain_file)
        if chain.get("status") in ["created", "running", "interrupted"]:
            interrupted.append(chain)
    return interrupted


def make_snapshot(chain_id):
    """手动保存链路快照（用于断点保护）"""
    chain_file = CHAIN_DIR / f"{chain_id}.json"
    if not chain_file.exists():
        print(f"[ERROR] 链路不存在: {chain_id}")
        return False
    chain = load_json(chain_file)
    snapshot_path = SNAPSHOT_DIR / f"{chain_id}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    save_json(snapshot_path, chain)
    print(f"[OK] 快照已保存: {snapshot_path.name}")
    return True


def resume_chain(chain_id):
    """恢复指定链路，从断点继续执行"""
    chain_file = CHAIN_DIR / f"{chain_id}.json"
    if not chain_file.exists():
        # 尝试从快照恢复
        snapshots = sorted(SNAPSHOT_DIR.glob(f"{chain_id}_*.json"), reverse=True)
        if snapshots:
            print(f"[INFO] 从快照恢复: {snapshots[0].name}")
            chain = load_json(snapshots[0])
            save_json(chain_file, chain)
        else:
            print(f"[ERROR] 链路和快照都不存在: {chain_id}")
            return False
    else:
        chain = load_json(chain_file)

    print(f"=== 恢复链路 {chain_id} ===")
    print(f"问题: {chain['question'][:60]}")
    print(f"原状态: {chain['status']} | 已完成步骤: {chain['current_step']}")

    # 标记为恢复中
    chain["status"] = "running"
    chain["resumed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    chain["resume_count"] = chain.get("resume_count", 0) + 1
    save_json(chain_file, chain)

    # 记录恢复日志
    log = load_json(RESUME_LOG)
    log.setdefault("resumes", []).append({
        "chain_id": chain_id,
        "resumed_at": chain["resumed_at"],
        "resume_count": chain["resume_count"],
        "step_at_resume": chain["current_step"],
    })
    save_json(RESUME_LOG, log)

    print(f"[OK] 链路已恢复，当前在步骤 {chain['current_step']}")
    print(f"     累计恢复次数: {chain['resume_count']}")
    print(f"     下一步: 运行 chain_fragment.py continue {chain_id}")
    return True


def resume_all():
    """恢复所有未完成链路"""
    interrupted = check_interrupted()
    if not interrupted:
        print("[INFO] 没有未完成的链路")
        return
    print(f"[INFO] 发现 {len(interrupted)} 条未完成链路")
    for chain in interrupted:
        print(f"\n--- 恢复 {chain['chain_id']} ---")
        resume_chain(chain["chain_id"])


def show_status():
    """显示断点续跑状态"""
    interrupted = check_interrupted()
    snapshots = list(SNAPSHOT_DIR.glob("*.json")) if SNAPSHOT_DIR.exists() else []
    log = load_json(RESUME_LOG)

    print("=== 断点续跑状态 ===")
    print(f"未完成链路: {len(interrupted)} 条")
    print(f"历史快照: {len(snapshots)} 个")
    print(f"累计恢复次数: {sum(1 for _ in log.get('resumes', []))} 次")

    if interrupted:
        print("\n未完成链路:")
        for c in interrupted:
            print(f"  [{c['status']}] {c['chain_id']} | 步骤{c['current_step']} | {c['question'][:40]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 resume_engine.py [check|resume|resume-all|snapshot|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "check":
        chains = check_interrupted()
        print(f"未完成链路: {len(chains)} 条")
        for c in chains:
            print(f"  {c['chain_id']}: {c['status']} (步骤{c['current_step']})")
    elif cmd == "resume" and len(sys.argv) > 2:
        resume_chain(sys.argv[2])
    elif cmd == "resume-all":
        resume_all()
    elif cmd == "snapshot" and len(sys.argv) > 2:
        make_snapshot(sys.argv[2])
    elif cmd == "status":
        show_status()
    else:
        print("参数错误")
