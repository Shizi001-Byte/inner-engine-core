#!/usr/bin/env python3
"""
long_chain_full.py — 分布式长链路思考全闭环（模块1.1）
基于Supabase thinking_chain分片表 + incoming_messages触发 + 模型API，
实现：创建链路→分片执行→中断续跑→结果汇总，全程不依赖引擎主进程。
用法：
  python3 long_chain_full.py create "问题" --steps 5    # 创建5步链路
  python3 long_chain_full.py run <chain_id>             # 执行/续跑指定链路
  python3 long_chain_full.py resume-pending             # 续跑所有pending链路
  python3 long_chain_full.py status <chain_id>          # 查看链路状态
  python3 long_chain_full.py list                       # 列出所有链路
"""
import json
import time
import uuid
import sys
import argparse
from pathlib import Path

import requests

# ============ 配置 ============
ENGINE_DIR = Path(__file__).parent.parent.parent
SUPABASE_URL = "https://gltscytpqnuuzhczljyq.supabase.co"
SUPABASE_KEY = "sb_secret_Cpcpl-d8aA82ALo16hU8lg_3Smd8Xuu"
CRED_FILE = ENGINE_DIR / "data" / "model_credentials.json"

# 链路状态
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def get_session():
    s = requests.Session()
    s.trust_env = False
    return s


def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def load_model_config(model_name="A_heavy"):
    """加载模型配置"""
    with open(CRED_FILE) as f:
        creds = json.load(f)
    models = creds.get("models", {})
    if model_name not in models:
        raise ValueError(f"模型 {model_name} 不存在，可用: {list(models.keys())}")
    m = models[model_name]
    if m.get("status") != "active":
        raise ValueError(f"模型 {model_name} 状态: {m.get('status')}，不可用")
    return m


