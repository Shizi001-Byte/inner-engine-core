#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引擎运行指标分析模块
移植自：.skills/doubao-data-analysis（结构化业务数据分析七决策门方法论）
用途：阴期零消耗任务，分析引擎运行数据，产出可审计的指标报告
原则：纯本地计算，零API调用；L1定向查数+L2诊断归因；所有结论带证据
"""
import json
import glob
import re
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

BASE_DIR = Path(__file__).parent.parent.parent
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
LOG_DIR = BASE_DIR / "logs"
COGNITION_DIR = BASE_DIR / "cognition_pool"
PIT_DIR = BASE_DIR / "data" / "pit_library"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# 九维名称映射
NINE_DIMS = ["zhuji", "lianjing", "yangqi", "jiedan", "yushen", "tongshen", "huanxu", "yangshen", "hedao"]
NINE_DIMS_CN = ["筑基", "炼精", "养气", "结丹", "育神", "通神", "还虚", "阳神", "合道"]


def _load_state():
    """加载引擎状态文件"""
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _analyze_token_consumption(state):
    """维度1：三模型token消耗分析"""
    if not state:
        return {"status": "skipped", "reason": "state not found"}
    models = {}
    total = 0
    for key, name in [("engine_a", "A"), ("engine_b", "B"), ("engine_c", "C")]:
        e = state.get(key, {})
        used = e.get("tokens_used", 0)
        requests = e.get("requests", 0)
        in_flight = e.get("in_flight_tokens", 0)
        avg_per_req = round(used / requests, 1) if requests > 0 else 0
        models[name] = {
            "tokens_used": used, "requests": requests,
            "in_flight": in_flight, "avg_per_request": avg_per_req
        }
        total += used
    # 占比
    for name in models:
        models[name]["percentage"] = round(models[name]["tokens_used"] / total * 100, 1) if total > 0 else 0
    # 额度预测（假设日预算160万）
    daily_budget = 1600000
    remaining = daily_budget - total
    burn_rate = total  # 当前累计消耗
    return {
        "status": "ok",
        "total_tokens": total,
        "daily_budget": daily_budget,
        "remaining": remaining,
        "remaining_percentage": round(remaining / daily_budget * 100, 1),
        "models": models,
        "dominant_model": max(models, key=lambda k: models[k]["tokens_used"]),
        "evidence": f"三模型累计消耗{total/10000:.1f}万token，剩余{remaining/10000:.1f}万（{remaining/daily_budget*100:.0f}%）"
    }


def _analyze_task_stats(state):
    """维度2：任务完成统计"""
    if not state:
        return {"status": "skipped"}
    completed = state.get("tasks_completed", 0)
    failed = state.get("tasks_failed", 0)
    total = completed + failed
    success_rate = round(completed / total * 100, 1) if total > 0 else 0
    # 本转进度
    zhuan = state.get("zhuan_count", 0)
    current_zhuan_tasks = state.get("current_zhuan_tasks", 0)
    # 目标任务
    goal_tasks = state.get("goal_tasks", [])
    failed_goals = state.get("failed_goal_tasks", [])
    return {
        "status": "ok",
        "total_completed": completed,
        "total_failed": failed,
        "success_rate": success_rate,
        "current_zhuan": zhuan,
        "current_zhuan_tasks": current_zhuan_tasks,
        "goal_tasks_count": len(goal_tasks) if isinstance(goal_tasks, list) else 0,
        "failed_goals_count": len(failed_goals) if isinstance(failed_goals, list) else 0,
        "evidence": f"累计完成{completed}任务，失败{failed}，成功率{success_rate}%；当前第{zhuan}转（{current_zhuan_tasks}/20）"
    }


def _analyze_cognition_quality():
    """维度3：认知池质量分布（S/A/B/C四级）"""
    if not COGNITION_DIR.exists():
        return {"status": "skipped", "reason": "cognition_pool not found"}
    files = sorted([f for f in COGNITION_DIR.glob("*.json") if f.is_file()])
    if not files:
        return {"status": "skipped", "reason": "no cognition files"}
    grade_counter = Counter()
    density_values = []
    level_counter = Counter()
    status_counter = Counter()
    # 分析最近100条
    sample = files[-100:] if len(files) > 100 else files
    for f in sample:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            # 等级
            density = data.get("density", {})
            if isinstance(density, dict):
                grade = density.get("grade", "unknown")
            else:
                grade = "unknown"
            grade_counter[grade] += 1
            # 密度值
            if isinstance(density, dict) and "info_density" in density:
                density_values.append(density["info_density"])
            # level/status
            if "level" in data:
                level_counter[str(data["level"])] += 1
            if "status" in data:
                status_counter[str(data["status"])] += 1
        except Exception:
            grade_counter["parse_error"] += 1
    avg_density = round(sum(density_values) / len(density_values), 3) if density_values else 0
    total = len(sample)
    return {
        "status": "ok",
        "total_cognition": len(files),
        "sampled": total,
        "grade_distribution": dict(grade_counter),
        "avg_info_density": avg_density,
        "top_levels": level_counter.most_common(5),
        "top_statuses": status_counter.most_common(5),
        "high_quality_ratio": round((grade_counter.get("S", 0) + grade_counter.get("A", 0)) / total * 100, 1) if total > 0 else 0,
        "evidence": f"认知池共{len(files)}条，抽检{total}条，S+A级占比{(grade_counter.get('S',0)+grade_counter.get('A',0))/total*100:.0f}%，平均信息密度{avg_density}"
    }


def _analyze_nine_dim_balance(state):
    """维度4：九维进度均衡度"""
    if not state:
        return {"status": "skipped"}
    progress = state.get("nine_dim_progress", {})
    if not progress:
        return {"status": "skipped", "reason": "nine_dim_progress not found"}
    dim_values = {}
    for i, dim in enumerate(NINE_DIMS):
        cn = NINE_DIMS_CN[i]
        val = progress.get(dim, progress.get(cn, 0))
        if isinstance(val, dict):
            val = val.get("count", val.get("tasks", 0))
        dim_values[cn] = int(val) if isinstance(val, (int, float)) else 0
    values = list(dim_values.values())
    if not values:
        return {"status": "skipped"}
    max_val = max(values)
    min_val = min(values)
    avg_val = round(sum(values) / len(values), 1)
    # 均衡度：1 - (max-min)/avg，越接近1越均衡
    balance_score = round(1 - (max_val - min_val) / avg_val, 3) if avg_val > 0 else 0
    weak_dims = [dim for dim, val in dim_values.items() if val < avg_val * 0.5]
    strong_dims = [dim for dim, val in dim_values.items() if val > avg_val * 1.5]
    return {
        "status": "ok",
        "dim_progress": dim_values,
        "max": max_val, "min": min_val, "avg": avg_val,
        "balance_score": balance_score,
        "weak_dims": weak_dims,
        "strong_dims": strong_dims,
        "evidence": f"九维均衡度{balance_score}，最强{max(weak_dims+strong_dims, key=lambda d: dim_values[d]) if weak_dims+strong_dims else 'N/A'}({max_val})，最弱{min(weak_dims+strong_dims, key=lambda d: dim_values[d]) if weak_dims+strong_dims else 'N/A'}({min_val})"
    }


def _analyze_log_anomalies(days=1):
    """维度5：日志异常检测（最近N天）"""
    if not LOG_DIR.exists():
        return {"status": "skipped", "reason": "logs not found"}
    log_files = sorted(LOG_DIR.glob("engine_*.log"))
    if not log_files:
        return {"status": "skipped", "reason": "no log files"}
    # 读最近的日志文件
    recent_log = log_files[-1]
    error_patterns = ["ERROR", "Traceback", "Exception", "LOOP-ERR", "FATAL", "CRITICAL"]
    warn_patterns = ["WARN", "timeout", "timed out", "failed", "401", "403", "500"]
    error_count = 0
    warn_count = 0
    error_samples = []
    warn_samples = []
    try:
        with open(recent_log, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        total_lines = len(lines)
        # 只看最近500行
        sample_lines = lines[-500:] if total_lines > 500 else lines
        for line in sample_lines:
            for pat in error_patterns:
                if pat in line:
                    error_count += 1
                    if len(error_samples) < 3:
                        error_samples.append(line.strip()[:150])
                    break
            for pat in warn_patterns:
                if pat in line and pat not in error_patterns:
                    warn_count += 1
                    if len(warn_samples) < 3:
                        warn_samples.append(line.strip()[:150])
                    break
    except Exception as e:
        return {"status": "fail", "error": str(e)}
    status = "ok" if error_count == 0 else "warn" if error_count < 5 else "fail"
    return {
        "status": status,
        "log_file": recent_log.name,
        "lines_scanned": len(sample_lines),
        "error_count": error_count,
        "warn_count": warn_count,
        "error_samples": error_samples,
        "warn_samples": warn_samples,
        "evidence": f"扫描{recent_log.name}最近{len(sample_lines)}行，错误{error_count}条，警告{warn_count}条"
    }


def _analyze_pit_library():
    """维度6：坑库健康度"""
    if not PIT_DIR.exists():
        return {"status": "skipped"}
    files = sorted([f for f in PIT_DIR.glob("*.json") if f.is_file()])
    level_counter = Counter()
    status_counter = Counter()
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            level = data.get("level", "unknown")
            status = data.get("status", "unknown")
            level_counter[level] += 1
            status_counter[status] += 1
        except Exception:
            level_counter["parse_error"] += 1
    return {
        "status": "ok",
        "total_pits": len(files),
        "level_distribution": dict(level_counter),
        "status_distribution": dict(status_counter),
        "fixed_ratio": round(status_counter.get("fixed", 0) / len(files) * 100, 1) if files else 0,
        "evidence": f"坑库共{len(files)}个，L1工程{level_counter.get('L1',0)}个/L2方法{level_counter.get('L2',0)}个/L3认知{level_counter.get('L3',0)}个，已修复{status_counter.get('fixed',0)}个"
    }


def run(state=None, **kwargs):
    """
    阴期任务入口：引擎运行指标结构化分析
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    if state is None:
        state = _load_state()

    report = {
        "report_time": datetime.now().isoformat(),
        "token_consumption": _analyze_token_consumption(state),
        "task_stats": _analyze_task_stats(state),
        "cognition_quality": _analyze_cognition_quality(),
        "nine_dim_balance": _analyze_nine_dim_balance(state),
        "log_anomalies": _analyze_log_anomalies(),
        "pit_library": _analyze_pit_library(),
    }

    # 综合健康度评分（0-100）
    score = 100
    # token剩余低于20%扣10分
    if report["token_consumption"].get("remaining_percentage", 100) < 20:
        score -= 10
    # 任务成功率低于90%扣10分
    if report["task_stats"].get("success_rate", 100) < 90:
        score -= 10
    # 九维均衡度低于0.5扣10分
    if report["nine_dim_balance"].get("balance_score", 1) < 0.5:
        score -= 10
    # 日志有错误扣5-15分
    err = report["log_anomalies"].get("error_count", 0)
    if err > 0:
        score -= min(15, err * 3)
    # 认知S+A占比低于30%扣10分
    if report["cognition_quality"].get("high_quality_ratio", 100) < 30:
        score -= 10
    score = max(0, score)
    report["health_score"] = score
    report["duration_seconds"] = round(time.time() - start, 2)

    # 保存产出
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"metrics_report_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    evidence = (
        f"健康度{score}分 | "
        f"{report['token_consumption'].get('evidence','')} | "
        f"{report['task_stats'].get('evidence','')} | "
        f"{report['cognition_quality'].get('evidence','')}"
    )

    return {
        "ok": score >= 60,
        "name": "yin_metrics_analyzer",
        "result": report,
        "evidence": evidence,
        "output_path": str(output_path)
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
