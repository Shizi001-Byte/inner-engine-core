#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预判层 Prediction Layer V2.0 — 加权评分自循环体系
核心改造：
1. 关键词分级加权（强/中/弱），解决"命中即报警"的误报爆炸
2. 分任务类型超时阈值，解决deep/l4天生高耗时被误判
3. 三维度独立评分（失败/超时/重复），互不干扰
4. 全量预判落库，为批量校验留凭证
5. verify_prediction自动回填，攒批后批量校验迭代
"""
import json
import time
import re
from datetime import datetime
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PREDICTION_LOG = DATA_DIR / "prediction_log.jsonl"
PREDICTION_STATE = DATA_DIR / "prediction_state.json"
RULES_CONFIG = DATA_DIR / "prediction_rules.json"

# ============================================================
# 规则配置（可被批量校验脚本自动迭代）
# ============================================================
DEFAULT_RULES = {
    "version": "2.0",
    "updated_at": None,
    "iteration_count": 0,
    # 强风险词：明确指向失败的词，权重+3
    "strong_risk_words": [
        "权限拒绝", "路径不存在", "密钥失效", "连接超时", "403", "404",
        "500", "熔断", "死锁", "内存溢出", "segfault", "崩溃",
        "凭证错误", "认证失败", "磁盘满", "端口占用", "依赖缺失",
    ],
    # 中风险词：可能出问题但不确定，权重+2
    "medium_risk_words": [
        "配置变更", "并发拉满", "首次执行", "迁移", "重构", "升级",
        "切换", "替换", "删除", "清空", "重置", "批量",
        "跨平台", "兼容性", "编码问题", "格式转换",
    ],
    # 弱风险词：工程常见词，单独出现不代表风险，权重+1
    "weak_risk_words": [
        "配置", "token", "参数", "脚本", "API", "同步", "数据库",
        "超时", "代理", "编码", "格式", "路径", "权限",
        "并发", "线程", "锁", "缓存", "刷新", "日志",
    ],
    # 失败风险评分阈值
    "failure_score_thresholds": {
        "low": 0,      # 0-2分 → low
        "medium": 3,   # 3-5分 → medium
        "high": 6,     # 6分以上 → high
    },
    # 分任务类型超时阈值（秒）
    "timeout_thresholds_by_type": {
        "deep": 180,
        "l4": 150,
        "cog": 120,
        "eng": 120,
        "exp": 90,
        "archive": 60,
        "asset": 60,
        "default": 120,
    },
    # 超时风险阈值（实际耗时/阈值比例）
    "timeout_ratio_thresholds": {
        "low": 0.5,     # 预计耗时 < 50%阈值 → low
        "medium": 0.8,  # 50%-80% → medium
        "high": 1.0,    # >80% → high
    },
    # 重复风险：同类任务连续执行次数阈值
    "duplicate_count_thresholds": {
        "low": 2,
        "medium": 4,
        "high": 6,
    },
}

# 运行时规则（从文件加载，支持迭代）
_rules = None


def load_rules():
    """加载规则配置，不存在则用默认值初始化"""
    global _rules
    if _rules is not None:
        return _rules
    if RULES_CONFIG.exists():
        try:
            with open(RULES_CONFIG) as f:
                _rules = json.load(f)
            return _rules
        except Exception:
            pass
    _rules = dict(DEFAULT_RULES)
    _rules["updated_at"] = datetime.now().isoformat()
    save_rules()
    return _rules


def save_rules():
    """保存规则配置"""
    global _rules
    if _rules is None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RULES_CONFIG, "w") as f:
        json.dump(_rules, f, ensure_ascii=False, indent=2)


def reset_rules_to_default():
    """重置为默认规则（用于回滚）"""
    global _rules
    _rules = dict(DEFAULT_RULES)
    _rules["updated_at"] = datetime.now().isoformat()
    save_rules()


# ============================================================
# 预判模型状态（准确率统计、自修正）
# ============================================================
_model_state = {
    "total_predictions": 0,
    "correct_predictions": 0,
    "dimension_stats": {
        "failure": {"correct": 0, "total": 0, "false_positive": 0, "false_negative": 0},
        "timeout": {"correct": 0, "total": 0, "false_positive": 0, "false_negative": 0},
        "duplicate": {"correct": 0, "total": 0, "false_positive": 0, "false_negative": 0},
    },
    "consecutive_errors": {"timeout": 0, "failure": 0, "duplicate": 0},
    "last_batch_verify": None,
    "pending_verify_count": 0,
}


def load_model_state():
    global _model_state
    if PREDICTION_STATE.exists():
        try:
            with open(PREDICTION_STATE) as f:
                saved = json.load(f)
            # 合并，兼容旧格式
            for k, v in saved.items():
                if k in _model_state:
                    _model_state[k] = v
                elif k not in ("timeout_threshold_sec", "duplicate_sim_threshold", "pit_keyword_weight", "recent_window"):
                    _model_state[k] = v
        except Exception:
            pass
    return _model_state


def save_model_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREDICTION_STATE, "w") as f:
        json.dump(_model_state, f, ensure_ascii=False, indent=2)


# ============================================================
# 核心预判逻辑
# ============================================================
def _calc_failure_risk(prompt_lower):
    """失败风险：加权评分制"""
    rules = load_rules()
    score = 0
    hits = {"strong": [], "medium": [], "weak": []}

    for word in rules["strong_risk_words"]:
        if word.lower() in prompt_lower:
            score += 3
            hits["strong"].append(word)
    for word in rules["medium_risk_words"]:
        if word.lower() in prompt_lower:
            score += 2
            hits["medium"].append(word)
    for word in rules["weak_risk_words"]:
        if word.lower() in prompt_lower:
            score += 1
            hits["weak"].append(word)

    thresholds = rules["failure_score_thresholds"]
    if score >= thresholds["high"]:
        level = "high"
    elif score >= thresholds["medium"]:
        level = "medium"
    else:
        level = "low"

    return level, score, hits


def _calc_timeout_risk(task_type, prompt_lower, state=None):
    """超时风险：分任务类型阈值 + 最近失败率"""
    rules = load_rules()
    threshold = rules["timeout_thresholds_by_type"].get(task_type, rules["timeout_thresholds_by_type"]["default"])

    # 基础风险：任务类型决定
    if task_type in ("deep", "l4"):
        base_ratio = 0.7  # 天生高耗时
    elif task_type in ("cog", "eng"):
        base_ratio = 0.5
    else:
        base_ratio = 0.3

    # prompt中出现"批量""大量""遍历"等词，提升风险
    if any(w in prompt_lower for w in ["批量", "大量", "遍历", "全量", "循环", "递归"]):
        base_ratio += 0.2

    # 最近失败率高，提升风险
    if state:
        recent = state.get("recent_task_stats", [])
        if recent:
            fail_rate = sum(1 for r in recent if r.get("status") == "failed") / len(recent)
            if fail_rate > 0.3:
                base_ratio += 0.2

    thresholds = rules["timeout_ratio_thresholds"]
    if base_ratio >= thresholds["high"]:
        level = "high"
    elif base_ratio >= thresholds["medium"]:
        level = "medium"
    else:
        level = "low"

    return level, threshold, round(base_ratio, 2)


def _calc_duplicate_risk(task_type, state=None):
    """重复风险：同类任务连续执行次数"""
    rules = load_rules()
    thresholds = rules["duplicate_count_thresholds"]

    same_type_count = 0
    if state:
        recent = state.get("recent_task_stats", [])
        if recent:
            same_type_count = sum(1 for r in recent if r.get("task_type") == task_type)

    if same_type_count >= thresholds["high"]:
        level = "high"
    elif same_type_count >= thresholds["medium"]:
        level = "medium"
    else:
        level = "low"

    return level, same_type_count


def predict_task(task_id, task_type, prompt, state=None):
    """
    任务执行前预判：失败风险/超时风险/重复风险
    返回预判结果dict（含评分明细，供批量校验使用）
    """
    load_model_state()
    rules = load_rules()
    prompt_lower = prompt.lower() if prompt else ""

    # 三维度独立预判
    failure_level, failure_score, failure_hits = _calc_failure_risk(prompt_lower)
    timeout_level, timeout_threshold, timeout_ratio = _calc_timeout_risk(task_type, prompt_lower, state)
    duplicate_level, duplicate_count = _calc_duplicate_risk(task_type, state)

    all_hits = failure_hits["strong"] + failure_hits["medium"] + failure_hits["weak"]

    prediction = {
        "task_id": task_id,
        "task_type": task_type,
        "timestamp": datetime.now().isoformat(),
        "rules_version": rules.get("version", "2.0"),
        # 失败风险
        "failure_risk": failure_level,
        "failure_score": failure_score,
        "failure_hits": failure_hits,
        # 超时风险
        "timeout_risk": timeout_level,
        "timeout_threshold_sec": timeout_threshold,
        "timeout_ratio_estimate": timeout_ratio,
        # 重复风险
        "duplicate_risk": duplicate_level,
        "duplicate_count": duplicate_count,
        # 兼容旧字段
        "pit_keywords_hit": all_hits,
        "confidence": "initial" if _model_state["total_predictions"] < 20 else "learning",
        # 校验状态
        "verified": False,
    }
    return prediction


# ============================================================
# 结果回填与验证
# ============================================================
def verify_prediction(prediction, actual_result):
    """
    任务执行后验证：对照预判与实际，记录误差，自动回填
    actual_result: execute_single_api的返回值
    """
    if not prediction:
        return None

    load_model_state()
    rules = load_rules()

    # 实际结果
    actual_timeout = actual_result.get("duration", 0) > prediction.get("timeout_threshold_sec", 120)
    actual_failure = actual_result.get("status") != "success"
    actual_duplicate = actual_result.get("is_duplicate", False)

    # 逐项验证（预判为high/medium算"有风险"，low算"无风险"）
    errors = []

    # 失败验证
    pred_failure = prediction["failure_risk"] in ("high", "medium")
    if pred_failure != actual_failure:
        errors.append("failure")
        _model_state["dimension_stats"]["failure"]["total"] += 1
        if pred_failure and not actual_failure:
            _model_state["dimension_stats"]["failure"]["false_positive"] += 1
        else:
            _model_state["dimension_stats"]["failure"]["false_negative"] += 1
        _model_state["consecutive_errors"]["failure"] += 1
    else:
        _model_state["dimension_stats"]["failure"]["correct"] += 1
        _model_state["dimension_stats"]["failure"]["total"] += 1
        _model_state["consecutive_errors"]["failure"] = 0

    # 超时验证
    pred_timeout = prediction["timeout_risk"] in ("high", "medium")
    if pred_timeout != actual_timeout:
        errors.append("timeout")
        _model_state["dimension_stats"]["timeout"]["total"] += 1
        if pred_timeout and not actual_timeout:
            _model_state["dimension_stats"]["timeout"]["false_positive"] += 1
        else:
            _model_state["dimension_stats"]["timeout"]["false_negative"] += 1
        _model_state["consecutive_errors"]["timeout"] += 1
    else:
        _model_state["dimension_stats"]["timeout"]["correct"] += 1
        _model_state["dimension_stats"]["timeout"]["total"] += 1
        _model_state["consecutive_errors"]["timeout"] = 0

    # 重复验证
    pred_dup = prediction["duplicate_risk"] in ("high", "medium")
    if pred_dup != actual_duplicate:
        errors.append("duplicate")
        _model_state["dimension_stats"]["duplicate"]["total"] += 1
        if pred_dup and not actual_duplicate:
            _model_state["dimension_stats"]["duplicate"]["false_positive"] += 1
        else:
            _model_state["dimension_stats"]["duplicate"]["false_negative"] += 1
        _model_state["consecutive_errors"]["duplicate"] += 1
    else:
        _model_state["dimension_stats"]["duplicate"]["correct"] += 1
        _model_state["dimension_stats"]["duplicate"]["total"] += 1
        _model_state["consecutive_errors"]["duplicate"] = 0

    # 总体准确率（三项全对才算对）
    _model_state["total_predictions"] += 1
    if not errors:
        _model_state["correct_predictions"] += 1
    _model_state["pending_verify_count"] += 1

    save_model_state()

    # 写入日志（标记为已回填待校验）
    log_entry = {
        "prediction": prediction,
        "actual": {
            "status": actual_result.get("status"),
            "duration": round(actual_result.get("duration", 0), 1),
            "is_duplicate": actual_duplicate,
            "error_type": actual_result.get("error_type", ""),
        },
        "errors": errors,
        "batch_verified": False,
        "accuracy_so_far": round(
            _model_state["correct_predictions"] / max(1, _model_state["total_predictions"]), 3
        ),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREDICTION_LOG, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    return log_entry


# ============================================================
# 统计查询
# ============================================================
def get_prediction_stats():
    """获取预判统计"""
    load_model_state()
    total = _model_state["total_predictions"]
    correct = _model_state["correct_predictions"]
    accuracy = correct / max(1, total)

    dim_stats = {}
    for dim, stats in _model_state["dimension_stats"].items():
        t = stats["total"]
        dim_stats[dim] = {
            "accuracy": round(stats["correct"] / max(1, t), 3) if t > 0 else 0,
            "false_positive_rate": round(stats["false_positive"] / max(1, t), 3) if t > 0 else 0,
            "false_negative_rate": round(stats["false_negative"] / max(1, t), 3) if t > 0 else 0,
            "total": t,
        }

    return {
        "total_predictions": total,
        "correct_predictions": correct,
        "overall_accuracy": round(accuracy, 3),
        "dimension_accuracy": dim_stats,
        "pending_batch_verify": _model_state["pending_verify_count"],
        "last_batch_verify": _model_state.get("last_batch_verify"),
        "rules_version": load_rules().get("version", "2.0"),
        "rules_iteration": load_rules().get("iteration_count", 0),
    }


def get_pending_verify_count():
    """获取待批量校验的记录数"""
    load_model_state()
    return _model_state.get("pending_verify_count", 0)


if __name__ == "__main__":
    print("预判层V2.0自测")
    print("=" * 50)

    # 测试1：低风险任务
    p1 = predict_task("test_001", "exp", "写一段关于宇宙的短文", {})
    print(f"[低风险] 失败={p1['failure_risk']}({p1['failure_score']}分) 超时={p1['timeout_risk']} 重复={p1['duplicate_risk']}")

    # 测试2：中风险任务
    p2 = predict_task("test_002", "eng", "批量配置API参数并同步到数据库，注意超时问题", {})
    print(f"[中风险] 失败={p2['failure_risk']}({p2['failure_score']}分) 超时={p2['timeout_risk']} 重复={p2['duplicate_risk']}")
    print(f"  命中词: 强={p2['failure_hits']['strong']} 中={p2['failure_hits']['medium']} 弱={p2['failure_hits']['weak']}")

    # 测试3：高风险任务
    p3 = predict_task("test_003", "deep", "重构并发线程锁，处理死锁和内存溢出，权限拒绝时降级", {})
    print(f"[高风险] 失败={p3['failure_risk']}({p3['failure_score']}分) 超时={p3['timeout_risk']} 重复={p3['duplicate_risk']}")
    print(f"  命中词: 强={p3['failure_hits']['strong']} 中={p3['failure_hits']['medium']} 弱={p3['failure_hits']['weak']}")

    # 验证回填
    r1 = verify_prediction(p1, {"status": "success", "duration": 30, "is_duplicate": False})
    print(f"\n[验证1] 误差={r1['errors']} 累计准确率={r1['accuracy_so_far']}")

    r2 = verify_prediction(p2, {"status": "failed", "duration": 200, "is_duplicate": False, "error_type": "timeout"})
    print(f"[验证2] 误差={r2['errors']} 累计准确率={r2['accuracy_so_far']}")

    print("\n统计:", json.dumps(get_prediction_stats(), ensure_ascii=False, indent=2))
