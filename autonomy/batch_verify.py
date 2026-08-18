#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量校验复盘脚本 Batch Verify V1.0
功能：攒够一批预判记录后，集中校验，拆解误报漏报，校准阈值，自动迭代规则
触发条件：pending_verify_count >= 100 或 手动调用
全程本地计算，零token消耗
"""
import json
import sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PREDICTION_LOG = DATA_DIR / "prediction_log.jsonl"
PREDICTION_STATE = DATA_DIR / "prediction_state.json"
RULES_CONFIG = DATA_DIR / "prediction_rules.json"
VERIFY_REPORT_DIR = DATA_DIR / "prediction_reports"


def load_jsonl(path):
    """加载jsonl文件"""
    records = []
    if not path.exists():
        return records
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records


def save_jsonl(path, records):
    """保存jsonl文件"""
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def calc_percentile(values, p):
    """计算百分位数"""
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def batch_verify(auto_iterate=True, dry_run=False):
    """
    批量校验主函数
    auto_iterate: 是否自动迭代低风险规则
    dry_run: 只输出报告不修改规则
    返回：校验报告dict
    """
    records = load_jsonl(PREDICTION_LOG)
    if not records:
        return {"error": "无预判记录"}

    # 筛选未批量校验的记录
    pending = [r for r in records if not r.get("batch_verified", False)]
    if not pending:
        return {"error": "无待校验记录", "total_records": len(records)}

    # ============================================================
    # 1. 三维度准确率统计
    # ============================================================
    dim_stats = {"failure": {"correct": 0, "fp": 0, "fn": 0, "total": 0},
                 "timeout": {"correct": 0, "fp": 0, "fn": 0, "total": 0},
                 "duplicate": {"correct": 0, "fp": 0, "fn": 0, "total": 0}}

    for r in pending:
        errors = r.get("errors", [])
        pred = r.get("prediction", {})
        actual = r.get("actual", {})

        for dim in ("failure", "timeout", "duplicate"):
            dim_stats[dim]["total"] += 1
            if dim in errors:
                # 判断是误报还是漏报
                pred_risk = pred.get(f"{dim}_risk", "low") in ("high", "medium")
                if dim == "failure":
                    actual_risk = actual.get("status") != "success"
                elif dim == "timeout":
                    actual_risk = actual.get("duration", 0) > pred.get("timeout_threshold_sec", 120)
                else:
                    actual_risk = actual.get("is_duplicate", False)

                if pred_risk and not actual_risk:
                    dim_stats[dim]["fp"] += 1  # 误报：预判有风险实际没风险
                else:
                    dim_stats[dim]["fn"] += 1  # 漏报：预判没风险实际有风险
            else:
                dim_stats[dim]["correct"] += 1

    # ============================================================
    # 2. 误报关键词拆解（频繁命中但实际未失败）
    # ============================================================
    fp_word_counter = Counter()
    fp_task_types = Counter()
    for r in pending:
        if "failure" in r.get("errors", []):
            pred = r.get("prediction", {})
            actual = r.get("actual", {})
            pred_risk = pred.get("failure_risk", "low") in ("high", "medium")
            actual_failure = actual.get("status") != "success"
            if pred_risk and not actual_failure:  # 误报
                hits = pred.get("failure_hits", {})
                for level, words in hits.items():
                    for w in words:
                        fp_word_counter[f"{level}:{w}"] += 1
                fp_task_types[pred.get("task_type", "unknown")] += 1

    # ============================================================
    # 3. 漏报关键词提取（真实失败但预判low）
    # ============================================================
    fn_error_types = Counter()
    fn_task_types = Counter()
    for r in pending:
        if "failure" in r.get("errors", []):
            pred = r.get("prediction", {})
            actual = r.get("actual", {})
            pred_risk = pred.get("failure_risk", "low") in ("high", "medium")
            actual_failure = actual.get("status") != "success"
            if not pred_risk and actual_failure:  # 漏报
                fn_error_types[actual.get("error_type", "unknown")] += 1
                fn_task_types[pred.get("task_type", "unknown")] += 1

    # ============================================================
    # 4. 超时阈值校准（按任务类型统计P80/P95）
    # ============================================================
    timeout_by_type = defaultdict(list)
    for r in pending:
        pred = r.get("prediction", {})
        actual = r.get("actual", {})
        ttype = pred.get("task_type", "default")
        duration = actual.get("duration", 0)
        if duration > 0:
            timeout_by_type[ttype].append(duration)

    timeout_calibration = {}
    for ttype, durations in timeout_by_type.items():
        timeout_calibration[ttype] = {
            "count": len(durations),
            "avg": round(sum(durations) / len(durations), 1),
            "p80": calc_percentile(durations, 80),
            "p95": calc_percentile(durations, 95),
            "max": max(durations),
        }

    # ============================================================
    # 5. 规则迭代建议
    # ============================================================
    suggestions = []
    rules = json.load(open(RULES_CONFIG)) if RULES_CONFIG.exists() else None

    # 5.1 弱风险词降权建议（误报Top5的弱风险词）
    weak_fp = [(w.split(":", 1)[1], c) for w, c in fp_word_counter.most_common(20) if w.startswith("weak:")]
    if weak_fp:
        suggestions.append({
            "type": "weak_word_demote",
            "title": "弱风险词误报过高，建议降权或移除",
            "words": weak_fp[:5],
            "action": "将误报率>30%的弱风险词从列表中移除",
        })

    # 5.2 超时阈值调整建议
    if rules:
        current_thresholds = rules.get("timeout_thresholds_by_type", {})
        for ttype, stats in timeout_calibration.items():
            current = current_thresholds.get(ttype, 120)
            p95 = stats["p95"]
            if p95 > current * 1.2:  # P95超过当前阈值20%，建议上调
                suggestions.append({
                    "type": "timeout_threshold_adjust",
                    "title": f"{ttype}任务超时阈值偏低",
                    "current": current,
                    "suggested": int(p95 * 1.1),
                    "p95_actual": p95,
                })
            elif p95 < current * 0.5:  # P95低于当前阈值50%，建议下调
                suggestions.append({
                    "type": "timeout_threshold_adjust",
                    "title": f"{ttype}任务超时阈值偏高",
                    "current": current,
                    "suggested": max(60, int(p95 * 1.2)),
                    "p95_actual": p95,
                })

    # 5.3 漏报新增风险词建议
    if fn_error_types:
        suggestions.append({
            "type": "new_risk_words",
            "title": "漏报失败原因，建议新增为风险词",
            "error_types": fn_error_types.most_common(5),
        })

    # ============================================================
    # 6. 自动迭代低风险规则
    # ============================================================
    auto_changes = []
    if auto_iterate and rules and not dry_run:
        rules_changed = False

        # 6.1 移除误报率最高的弱风险词（Top3，且误报次数>=3）
        if weak_fp:
            to_remove = [w for w, c in weak_fp[:3] if c >= 3]
            if to_remove:
                original_weak = rules.get("weak_risk_words", [])
                new_weak = [w for w in original_weak if w not in to_remove]
                if len(new_weak) < len(original_weak):
                    rules["weak_risk_words"] = new_weak
                    auto_changes.append(f"移除误报弱风险词: {to_remove}")
                    rules_changed = True

        # 6.2 超时阈值微调（P95偏差>20%时调整）
        for ttype, stats in timeout_calibration.items():
            current = rules.get("timeout_thresholds_by_type", {}).get(ttype)
            if current:
                p95 = stats["p95"]
                if p95 > current * 1.2:
                    new_val = int(p95 * 1.1)
                    rules["timeout_thresholds_by_type"][ttype] = new_val
                    auto_changes.append(f"{ttype}超时阈值: {current}→{new_val}")
                    rules_changed = True
                elif p95 < current * 0.5 and p95 > 30:
                    new_val = max(60, int(p95 * 1.2))
                    rules["timeout_thresholds_by_type"][ttype] = new_val
                    auto_changes.append(f"{ttype}超时阈值: {current}→{new_val}")
                    rules_changed = True

        if rules_changed:
            rules["iteration_count"] = rules.get("iteration_count", 0) + 1
            rules["updated_at"] = datetime.now().isoformat()
            with open(RULES_CONFIG, "w") as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)

    # ============================================================
    # 7. 标记已校验 + 更新state
    # ============================================================
    if not dry_run:
        for r in records:
            if not r.get("batch_verified", False):
                r["batch_verified"] = True
                r["batch_verified_at"] = datetime.now().isoformat()
        save_jsonl(PREDICTION_LOG, records)

        # 更新state
        state = json.load(open(PREDICTION_STATE)) if PREDICTION_STATE.exists() else {}
        state["pending_verify_count"] = 0
        state["last_batch_verify"] = datetime.now().isoformat()
        state["last_batch_verify_count"] = len(pending)
        with open(PREDICTION_STATE, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    # ============================================================
    # 8. 生成报告
    # ============================================================
    report = {
        "verify_time": datetime.now().isoformat(),
        "batch_size": len(pending),
        "total_records": len(records),
        "dimension_accuracy": {
            dim: {
                "accuracy": round(s["correct"] / max(1, s["total"]), 3),
                "false_positive": s["fp"],
                "false_negative": s["fn"],
                "correct": s["correct"],
                "total": s["total"],
            }
            for dim, s in dim_stats.items()
        },
        "false_positive_top_words": fp_word_counter.most_common(10),
        "false_negative_error_types": fn_error_types.most_common(5),
        "timeout_calibration": timeout_calibration,
        "suggestions": suggestions,
        "auto_changes": auto_changes,
        "dry_run": dry_run,
    }

    # 保存报告
    VERIFY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = VERIFY_REPORT_DIR / f"verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    report["report_path"] = str(report_path)

    return report


def print_report(report):
    """打印可读报告"""
    if "error" in report:
        print(f"[跳过] {report['error']}")
        return

    print("=" * 60)
    print(f"批量校验报告 | 批次大小: {report['batch_size']} | 总记录: {report['total_records']}")
    print("=" * 60)

    print("\n【三维度准确率】")
    for dim, stats in report["dimension_accuracy"].items():
        print(f"  {dim:10s}: 准确率={stats['accuracy']:.1%}  误报={stats['false_positive']}  漏报={stats['false_negative']}  正确={stats['correct']}/{stats['total']}")

    if report["false_positive_top_words"]:
        print("\n【误报Top关键词】")
        for word, count in report["false_positive_top_words"][:5]:
            print(f"  {word}: {count}次")

    if report["false_negative_error_types"]:
        print("\n【漏报失败类型】")
        for etype, count in report["false_negative_error_types"]:
            print(f"  {etype}: {count}次")

    if report["timeout_calibration"]:
        print("\n【超时阈值校准】")
        for ttype, stats in report["timeout_calibration"].items():
            print(f"  {ttype:10s}: 样本{stats['count']:3d}  平均{stats['avg']:6.1f}s  P80={stats['p80']:6.1f}  P95={stats['p95']:6.1f}  最大={stats['max']:6.1f}")

    if report["suggestions"]:
        print("\n【优化建议】")
        for i, s in enumerate(report["suggestions"], 1):
            print(f"  {i}. [{s['type']}] {s['title']}")

    if report["auto_changes"]:
        print("\n【已自动迭代】")
        for c in report["auto_changes"]:
            print(f"  ✓ {c}")

    print(f"\n报告已保存: {report.get('report_path', 'N/A')}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="预判层批量校验")
    parser.add_argument("--dry-run", action="store_true", help="只输出报告不修改规则")
    parser.add_argument("--no-auto", action="store_true", help="不自动迭代规则")
    args = parser.parse_args()

    report = batch_verify(auto_iterate=not args.no_auto, dry_run=args.dry_run)
    print_report(report)