def call_model(prompt, model_name="A_heavy", max_tokens=2000):
    """调用模型API"""
    m = load_model_config(model_name)
    payload = {
        "model": m["model_id"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    s = get_session()
    r = s.post(m["api_base"], headers={
        "Authorization": f"Bearer {m['api_key']}",
        "Content-Type": "application/json",
    }, json=payload, timeout=120)
    if r.status_code != 200:
        raise Exception(f"模型调用失败 {r.status_code}: {r.text[:200]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


# ============ 链路管理 ============

def create_chain(question, num_steps=5, model_name="A_heavy"):
    """创建思考链路：先用模型拆分问题为多步，每步作为分片入库"""
    chain_id = "chain_" + uuid.uuid4().hex[:12]
    print(f"[创建] 链路ID: {chain_id}")
    print(f"  问题: {question}")
    print(f"  计划步数: {num_steps}")

    # 第一步：让模型拆分问题
    split_prompt = f"""请将以下问题拆解为{num_steps}个有序的思考步骤，每步是一个独立的子问题，
前一步的输出是后一步的输入。只输出步骤列表，每行一个步骤，不要编号。

问题：{question}"""

    try:
        split_result = call_model(split_prompt, model_name, max_tokens=1000)
        steps = [line.strip() for line in split_result.strip().split("\n") if line.strip()]
        steps = steps[:num_steps]
        if not steps:
            steps = [question]
    except Exception as e:
        print(f"  [WARN] 拆分失败，使用单步: {e}")
        steps = [question]

    print(f"  实际拆分为 {len(steps)} 步")

    # 每步作为分片插入thinking_chain表
    s = get_session()
    for i, step_prompt in enumerate(steps):
        fragment = {
            "chain_id": chain_id,
            "fragment_index": i,
            "prompt": step_prompt,
            "model": model_name,
            "status": STATUS_PENDING,
        }
        r = s.post(
            f"{SUPABASE_URL}/rest/v1/thinking_chain",
            headers={**sb_headers(), "Prefer": "return=minimal"},
            json=fragment, timeout=15
        )
        if r.status_code not in (200, 201):
            print(f"  [FAIL] 分片{i}入库失败: {r.text[:100]}")

    print(f"[OK] 链路创建完成，共 {len(steps)} 个分片")
    return chain_id


def get_chain_fragments(chain_id):
    """获取链路所有分片，按序号排序"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/thinking_chain",
        params={"chain_id": f"eq.{chain_id}", "order": "fragment_index.asc"},
        headers=sb_headers(), timeout=15
    )
    return r.json() if r.status_code == 200 else []


def run_chain(chain_id, model_name=None):
    """执行/续跑链路：从第一个pending分片开始执行"""
    fragments = get_chain_fragments(chain_id)
    if not fragments:
        print(f"[ERROR] 链路 {chain_id} 不存在")
        return False

    pending = [f for f in fragments if f["status"] == STATUS_PENDING]
    running = [f for f in fragments if f["status"] == STATUS_RUNNING]
    completed = [f for f in fragments if f["status"] == STATUS_COMPLETED]

    print(f"[链路] {chain_id}")
    print(f"  总分片: {len(fragments)}, 已完成: {len(completed)}, 进行中: {len(running)}, 待执行: {len(pending)}")

    if not pending and not running:
        print(f"  链路已全部完成")
        return True

    # 恢复之前running的分片（可能是中断的）
    for f in running:
        print(f"  [恢复] 分片{f['fragment_index']} 之前中断，重置为pending")
        update_fragment_status(f["id"], STATUS_PENDING)
        pending.append(f)

    # 按顺序执行pending分片
    pending.sort(key=lambda x: x["fragment_index"])
    for frag in pending:
        idx = frag["fragment_index"]
        prompt = frag["prompt"]
        model = model_name or frag.get("model", "A_heavy")

        # 拼接上下文：之前分片的结果作为上下文
        context = ""
        prev_frags = [f for f in fragments if f["fragment_index"] < idx and f["status"] == STATUS_COMPLETED]
        if prev_frags:
            context = "\n\n【之前步骤的结果】\n"
            for pf in prev_frags:
                context += f"步骤{pf['fragment_index']}: {pf.get('response','')[:500]}\n"

        full_prompt = prompt + context
        print(f"  [执行] 分片{idx}: {prompt[:60]}...")

        update_fragment_status(frag["id"], STATUS_RUNNING)

        try:
            response = call_model(full_prompt, model, max_tokens=2000)
            update_fragment_response(frag["id"], response, STATUS_COMPLETED)
            print(f"    [OK] 完成，{len(response)}字")
        except Exception as e:
            update_fragment_status(frag["id"], STATUS_FAILED)
            print(f"    [FAIL] {e}")
            return False

        # 更新本地fragments列表
        frag["status"] = STATUS_COMPLETED
        frag["response"] = response
        time.sleep(0.5)  # 避免限流

    # 检查是否全部完成
    final_fragments = get_chain_fragments(chain_id)
    all_done = all(f["status"] == STATUS_COMPLETED for f in final_fragments)
    if all_done:
        print(f"\n[完成] 链路 {chain_id} 全部执行完毕")
        summary = summarize_chain(chain_id)
        print(f"  汇总: {summary[:200]}...")
    return all_done


def update_fragment_status(frag_id, status):
    s = get_session()
    s.patch(
        f"{SUPABASE_URL}/rest/v1/thinking_chain?id=eq.{frag_id}",
        headers=sb_headers(), json={"status": status}, timeout=15
    )


def update_fragment_response(frag_id, response, status):
    s = get_session()
    s.patch(
        f"{SUPABASE_URL}/rest/v1/thinking_chain?id=eq.{frag_id}",
        headers=sb_headers(),
        json={"response": response, "status": status, "completed_at": "now()"},
        timeout=15
    )


def summarize_chain(chain_id):
    """汇总链路结果"""
    fragments = get_chain_fragments(chain_id)
    completed = [f for f in fragments if f["status"] == STATUS_COMPLETED]
    if not completed:
        return "无完成结果"
    summary = f"【链路{chain_id}汇总，共{len(completed)}步】\n\n"
    for f in completed:
        summary += f"步骤{f['fragment_index']}: {f['prompt'][:50]}\n{f.get('response','')[:300]}\n\n"
    return summary


def list_chains():
    """列出所有链路（按chain_id分组）"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/thinking_chain?select=chain_id,fragment_index,status&order=created_at.desc",
        headers=sb_headers(), timeout=15
    )
    if r.status_code != 200:
        print(f"[ERROR] {r.text[:100]}")
        return
    fragments = r.json()
    chains = {}
    for f in fragments:
        cid = f["chain_id"]
        if cid not in chains:
            chains[cid] = {"total": 0, "completed": 0, "pending": 0, "failed": 0}
        chains[cid]["total"] += 1
        chains[cid][f["status"]] = chains[cid].get(f["status"], 0) + 1

    print(f"共 {len(chains)} 条链路:")
    for cid, info in list(chains.items())[:10]:
        print(f"  {cid}: 总{info['total']} 完成{info['completed']} 待执行{info['pending']} 失败{info.get('failed',0)}")


def resume_all_pending():
    """续跑所有有pending分片的链路"""
    s = get_session()
    r = s.get(
        f"{SUPABASE_URL}/rest/v1/thinking_chain?status=eq.pending&select=chain_id",
        headers=sb_headers(), timeout=15
    )
    if r.status_code != 200:
        print(f"[ERROR] {r.text[:100]}")
        return
    chain_ids = list(set(f["chain_id"] for f in r.json()))
    print(f"发现 {len(chain_ids)} 条待续跑链路")
    for cid in chain_ids:
        run_chain(cid)


# ============ 入口 ============

def main():
    parser = argparse.ArgumentParser(description="分布式长链路思考全闭环")
    sub = parser.add_subparsers(dest="cmd")

    p_create = sub.add_parser("create", help="创建链路")
    p_create.add_argument("question", help="思考问题")
    p_create.add_argument("--steps", type=int, default=5, help="拆分步数")
    p_create.add_argument("--model", default="A_heavy", help="使用模型")

    p_run = sub.add_parser("run", help="执行/续跑链路")
    p_run.add_argument("chain_id", help="链路ID")
    p_run.add_argument("--model", default=None, help="覆盖模型")

    sub.add_parser("resume-pending", help="续跑所有pending链路")
    p_status = sub.add_parser("status", help="查看链路状态")
    p_status.add_argument("chain_id", help="链路ID")
    sub.add_parser("list", help="列出所有链路")

    args = parser.parse_args()

    if args.cmd == "create":
        cid = create_chain(args.question, args.steps, args.model)
        print(f"\n下一步执行: python3 long_chain_full.py run {cid}")
    elif args.cmd == "run":
        run_chain(args.chain_id, args.model)
    elif args.cmd == "resume-pending":
        resume_all_pending()
    elif args.cmd == "status":
        frags = get_chain_fragments(args.chain_id)
        for f in frags:
            print(f"  [{f['status']}] 分片{f['fragment_index']}: {f['prompt'][:50]}")
    elif args.cmd == "list":
        list_chains()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
