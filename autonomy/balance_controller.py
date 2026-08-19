"""
阴阳自衡控制器
反者道之动：每一项正向规则都配一项反向制衡，防止单向极端化
"""
import json
from datetime import datetime
from pathlib import Path

BALANCE_LOG = Path(__file__).parent.parent / "data" / "balance_log.json"


def check_density_balance(state):
    """
    密度制衡：某类认知连续高密时，强制稀释
    反者道之动：高密到极端会走向反面（全是工整套话，创造力下降）
    """
    actions = []
    density_stats = state.get("density_stats", {})
    if not density_stats:
        return actions

    for ctype, stats in density_stats.items():
        s_count = stats.get("S", 0)
        total = stats.get("total", 0)
        if total >= 5 and s_count / total >= 0.7:
            # 连续高密，触发稀释
            weights = state.get("task_weights", {})
            current = weights.get(ctype, 1.0)
            if current > 0.5:
                weights[ctype] = round(current * 0.7, 2)
                state["task_weights"] = weights
                actions.append(f"密度制衡：{ctype}连续高密({s_count}/{total})，权重{current}→{weights[ctype]}")
                # 强制混入探索类
                exp_weight = weights.get("exp", 1.0)
                weights["exp"] = round(exp_weight * 1.3, 2)
                actions.append(f"密度制衡：提升exp探索类权重{exp_weight}→{weights['exp']}")
    return actions


def check_weight_balance(state):
    """
    权重制衡：某类任务权重超过50%时回拉
    反者道之动：权重倾斜到极端会能力单极化
    """
    actions = []
    weights = state.get("task_weights", {})
    if not weights:
        return actions

    total_w = sum(weights.values())
    if total_w == 0:
        return actions

    for ctype, w in weights.items():
        ratio = w / total_w
        if ratio >= 0.5:
            # 超过50%，回拉到45%
            target = total_w * 0.45
            weights[ctype] = round(target, 2)
            actions.append(f"权重制衡：{ctype}占比{ratio:.0%}超50%，回拉至{weights[ctype]}")
            # 给短板类型分配最低10%
            for other in weights:
                if other != ctype and weights[other] / total_w < 0.1:
                    weights[other] = round(total_w * 0.1, 2)
                    actions.append(f"权重制衡：短板{other}保底至{weights[other]}")
            state["task_weights"] = weights
            break
    return actions


def check_complexity_balance(state):
    """
    复杂度制衡：每新增模块必须清理冗余
    反者道之动：功能越加越多，复杂度反噬稳定性
    """
    # 这个在人工加模块时触发，记录到日志
    return ["复杂度制衡：新增模块前请同步清理冗余代码/死代码/过时逻辑"]


def run_balance_check(state):
    """运行全部制衡检查"""
    all_actions = []
    all_actions.extend(check_density_balance(state))
    all_actions.extend(check_weight_balance(state))

    if all_actions:
        log_entry = {
            "time": datetime.now().isoformat(),
            "zhuan": state.get("zhuan_count", 0),
            "actions": all_actions,
        }
        history = state.get("balance_log", [])
        history.append(log_entry)
        if len(history) > 50:
            state["balance_log"] = history[-50:]
        else:
            state["balance_log"] = history

    return all_actions


def update_density_stats(state, task_type, grade):
    """更新密度统计，用于制衡判断"""
    stats = state.setdefault("density_stats", {})
    type_stats = stats.setdefault(task_type, {"S": 0, "A": 0, "B": 0, "C": 0, "total": 0})
    type_stats[grade] = type_stats.get(grade, 0) + 1
    type_stats["total"] += 1
    # 只保留最近20条统计
    if type_stats["total"] > 20:
        # P2-5修复：只减大于0的等级，total减实际减少量，保持sum==total
        actual_dec = 0
        for k in ["S", "A", "B", "C"]:
            if type_stats[k] > 0:
                type_stats[k] -= 1
                actual_dec += 1
        type_stats["total"] -= actual_dec
