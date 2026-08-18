#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资产预判校验迭代 Asset Verify V1.0
功能：对资产预判结果进行批量校验，拆解误判，自动迭代规则
- 校验分级准确性
- 闲置资产清单
- 高复用资产Top榜
- 规则权重自动调整
全程本地计算，零token消耗
"""
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
ASSET_DB = DATA_DIR / "asset_db.json"
ASSET_PREDICTION_DB = DATA_DIR / "asset_prediction_db.json"
RULES_CONFIG = DATA_DIR / "asset_rules.json"
VERIFY_REPORT_DIR = DATA_DIR / "asset_verify_reports"


def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def verify_asset_predictions(auto_iterate=True, dry_run=False):
    """
    批量校验资产预判结果
    auto_iterate: 是否自动迭代规则
    dry_run: 只输出报告不修改规则
    """
    pred_db = load_json(ASSET_PREDICTION_DB)
    predictions = pred_db.get("predictions", [])
    if not predictions:
        return {"error": "无预判数据，请先运行asset_prediction.py"}

    rules = load_json(RULES_CONFIG)

    # ============================================================
    # 1. 分级统计
    # ============================================================
    grade_stats = defaultdict(lambda: defaultdict(int))
    score_distribution = defaultdict(list)

    for p in predictions:
        atype = p["asset_type"]
        grade = p["prediction"]["grade"]
        score = p["prediction"]["total_score"]
        grade_stats[atype][grade] += 1
        score_distribution[atype].append(score)

    # ============================================================
    # 2. 工程类校验：误判分析
    # ============================================================
    eng_assets = [p for p in predictions if p["asset_type"] == "engineering"]
    eng_issues = []

    # 2.1 待清理资产检查：90天未修改且0调用
    stale_candidates = [p for p in eng_assets
                        if p["asset_meta"].get("days_since_modified", 0) >= 90
                        and p["asset_meta"].get("calls_30d", 0) == 0]
    if stale_candidates:
        eng_issues.append({
            "type": "stale_candidates",
            "title": "待清理资产候选",
            "count": len(stale_candidates),
            "assets": [p["path"] for p in stale_candidates[:10]],
        })

    # 2.2 高报错资产检查
    high_error = [p for p in eng_assets
                  if p["asset_meta"].get("errors_30d", 0) >= 3]
    if high_error:
        eng_issues.append({
            "type": "high_error_assets",
            "title": "高报错资产（待重构候选）",
            "count": len(high_error),
            "assets": [f"{p['path']}({p['asset_meta']['errors_30d']}次报错)" for p in high_error[:10]],
        })

    # 2.3 核心资产确认：调用次数Top10
    top_called = sorted(eng_assets, key=lambda x: x["asset_meta"].get("calls_30d", 0), reverse=True)[:10]
    core_confirmed = [p for p in top_called if p["prediction"]["grade"] == "core"]

    # ============================================================
    # 3. 认知类校验：误判分析
    # ============================================================
    cog_assets = [p for p in predictions if p["asset_type"] == "cognition"]
    cog_issues = []

    # 3.1 高密度认知检查
    high_density = [p for p in cog_assets if p["asset_meta"].get("density", 0) >= 0.5]
    if high_density:
        cog_issues.append({
            "type": "high_density_cognition",
            "title": "高密度认知（应升级为公理/经验）",
            "count": len(high_density),
            "assets": [f"{p['name']}(密度{p['asset_meta']['density']})" for p in high_density[:10]],
        })

    # 3.2 冗余认知检查：低密度+0应用
    redundant = [p for p in cog_assets
                 if p["asset_meta"].get("density", 0) < 0.3
                 and p["asset_meta"].get("application_count", 0) == 0]
    if redundant:
        cog_issues.append({
            "type": "redundant_cognition",
            "title": "冗余认知候选（低密度+零应用）",
            "count": len(redundant),
            "assets": [p["path"] for p in redundant[:10]],
        })

    # 3.3 坑库资产确认
    pit_assets = [p for p in cog_assets if "pit_library" in p.get("path", "")]
    if pit_assets:
        cog_issues.append({
            "type": "pit_library_assets",
            "title": "坑库资产（独特性高，应标记为经验级）",
            "count": len(pit_assets),
        })

    # ============================================================
    # 4. 规则迭代建议
    # ============================================================
    suggestions = []

    # 4.1 工程类：如果全是edge，说明调用次数统计有问题或阈值太高
    eng_grades = grade_stats.get("engineering", {})
    if eng_grades.get("core", 0) == 0 and len(eng_assets) > 10:
        suggestions.append({
            "type": "eng_threshold_adjust",
            "title": "工程类核心资产阈值可能过高，建议降低core阈值或优化调用统计",
            "current_core_threshold": rules.get("asset_types", {}).get("engineering", {}).get("thresholds", {}).get("core", {}).get("min_score", 70),
            "suggested": 50,
        })

    # 4.2 认知类：如果全是redundant，说明密度提取有问题
    cog_grades = grade_stats.get("cognition", {})
    if cog_grades.get("axiom", 0) == 0 and cog_grades.get("experience", 0) == 0 and len(cog_assets) > 50:
        suggestions.append({
            "type": "cog_density_extraction",
            "title": "认知类密度提取可能失效，全量被判为冗余",
            "action": "优化asset_scanner.py中的密度提取逻辑",
        })

    # 4.3 闲置阈值调整
    stale_count = eng_grades.get("stale", 0)
    if stale_count > len(eng_assets) * 0.3:
        suggestions.append({
            "type": "stale_threshold_adjust",
            "title": "待清理资产占比过高，建议上调stale天数阈值",
            "current": rules.get("asset_types", {}).get("engineering", {}).get("stale_days", 90),
            "suggested": 120,
        })

    # ============================================================
    # 5. 自动迭代低风险规则
    # ============================================================
    auto_changes = []
    if auto_iterate and rules and not dry_run:
        rules_changed = False
        auto_cfg = rules.get("auto_iterate", {})

        # 5.1 闲置阈值微调
        if stale_count > len(eng_assets) * 0.3 and auto_cfg.get("enabled", True):
            current_stale = rules.get("asset_types", {}).get("engineering", {}).get("stale_days", 90)
            new_stale = current_stale + auto_cfg.get("stale_days_adjust_step", 7)
            rules["asset_types"]["engineering"]["stale_days"] = new_stale
            auto_changes.append(f"工程类闲置阈值: {current_stale}→{new_stale}天")
            rules_changed = True

        if rules_changed:
            rules["iteration_count"] = rules.get("iteration_count", 0) + 1
            rules["updated_at"] = datetime.now().isoformat()
            save_json(RULES_CONFIG, rules)

    # ============================================================
    # 6. 标记已校验
    # ============================================================
    if not dry_run:
        for p in predictions:
            p["verified"] = True
            p["verified_at"] = datetime.now().isoformat()
        pred_db["last_verified"] = datetime.now().isoformat()
        save_json(ASSET_PREDICTION_DB, pred_db)

    # ============================================================
    # 7. 生成报告
    # ============================================================
    report = {
        "verify_time": datetime.now().isoformat(),
        "total_assets": len(predictions),
        "grade_stats": dict(grade_stats),
        "engineering_issues": eng_issues,
        "cognition_issues": cog_issues,
        "suggestions": suggestions,
        "auto_changes": auto_changes,
        "dry_run": dry_run,
        "score_summary": {
            atype: {
                "avg": round(sum(scores) / len(scores), 1) if scores else 0,
                "max": max(scores) if scores else 0,
                "min": min(scores) if scores else 0,
            }
            for atype, scores in score_distribution.items()
        },
    }

    VERIFY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = VERIFY_REPORT_DIR / f"asset_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_json(report_path, report)
    report["report_path"] = str(report_path)

    return report


def print_report(report):
    """打印可读报告"""
    if "error" in report:
        print(f"[跳过] {report['error']}")
        return

    print("=" * 60)
    print(f"资产预判校验报告 | 总资产: {report['total_assets']}")
    print("=" * 60)

    print("\n【分级统计】")
    for atype, grades in report["grade_stats"].items():
        print(f"  {atype}:")
        for grade, count in grades.items():
            print(f"    {grade}: {count}")

    print("\n【分数概览】")
    for atype, stats in report.get("score_summary", {}).items():
        print(f"  {atype}: 平均{stats['avg']} 最高{stats['max']} 最低{stats['min']}")

    if report["engineering_issues"]:
        print("\n【工程类问题】")
        for issue in report["engineering_issues"]:
            print(f"  [{issue['type']}] {issue['title']} ({issue['count']}个)")
            for a in issue.get("assets", [])[:3]:
                print(f"    - {a}")

    if report["cognition_issues"]:
        print("\n【认知类问题】")
        for issue in report["cognition_issues"]:
            print(f"  [{issue['type']}] {issue['title']} ({issue['count']}个)")
            for a in issue.get("assets", [])[:3]:
                print(f"    - {a}")

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
    parser = argparse.ArgumentParser(description="资产预判批量校验")
    parser.add_argument("--dry-run", action="store_true", help="只输出报告不修改规则")
    parser.add_argument("--no-auto", action="store_true", help="不自动迭代规则")
    args = parser.parse_args()

    report = verify_asset_predictions(auto_iterate=not args.no_auto, dry_run=args.dry_run)
    print_report(report)
