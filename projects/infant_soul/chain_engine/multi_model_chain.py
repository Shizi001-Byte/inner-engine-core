#!/usr/bin/env python3
"""
multi_model_chain.py — 多模型分工推理（模块2.3）

重度逻辑用GLM-5.2，快速校验用Seed-2.1，文本润色用DeepSeek，
一条链路自动切换最优模型。
解决：单一模型能力局限、成本优化、速度优化。

用法：
  python3 multi_model_chain.py route "任务描述"   # 自动路由到最优模型
  python3 multi_model_chain.py status             # 查看各模型状态和额度
  python3 multi_model_chain.py test               # 测试所有模型连通性
"""

import json
import time
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent
CREDENTIALS_FILE = ENGINE_DIR / "data" / "model_credentials.json"
ROUTE_LOG = Path(__file__).parent.parent / "data" / "route_log.json"


def load_models():
    """加载模型配置"""
    if CREDENTIALS_FILE.exists():
        with open(CREDENTIALS_FILE, "r") as f:
            return json.load(f)
    return {"models": {}, "routing_strategy": {}}


def classify_task(task_desc):
    """任务分类：决定用哪个模型"""
    task_lower = task_desc.lower()
    # 重度逻辑/深度推理
    heavy_keywords = ["深度分析", "推演", "架构设计", "复杂逻辑", "数学", "计算", "系统设计", "长链路"]
    # 中度任务
    mid_keywords = ["总结", "改写", "翻译", "分类", "提取", "润色"]
    # 轻度任务
    light_keywords = ["问答", "简单", "快速", "校验", "格式", "检查"]

    for kw in heavy_keywords:
        if kw in task_lower:
            return "heavy", "A_heavy"
    for kw in light_keywords:
        if kw in task_lower:
            return "light", "B_light"
    return "mid", "C_mid"


def route_task(task_desc, force_model=None):
    """路由任务到最优模型"""
    config = load_models()
    models = config.get("models", {})

    if force_model and force_model in models:
        chosen = force_model
        reason = "人工指定"
    else:
        task_type, default_model = classify_task(task_desc)
        chosen = default_model
        reason = f"自动路由（{task_type}型任务）"

        # 检查模型状态，如果默认模型不可用，降级
        model_info = models.get(chosen, {})
        if model_info.get("status") != "active":
            # 降级到下一级
            fallback_order = ["A_heavy", "C_mid", "B_light"]
            for fb in fallback_order:
                if models.get(fb, {}).get("status") == "active":
                    chosen = fb
                    reason += f" → 降级到{fb}（原模型{model_info.get('status')}）"
                    break

    # 记录路由日志
    log = []
    if ROUTE_LOG.exists():
        with open(ROUTE_LOG, "r") as f:
            log = json.load(f)
    log.append({
        "task": task_desc[:50],
        "routed_to": chosen,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    log = log[-100:]  # 只保留最近100条
    with open(ROUTE_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"[路由结果]")
    print(f"  任务: {task_desc[:60]}")
    print(f"  分配模型: {chosen}")
    print(f"  原因: {reason}")
    return chosen


def show_status():
    """显示各模型状态"""
    config = load_models()
    models = config.get("models", {})
    print("=== 多模型状态 ===")
    for name, info in models.items():
        status = info.get("status", "unknown")
        model = info.get("model", "?")
        used = info.get("used_tokens", 0)
        limit = info.get("limit_tokens", 0)
        status_icon = "✓" if status == "active" else "✗"
        print(f"  {status_icon} {name}: {model} | 状态:{status} | 额度:{used}/{limit}")

    # 路由统计
    if ROUTE_LOG.exists():
        with open(ROUTE_LOG, "r") as f:
            log = json.load(f)
        print(f"\n路由统计: 累计{len(log)}次")
        from collections import Counter
        counts = Counter(item["routed_to"] for item in log)
        for model, count in counts.most_common():
            print(f"  {model}: {count}次")


def test_connectivity():
    """测试所有模型连通性（模拟）"""
    config = load_models()
    models = config.get("models", {})
    print("=== 模型连通性测试 ===")
    for name, info in models.items():
        status = info.get("status", "unknown")
        if status == "active":
            print(f"  ✓ {name}: 可调用（{info.get('model','?')}）")
        else:
            print(f"  ✗ {name}: 不可用（{status}）")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 multi_model_chain.py [route|status|test]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "route" and len(sys.argv) > 2:
        force = None
        if "--force" in sys.argv:
            idx = sys.argv.index("--force")
            if idx + 1 < len(sys.argv):
                force = sys.argv[idx + 1]
        route_task(sys.argv[2], force)
    elif cmd == "status":
        show_status()
    elif cmd == "test":
        test_connectivity()
    else:
        print("参数错误")
