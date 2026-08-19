#!/usr/bin/env python3
"""
chain_fragment.py — 思考链路分片协议（模块2.1）

把一条完整推理链拆成N个「思考子任务」，每个子任务单独调用模型，
结果存入本地JSON（未来可接Redis），接力推进。
解决：单会话轮次限制、长思考链路中断、单模型上下文溢出。

用法：
  python3 chain_fragment.py start "你的深度问题"   # 启动一条新链路
  python3 chain_fragment.py continue <chain_id>     # 继续未完成的链路
  python3 chain_fragment.py status <chain_id>       # 查看链路状态
  python3 chain_fragment.py list                    # 列出所有链路
"""

import json
import time
import uuid
import sys
from pathlib import Path

CHAIN_DIR = Path(__file__).parent.parent / "data" / "chains"
CHAIN_DIR.mkdir(parents=True, exist_ok=True)


def create_chain(question, max_steps=10):
    """创建一条新的思考链路"""
    chain_id = str(uuid.uuid4())[:8]
    chain = {
        "chain_id": chain_id,
        "question": question,
        "max_steps": max_steps,
        "current_step": 0,
        "status": "created",  # created → running → completed → interrupted
        "steps": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    # 第一步：问题拆解
    chain["steps"].append({
        "step": 1,
        "type": "decompose",
        "prompt": f"请将以下问题拆解为3-5个关键子问题，按思考顺序排列：\n\n{question}",
        "result": None,
        "status": "pending",
    })
    save_chain(chain)
    print(f"[OK] 链路已创建: {chain_id}")
    print(f"     问题: {question[:50]}...")
    print(f"     最大步数: {max_steps}")
    return chain_id


def save_chain(chain):
    """保存链路状态"""
    chain["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path = CHAIN_DIR / f"{chain['chain_id']}.json"
    with open(path, "w") as f:
        json.dump(chain, f, indent=2, ensure_ascii=False)


def load_chain(chain_id):
    """加载链路状态"""
    path = CHAIN_DIR / f"{chain_id}.json"
    if not path.exists():
        print(f"[ERROR] 链路不存在: {chain_id}")
        return None
    with open(path, "r") as f:
        return json.load(f)


def execute_step(chain_id):
    """执行当前步骤（模拟模型调用，实际使用时接入引擎模型路由）"""
    chain = load_chain(chain_id)
    if not chain:
        return

    pending_steps = [s for s in chain["steps"] if s["status"] == "pending"]
    if not pending_steps:
        # 所有步骤完成，生成总结
        if chain["status"] != "completed":
            chain["status"] = "completed"
            chain["steps"].append({
                "step": len(chain["steps"]) + 1,
                "type": "summary",
                "prompt": "综合以上所有分析，给出最终结论",
                "result": "链路已完成，请查看各步骤结果",
                "status": "completed",
            })
            save_chain(chain)
            print(f"[OK] 链路 {chain_id} 已完成")
        return

    current = pending_steps[0]
    print(f"[执行] 步骤{current['step']} [{current['type']}]: {current['prompt'][:60]}...")

    # 模拟执行（实际接入时调用引擎的模型路由）
    current["result"] = f"[模拟结果] 步骤{current['step']}已执行，待接入真实模型路由"
    current["status"] = "completed"
    current["executed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    # 根据当前步骤类型生成下一步
    if current["type"] == "decompose":
        chain["steps"].append({
            "step": current["step"] + 1,
            "type": "analyze",
            "prompt": "针对拆解出的第一个子问题进行深度分析",
            "result": None,
            "status": "pending",
        })
    elif current["type"] == "analyze" and current["step"] < chain["max_steps"] - 1:
        chain["steps"].append({
            "step": current["step"] + 1,
            "type": "analyze",
            "prompt": "继续深入分析下一个子问题，注意与上一步结论的衔接",
            "result": None,
            "status": "pending",
        })

    chain["current_step"] = current["step"]
    chain["status"] = "running"
    save_chain(chain)
    print(f"[OK] 步骤{current['step']}完成")


def show_status(chain_id):
    """显示链路状态"""
    chain = load_chain(chain_id)
    if not chain:
        return
    print(f"=== 链路 {chain_id} ===")
    print(f"问题: {chain['question']}")
    print(f"状态: {chain['status']}")
    print(f"当前步骤: {chain['current_step']}/{chain['max_steps']}")
    print(f"创建时间: {chain['created_at']}")
    print(f"\n步骤明细:")
    for s in chain["steps"]:
        icon = "✓" if s["status"] == "completed" else "○"
        print(f"  {icon} 步骤{s['step']} [{s['type']}]: {s['prompt'][:40]}...")


def list_chains():
    """列出所有链路"""
    chains = sorted(CHAIN_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"=== 思考链路列表（共{len(chains)}条）===")
    for c in chains[:10]:
        with open(c, "r") as f:
            data = json.load(f)
        print(f"  [{data['status']}] {data['chain_id']} | 步骤{data['current_step']}/{data['max_steps']} | {data['question'][:40]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 chain_fragment.py [start|continue|status|list] [参数]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start" and len(sys.argv) > 2:
        create_chain(sys.argv[2])
    elif cmd == "continue" and len(sys.argv) > 2:
        execute_step(sys.argv[2])
    elif cmd == "status" and len(sys.argv) > 2:
        show_status(sys.argv[2])
    elif cmd == "list":
        list_chains()
    else:
        print("参数错误")
