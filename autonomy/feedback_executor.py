"""
九转引擎·认知反哺执行引擎
把"文字建议"转化为"实际配置修改"，打通认知→调参→行为的闭环
"""
import json
import time
from datetime import datetime
from pathlib import Path

EVOLUTION_LOG = Path(__file__).parent.parent / "data" / "evolution_log.json"

# 安全边界
SAFETY_LIMITS = {
    "concurrency": {"min": 1, "max": 5, "step": 1},
    "weight": {"min": 0.2, "max": 5.0, "step_ratio": 0.3},
    "fuse_cooldown": {"min": 60, "max": 600, "step": 60},
    "waste_threshold": {"min": 0.4, "max": 0.8, "step": 0.05},
}


def log_evolution(state, action, detail, before, after):
    """记录每次调参动作，形成可追溯的进化日志"""
    entry = {
        "time": datetime.now().isoformat(),
        "zhuan": state.get("zhuan_count", 0),
        "action": action,
        "detail": detail,
        "before": before,
        "after": after,
    }
    history = state.setdefault("evolution_log", [])
    history.append(entry)
    # 只保留最近100条
    if len(history) > 100:
        state["evolution_log"] = history[-100:]
    return entry


def adjust_concurrency(state, direction, reason=""):
    """调整并发数，direction: 'up'/'down'/int值"""
    current = state.get("concurrency_override", 3)
    limits = SAFETY_LIMITS["concurrency"]
    if direction == "up":
        new_val = min(limits["max"], current + limits["step"])
    elif direction == "down":
        new_val = max(limits["min"], current - limits["step"])
    else:
        new_val = max(limits["min"], min(limits["max"], int(direction)))
    if new_val != current:
        state["concurrency_override"] = new_val
        log_evolution(state, "concurrency", reason, current, new_val)
        return True, current, new_val
    return False, current, current


def adjust_task_weight(state, task_type, ratio, reason=""):
    """调整任务类型权重，ratio为倍数如0.8/1.2"""
    weights = state.setdefault("task_weights", {})
    current = weights.get(task_type, 1.0)
    limits = SAFETY_LIMITS["weight"]
    new_val = max(limits["min"], min(limits["max"], current * ratio))
    new_val = round(new_val, 2)
    if abs(new_val - current) > 0.01:
        weights[task_type] = new_val
        log_evolution(state, f"weight_{task_type}", reason, current, new_val)
        return True, current, new_val
    return False, current, current


def adjust_fuse_cooldown(state, direction, reason=""):
    """调整熔断冷却时间"""
    current = state.get("fuse_cooldown_override", 120)
    limits = SAFETY_LIMITS["fuse_cooldown"]
    if direction == "up":
        new_val = min(limits["max"], current + limits["step"])
    elif direction == "down":
        new_val = max(limits["min"], current - limits["step"])
    else:
        new_val = max(limits["min"], min(limits["max"], int(direction)))
    if new_val != current:
        state["fuse_cooldown_override"] = new_val
        log_evolution(state, "fuse_cooldown", reason, current, new_val)
        return True, current, new_val
    return False, current, current


def calculate_auto_adjustments(state):
    """基于近10个任务的表现，自动计算调参建议"""
    adjustments = []
    recent = state.get("recent_task_stats", [])
    if not recent:
        return adjustments

    # 1. 失败率→并发调整
    failures = sum(1 for t in recent if t.get("status") == "failed")
    failure_rate = failures / len(recent) if recent else 0
    if failure_rate > 0.15:
        adjustments.append(("concurrency", "down", f"失败率{failure_rate:.0%}>15%，降并发"))
    elif failure_rate < 0.03 and len(recent) >= 10:
        adjustments.append(("concurrency", "up", f"失败率{failure_rate:.0%}<3%，提并发"))

    # 2. 各类型增量分→权重调整
    type_scores = {}
    for t in recent:
        ttype = t.get("type", "exp")
        score = t.get("increment_score", 50)
        type_scores.setdefault(ttype, []).append(score)
    for ttype, scores in type_scores.items():
        avg = sum(scores) / len(scores)
        if avg >= 80 and len(scores) >= 3:
            adjustments.append((f"weight_{ttype}", 1.2, f"{ttype}平均增量分{avg:.0f}≥80，提权重"))
        elif avg <= 40 and len(scores) >= 3:
            adjustments.append((f"weight_{ttype}", 0.8, f"{ttype}平均增量分{avg:.0f}≤40，降权重"))

    # 3. 重复率→权重调整
    dup_rate = sum(1 for t in recent if t.get("is_duplicate")) / len(recent) if recent else 0
    if dup_rate > 0.3:
        # 找重复最多的类型降权
        type_dup = {}
        for t in recent:
            if t.get("is_duplicate"):
                ttype = t.get("type", "exp")
                type_dup[ttype] = type_dup.get(ttype, 0) + 1
        if type_dup:
            worst_type = max(type_dup, key=type_dup.get)
            adjustments.append((f"weight_{worst_type}", 0.7, f"{worst_type}重复率高，降权重"))

    return adjustments


def execute_feedback(state, feedback_list=None):
    """执行反哺调参，feedback_list为None时自动计算"""
    if feedback_list is None:
        feedback_list = calculate_auto_adjustments(state)

    results = []
    for item in feedback_list:
        if len(item) == 3:
            target, value, reason = item
        else:
            continue

        if target == "concurrency":
            ok, before, after = adjust_concurrency(state, value, reason)
        elif target == "fuse_cooldown":
            ok, before, after = adjust_fuse_cooldown(state, value, reason)
        elif target.startswith("weight_"):
            ttype = target.replace("weight_", "")
            ok, before, after = adjust_task_weight(state, ttype, value, reason)
        else:
            ok, before, after = False, None, None

        if ok:
            results.append({"target": target, "before": before, "after": after, "reason": reason})

    return results


def record_task_stat(state, task_type, status, increment_score=50, is_duplicate=False):
    """记录单任务统计，用于自动调参计算"""
    recent = state.setdefault("recent_task_stats", [])
    recent.append({
        "type": task_type,
        "status": status,
        "increment_score": increment_score,
        "is_duplicate": is_duplicate,
        "time": datetime.now().isoformat(),
    })
    # 只保留最近20条
    if len(recent) > 20:
        state["recent_task_stats"] = recent[-20:]
