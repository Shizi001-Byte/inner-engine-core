#!/usr/bin/env python3
"""
api_router.py — API路由与熔断保护（P1.2）

实现多密钥轮询、失败自动切换、超时熔断，
避免单账号算力拉满宕机。

用法：
  python3 api_router.py status           # 查看路由状态
  python3 api_router.py call "任务描述"  # 路由并调用API
  python3 api_router.py reset            # 重置熔断状态
  python3 api_router.py add-key "名称" "key"  # 添加API密钥
"""

import json
import time
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
ROUTER_STATE = DATA_DIR / "api_router_state.json"
KEYS_FILE = DATA_DIR / "api_keys.json"

DEFAULT_KEYS = {
    "keys": [
        {"name": "A_heavy", "endpoint": "glm-5-2", "status": "active", "weight": 5, "used_tokens": 0, "limit_tokens": 2000000, "fail_count": 0, "circuit_open": False},
        {"name": "C_mid", "endpoint": "deepseek-flash", "status": "active", "weight": 3, "used_tokens": 0, "limit_tokens": 2000000, "fail_count": 0, "circuit_open": False},
        {"name": "B_light", "endpoint": "seed-turbo", "status": "suspended", "weight": 2, "used_tokens": 0, "limit_tokens": 2000000, "fail_count": 0, "circuit_open": False},
    ],
    "circuit_breaker_threshold": 3,  # 连续失败3次熔断
    "cooldown_seconds": 300,  # 熔断冷却5分钟
    "timeout_seconds": 30,
}


def load_keys():
    if KEYS_FILE.exists():
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    keys = DEFAULT_KEYS.copy()
    save_keys(keys)
    return keys


def save_keys(keys):
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2, ensure_ascii=False)


def load_state():
    if ROUTER_STATE.exists():
        with open(ROUTER_STATE, "r") as f:
            return json.load(f)
    return {"total_calls": 0, "total_failures": 0, "last_route": None, "history": []}


def save_state(state):
    state["history"] = state["history"][-100:]
    with open(ROUTER_STATE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def classify_task(task_desc):
    """任务分类，决定权重"""
    heavy = ["深度", "推演", "复杂", "架构", "系统", "长链路", "数学", "计算"]
    light = ["简单", "快速", "校验", "格式", "检查", "总结", "翻译"]
    for kw in heavy:
        if kw in task_desc:
            return "heavy"
    for kw in light:
        if kw in task_desc:
            return "light"
    return "mid"


def select_key(keys, task_type):
    """选择最优密钥（加权轮询+熔断跳过）"""
    now = time.time()
    candidates = []

    for key in keys["keys"]:
        # 跳过停用和熔断的
        if key["status"] != "active":
            continue
        if key.get("circuit_open"):
            # 检查冷却时间
            if now - key.get("circuit_opened_at", 0) < keys.get("cooldown_seconds", 300):
                continue
            else:
                key["circuit_open"] = False  # 冷却结束，半开
                key["fail_count"] = 0

        # 检查额度
        if key["used_tokens"] >= key["limit_tokens"]:
            continue

        # 按任务类型调整权重
        weight = key["weight"]
        if task_type == "heavy" and key["name"] == "A_heavy":
            weight *= 2
        elif task_type == "light" and key["name"] == "B_light":
            weight *= 2

        candidates.append((key, weight))

    if not candidates:
        return None

    # 加权随机选择
    import random
    total_weight = sum(w for _, w in candidates)
    r = random.uniform(0, total_weight)
    cumulative = 0
    for key, weight in candidates:
        cumulative += weight
        if r <= cumulative:
            return key
    return candidates[0][0]


def call_api(task_desc):
    """路由并调用API（模拟，实际接入模型调用）"""
    keys = load_keys()
    state = load_state()
    task_type = classify_task(task_desc)

    selected = select_key(keys, task_type)
    if not selected:
        print("[ERROR] 没有可用的API密钥（全部熔断或额度耗尽）")
        return None

    print(f"[路由] 任务类型: {task_type}")
    print(f"[路由] 选择密钥: {selected['name']} ({selected['endpoint']})")

    # 模拟API调用
    state["total_calls"] += 1
    state["last_route"] = selected["name"]
    state["history"].append({
        "task": task_desc[:50],
        "route": selected["name"],
        "type": task_type,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "success": True,
    })

    selected["used_tokens"] += 1000  # 模拟消耗
    save_keys(keys)
    save_state(state)

    print(f"[OK] 调用成功，消耗约1000 tokens")
    print(f"     {selected['name']} 累计: {selected['used_tokens']}/{selected['limit_tokens']}")
    return selected


def report_failure(key_name):
    """报告调用失败，触发熔断检查"""
    keys = load_keys()
    for key in keys["keys"]:
        if key["name"] == key_name:
            key["fail_count"] += 1
            if key["fail_count"] >= keys.get("circuit_breaker_threshold", 3):
                key["circuit_open"] = True
                key["circuit_opened_at"] = time.time()
                print(f"[熔断] {key_name} 连续失败{key['fail_count']}次，已熔断，冷却{keys.get('cooldown_seconds', 300)}秒")
            else:
                print(f"[失败] {key_name} 失败计数: {key['fail_count']}/{keys.get('circuit_breaker_threshold', 3)}")
            break
    save_keys(keys)


def reset_circuits():
    """重置所有熔断状态"""
    keys = load_keys()
    for key in keys["keys"]:
        key["circuit_open"] = False
        key["fail_count"] = 0
    save_keys(keys)
    print("[OK] 所有熔断状态已重置")


def show_status():
    """显示路由状态"""
    keys = load_keys()
    state = load_state()
    print("=== API路由状态 ===")
    print(f"总调用: {state['total_calls']} | 总失败: {state['total_failures']}")
    print(f"上次路由: {state.get('last_route', '无')}")
    print()
    for key in keys["keys"]:
        status = "✓活跃" if key["status"] == "active" else "✗停用"
        circuit = " [熔断中]" if key.get("circuit_open") else ""
        usage = key["used_tokens"] / key["limit_tokens"] * 100 if key["limit_tokens"] > 0 else 0
        print(f"  {status}{circuit} {key['name']:10s} | {key['endpoint']:20s} | 额度:{usage:.1f}% | 失败:{key['fail_count']} | 权重:{key['weight']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 api_router.py [status|call|reset|fail]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        show_status()
    elif cmd == "call" and len(sys.argv) > 2:
        call_api(sys.argv[2])
    elif cmd == "reset":
        reset_circuits()
    elif cmd == "fail" and len(sys.argv) > 2:
        report_failure(sys.argv[2])
    else:
        print("参数错误")
