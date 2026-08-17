#!/usr/bin/env python3
"""
V7.2 双向同步管理器
- 本体→引擎：同步规则更新、配置变更、新任务
- 引擎→本体：同步回执摘要、状态报告、关键产出
- 冲突检测：基于MD5和时间戳
- 同步日志与审计
"""
import os, json, hashlib, shutil, time
from datetime import datetime
from pathlib import Path

# ============ 路径配置 ============
WORKSPACE = Path("/home/user/.super_doubao/super-doubao-runtime/workspace")
ENGINE_DIR = WORKSPACE / "engine_v7_2"
SYNC_LOG_DIR = ENGINE_DIR / "logs"
SYNC_STATE_FILE = ENGINE_DIR / "data" / "sync_state.json"

for d in [SYNC_LOG_DIR, ENGINE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

# 同步规则定义
SYNC_RULES = {
    # 本体→引擎：规则文件变更时同步
    "body_to_engine": [
        {
            "name": "core_anchor",
            "source": WORKSPACE / "engine_v7_2" / "body" / "core_anchor.md",
            "dest": ENGINE_DIR / "body" / "core_anchor.md",
            "description": "本体核心锚点文件",
        },
        {
            "name": "body_call_rules",
            "source": WORKSPACE / "engine_v7_2" / "body" / "body_call_rules.md",
            "dest": ENGINE_DIR / "body" / "body_call_rules.md",
            "description": "本体调用引擎规则",
        },
    ],
    # 引擎→本体：回执和状态摘要
    "engine_to_body": [
        {
            "name": "latest_receipts",
            "source": ENGINE_DIR / "dispatch" / "receipts",
            "dest": WORKSPACE / "engine_v7_2" / "dispatch" / "receipts",
            "description": "任务回执",
            "mode": "sync_dir",
        },
        {
            "name": "task_status",
            "source": ENGINE_DIR / "dispatch" / "status",
            "dest": WORKSPACE / "engine_v7_2" / "dispatch" / "status",
            "description": "任务状态",
            "mode": "sync_dir",
        },
    ],
}

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(SYNC_LOG_DIR / f"sync_{datetime.now().strftime('%Y-%m-%d')}.log", "a") as f:
        f.write(line + "\n")

def load_sync_state():
    if SYNC_STATE_FILE.exists():
        with open(SYNC_STATE_FILE) as f:
            return json.load(f)
    return {"last_sync": None, "file_hashes": {}, "sync_count": 0, "conflicts": []}

def save_sync_state(state):
    with open(SYNC_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def calculate_md5(filepath):
    if not filepath.exists():
        return None
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def sync_file(source, dest, state, direction):
    """同步单个文件，检测冲突"""
    if not source.exists():
        log(f"  源文件不存在: {source}", "WARN")
        return False, "source_missing"
    # 单节点环境：source和dest可能是同一个文件，跳过
    try:
        if source.resolve() == dest.resolve():
            return False, "same_file"
    except Exception:
        pass

    source_md5 = calculate_md5(source)
    source_key = str(source)

    # 检查是否有变更
    last_hash = state["file_hashes"].get(source_key)
    if last_hash == source_md5 and dest.exists():
        return False, "no_change"

    # 冲突检测：目标文件被修改过
    if dest.exists():
        dest_md5 = calculate_md5(dest)
        if last_hash and dest_md5 != last_hash and dest_md5 != source_md5:
            conflict = {
                "file": str(source),
                "direction": direction,
                "source_md5": source_md5,
                "dest_md5": dest_md5,
                "last_synced_hash": last_hash,
                "time": datetime.now().isoformat(),
            }
            state["conflicts"].append(conflict)
            log(f"  [CONFLICT] 检测到冲突: {source.name}", "WARN")
            # 冲突策略：引擎侧为准，备份本体侧
            backup = dest.with_suffix(dest.suffix + ".conflict_backup")
            shutil.copy2(dest, backup)
            log(f"  已备份冲突文件至: {backup}")

    # 执行同步
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    state["file_hashes"][source_key] = source_md5
    log(f"  同步: {source.name} → {dest.parent.name}/")
    return True, "synced"

def sync_directory(source_dir, dest_dir, state, direction):
    """同步目录下所有文件"""
    if not source_dir.exists():
        return 0

    synced = 0
    for src_file in source_dir.glob("*"):
        if src_file.is_file():
            dest_file = dest_dir / src_file.name
            ok, status = sync_file(src_file, dest_file, state, direction)
            if ok:
                synced += 1
    return synced

def run_body_to_engine(state):
    """本体→引擎同步"""
    log("[B→E] 本体→引擎同步开始")
    total = 0
    for rule in SYNC_RULES["body_to_engine"]:
        ok, status = sync_file(rule["source"], rule["dest"], state, "body_to_engine")
        if ok:
            total += 1
    log(f"[B→E] 同步完成，变更文件: {total}")
    return total

def run_engine_to_body(state):
    """引擎→本体同步"""
    log("[E→B] 引擎→本体同步开始")
    total = 0
    for rule in SYNC_RULES["engine_to_body"]:
        if rule.get("mode") == "sync_dir":
            count = sync_directory(rule["source"], rule["dest"], state, "engine_to_body")
            total += count
        else:
            ok, status = sync_file(rule["source"], rule["dest"], state, "engine_to_body")
            if ok:
                total += 1
    log(f"[E→B] 同步完成，变更文件: {total}")
    return total

def generate_sync_summary(state, b2e_count, e2b_count):
    """生成同步摘要供本体快速读取"""
    summary = {
        "last_sync": datetime.now().isoformat(),
        "sync_count": state["sync_count"],
        "body_to_engine_changes": b2e_count,
        "engine_to_body_changes": e2b_count,
        "pending_conflicts": len(state["conflicts"]),
        "latest_receipts": [],
    }

    # 读取最近5条回执
    receipt_dir = ENGINE_DIR / "dispatch" / "receipts"
    if receipt_dir.exists():
        receipts = sorted(receipt_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]
        for r in receipts:
            try:
                with open(r) as f:
                    data = json.load(f)
                summary["latest_receipts"].append({
                    "task_id": data.get("task_id"),
                    "status": data.get("status"),
                    "summary": data.get("summary", "")[:80],
                    "time": data.get("timestamp"),
                })
            except:
                pass

    summary_path = ENGINE_DIR / "data" / "latest_sync_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary

def main():
    log("=" * 50)
    log("[START] V7.2 双向同步开始")
    log("=" * 50)

    state = load_sync_state()

    # 双向同步
    b2e = run_body_to_engine(state)
    e2b = run_engine_to_body(state)

    # 更新状态
    state["last_sync"] = datetime.now().isoformat()
    state["sync_count"] = state.get("sync_count", 0) + 1
    save_sync_state(state)

    # 生成摘要
    summary = generate_sync_summary(state, b2e, e2b)

    log("=" * 50)
    log("[DONE] 双向同步完成")
    log(f"  本体→引擎: {b2e} 个变更")
    log(f"  引擎→本体: {e2b} 个变更")
    log(f"  累计同步次数: {state['sync_count']}")
    log(f"  待处理冲突: {len(state['conflicts'])}")
    log(f"  最近回执: {len(summary['latest_receipts'])} 条")
    log("=" * 50)

if __name__ == "__main__":
    main()
