#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资产预判分级 Asset Prediction V1.0
功能：对扫描到的资产进行评分、分级、复用匹配
- 工程类：核心/边缘/待清理/待重构
- 认知类：公理/经验/假说/冗余
- 内容类：模板/成品/待优化/废弃（暂不启用）
全程本地计算，零token消耗
"""
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
ASSET_DB = DATA_DIR / "asset_db.json"
RULES_CONFIG = DATA_DIR / "asset_rules.json"
ASSET_PREDICTION_DB = DATA_DIR / "asset_prediction_db.json"


def load_rules():
    if RULES_CONFIG.exists():
        with open(RULES_CONFIG) as f:
            return json.load(f)
    return {}


def load_asset_db():
    if ASSET_DB.exists():
        with open(ASSET_DB) as f:
            return json.load(f)
    return {"assets": []}


# ============================================================
# 工程类资产评分分级
# ============================================================
def score_engineering_asset(asset, rules):
    """工程类资产评分：调用频次+新鲜度+报错率+复杂度+复用性"""
    scoring = rules.get("asset_types", {}).get("engineering", {}).get("scoring", {})
    thresholds = rules.get("asset_types", {}).get("engineering", {}).get("thresholds", {})

    # 1. 调用频次分（0-100）：30天内调用次数
    calls = asset.get("calls_30d", 0)
    call_score = min(100, calls * 10)  # 10次以上满分

    # 2. 新鲜度分（0-100）：最近修改时间
    days = asset.get("days_since_modified", 365)
    if days <= 7:
        recency_score = 100
    elif days <= 30:
        recency_score = 80
    elif days <= 90:
        recency_score = 50
    else:
        recency_score = 20

    # 3. 报错率分（0-100）：报错率越低分越高
    error_rate = asset.get("error_rate", 0)
    error_score = max(0, 100 - error_rate * 200)  # 报错率50%以上0分

    # 4. 复杂度分（0-100）：适中复杂度得分高，过低可能是废文件
    complexity = asset.get("complexity_score", 0)
    if 20 <= complexity <= 80:
        complexity_score = 80
    elif complexity > 80:
        complexity_score = 60  # 过于复杂可能需要重构
    else:
        complexity_score = 40  # 过于简单可能是废文件

    # 5. 复用性分（0-100）：被import或被引用的次数（简化为调用次数代理）
    reusability_score = min(100, calls * 8)

    # 加权总分
    total_score = (
        call_score * scoring.get("call_frequency_weight", 0.35) +
        recency_score * scoring.get("recency_weight", 0.25) +
        error_score * scoring.get("error_rate_weight", 0.20) +
        complexity_score * scoring.get("complexity_weight", 0.10) +
        reusability_score * scoring.get("reusability_weight", 0.10)
    )

    # 分级
    stale_days = rules.get("asset_types", {}).get("engineering", {}).get("stale_days", 90)
    if error_rate >= thresholds.get("refactor", {}).get("error_rate_threshold", 0.20) and calls > 0:
        grade = "refactor"  # 待重构
    elif days >= stale_days and calls == 0:
        grade = "stale"  # 待清理
    elif total_score >= thresholds.get("core", {}).get("min_score", 70):
        grade = "core"  # 核心资产
    else:
        grade = "edge"  # 边缘资产

    return {
        "total_score": round(total_score, 1),
        "dimension_scores": {
            "call_frequency": round(call_score, 1),
            "recency": round(recency_score, 1),
            "error_rate": round(error_score, 1),
            "complexity": round(complexity_score, 1),
            "reusability": round(reusability_score, 1),
        },
        "grade": grade,
        "grade_name": {
            "core": "核心资产",
            "edge": "边缘资产",
            "stale": "待清理资产",
            "refactor": "待重构资产",
        }.get(grade, grade),
    }


# ============================================================
# 认知类资产评分分级
# ============================================================
def score_cognition_asset(asset, rules):
    """认知类资产评分：密度+应用次数+新鲜度+独特性+时效性"""
    scoring = rules.get("asset_types", {}).get("cognition", {}).get("scoring", {})

    # 1. 密度分（0-100）
    density = asset.get("density", 0)
    density_score = min(100, density * 100)

    # 2. 应用次数分（0-100）
    applications = asset.get("application_count", 0)
    app_score = min(100, applications * 20)  # 5次以上满分

    # 3. 新鲜度分（0-100）
    days = asset.get("days_since_modified", 365)
    if days <= 7:
        recency_score = 100
    elif days <= 30:
        recency_score = 80
    elif days <= 90:
        recency_score = 50
    else:
        recency_score = 30

    # 4. 独特性分（0-100）：坑库类认知独特性高
    if asset.get("is_pit", False):
        uniqueness_score = 90
    else:
        uniqueness_score = 60  # 普通认知默认中等独特性

    # 5. 时效性分（0-100）：工程类认知时效性强，哲学类认知时效性弱
    timeliness_score = 70  # 默认中等

    # 加权总分
    total_score = (
        density_score * scoring.get("density_weight", 0.30) +
        app_score * scoring.get("application_count_weight", 0.30) +
        recency_score * scoring.get("recency_weight", 0.15) +
        uniqueness_score * scoring.get("uniqueness_weight", 0.15) +
        timeliness_score * scoring.get("timeliness_weight", 0.10)
    )

    # 分级
    thresholds = rules.get("asset_types", {}).get("cognition", {}).get("thresholds", {})
    if density >= thresholds.get("axiom", {}).get("min_density", 0.7) and applications >= thresholds.get("axiom", {}).get("min_applications", 5):
        grade = "axiom"  # 一级公理
    elif density >= thresholds.get("experience", {}).get("min_density", 0.5) and applications >= thresholds.get("experience", {}).get("min_applications", 2):
        grade = "experience"  # 二级经验
    elif density >= thresholds.get("hypothesis", {}).get("min_density", 0.3):
        grade = "hypothesis"  # 三级假说
    else:
        grade = "redundant"  # 冗余待合并

    return {
        "total_score": round(total_score, 1),
        "dimension_scores": {
            "density": round(density_score, 1),
            "application_count": round(app_score, 1),
            "recency": round(recency_score, 1),
            "uniqueness": round(uniqueness_score, 1),
            "timeliness": round(timeliness_score, 1),
        },
        "grade": grade,
        "grade_name": {
            "axiom": "一级公理",
            "experience": "二级经验",
            "hypothesis": "三级假说",
            "redundant": "冗余待合并",
        }.get(grade, grade),
    }


# ============================================================
# 全量预判分级
# ============================================================
def predict_all_assets():
    """对所有资产进行预判分级"""
    rules = load_rules()
    db = load_asset_db()
    assets = db.get("assets", [])

    results = []
    grade_stats = defaultdict(lambda: defaultdict(int))

    for asset in assets:
        asset_type = asset.get("asset_type", "unknown")
        if asset_type == "engineering":
            prediction = score_engineering_asset(asset, rules)
        elif asset_type == "cognition":
            prediction = score_cognition_asset(asset, rules)
        else:
            prediction = {"total_score": 0, "grade": "unknown", "grade_name": "未知"}

        result = {
            "path": asset.get("path"),
            "asset_type": asset_type,
            "name": asset.get("name"),
            "prediction": prediction,
            "asset_meta": {
                "size_bytes": asset.get("size_bytes"),
                "days_since_modified": asset.get("days_since_modified"),
                "calls_30d": asset.get("calls_30d", 0),
                "errors_30d": asset.get("errors_30d", 0),
                "density": asset.get("density", 0),
                "application_count": asset.get("application_count", 0),
            },
            "verified": False,
            "predicted_at": datetime.now().isoformat(),
        }
        results.append(result)
        grade_stats[asset_type][prediction["grade"]] += 1

    # 保存预判结果
    prediction_db = {
        "predicted_at": datetime.now().isoformat(),
        "total_assets": len(results),
        "grade_stats": dict(grade_stats),
        "predictions": results,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ASSET_PREDICTION_DB, "w") as f:
        json.dump(prediction_db, f, ensure_ascii=False, indent=2)

    return prediction_db


# ============================================================
# 正向复用匹配：新任务进来时，查找可复用资产
# ============================================================
def find_reusable_assets(task_type, prompt, top_k=3):
    """
    正向链路：新任务预判时，查找可复用的存量资产
    返回：可复用资产列表（核心资产优先）
    """
    if not ASSET_PREDICTION_DB.exists():
        return []

    with open(ASSET_PREDICTION_DB) as f:
        db = json.load(f)

    predictions = db.get("predictions", [])
    prompt_lower = prompt.lower() if prompt else ""

    # 筛选核心/高价值资产
    candidates = []
    for p in predictions:
        grade = p["prediction"].get("grade", "")
        score = p["prediction"].get("total_score", 0)
        name = p.get("name", "").lower()
        path = p.get("path", "").lower()

        # 核心资产或高分资产
        if grade in ("core", "axiom", "experience") or score >= 60:
            # 简单关键词匹配
            relevance = 0
            for keyword in prompt_lower.split():
                if len(keyword) > 1 and keyword in name + path:
                    relevance += 1
            if relevance > 0 or grade in ("core", "axiom"):
                candidates.append({
                    "path": p["path"],
                    "name": p["name"],
                    "asset_type": p["asset_type"],
                    "grade": grade,
                    "grade_name": p["prediction"].get("grade_name", ""),
                    "score": score,
                    "relevance": relevance,
                })

    # 按相关性+分数排序
    candidates.sort(key=lambda x: (x["relevance"], x["score"]), reverse=True)
    return candidates[:top_k]


def get_prediction_summary():
    """获取预判分级摘要"""
    if not ASSET_PREDICTION_DB.exists():
        return {"error": "无预判数据，请先运行predict_all_assets()"}

    with open(ASSET_PREDICTION_DB) as f:
        db = json.load(f)

    return {
        "predicted_at": db.get("predicted_at"),
        "total_assets": db.get("total_assets"),
        "grade_stats": db.get("grade_stats", {}),
        "core_assets": [p["path"] for p in db["predictions"]
                        if p["prediction"].get("grade") in ("core", "axiom")][:10],
        "stale_assets": [p["path"] for p in db["predictions"]
                         if p["prediction"].get("grade") in ("stale", "redundant")][:10],
    }


if __name__ == "__main__":
    print("=" * 50)
    print("资产预判分级 V1.0")
    print("=" * 50)

    result = predict_all_assets()
    print(f"\n预判完成: {result['total_assets']}个资产")

    print("\n【分级统计】")
    for asset_type, grades in result["grade_stats"].items():
        print(f"  {asset_type}:")
        for grade, count in grades.items():
            print(f"    {grade}: {count}")

    summary = get_prediction_summary()
    print(f"\n【核心资产Top10】")
    for p in summary.get("core_assets", []):
        print(f"  {p}")

    print(f"\n【待清理/冗余资产Top10】")
    for p in summary.get("stale_assets", []):
        print(f"  {p}")

    # 测试复用匹配
    print("\n【复用匹配测试】")
    reusable = find_reusable_assets("eng", "引擎配置 API 并发 超时", top_k=3)
    for r in reusable:
        print(f"  {r['grade_name']} | {r['name']} | 分数{r['score']} | 相关度{r['relevance']}")
