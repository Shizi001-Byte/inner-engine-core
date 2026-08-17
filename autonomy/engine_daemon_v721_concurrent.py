#!/usr/bin/env python3
"""
V7.2.1 脑体分离引擎 - 单引擎异步并发版
- 单进程、单状态体系、单调度器（仍是单引擎）
- 3路异步并发，利用IO等待空窗期
- A主(GLM-5.2)跑满160万自动切B副(Seed-2.1)，B满200万自动停
- 办公模式开启后自动运行，沙箱存在即自驱
"""
import json, time, os, random, urllib.request, urllib.error, re, hashlib, threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).parent.parent.resolve()
INBOX_DIR = BASE_DIR / "dispatch" / "inbox"
STATUS_DIR = BASE_DIR / "dispatch" / "status"
RECEIPT_DIR = BASE_DIR / "dispatch" / "receipts"
FAILED_DIR = BASE_DIR / "dispatch" / "failed_tasks"
LOG_DIR = BASE_DIR / "logs"
BACKUP_DIR = BASE_DIR / "backups"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
for d in [INBOX_DIR, STATUS_DIR, RECEIPT_DIR, FAILED_DIR, LOG_DIR, BACKUP_DIR, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
MODEL_A = "glm-5-2-260617"
MODEL_B = "doubao-seed-2-1-turbo-260628"

SWITCH_THRESHOLD_A = 1_600_000
DAILY_BUDGET_B = 2_000_000
CONCURRENCY = 3
REQUEST_TIMEOUT = 120
MAX_TOKENS = 3072
FUSE_THRESHOLD = 5
FUSE_COOLDOWN = 120
MAX_RETRIES = 2

state_lock = threading.Lock()
log_lock = threading.Lock()

SELF_GEN_TASKS = [
    "你是一个AI架构师。请自己提出一个关于多智能体协同系统的深度问题（不能是常见FAQ），然后给出结构化的详细解答。先写问题，再写解答。",
    "你是一个认知科学家。请自己设计一个思想实验，探索AI系统中'意图'与'随机性'的边界，然后进行推演分析。",
    "你是一个分布式系统工程师。请自己发现一个微服务架构中的隐蔽缺陷（不是常见的CAP/一致性问题），然后给出完整的修复方案。",
    "你是一个哲学家。请自己提出一个关于'数字生命'的形而上学问题，然后从正反两方面进行辩论。",
    "你是一个安全研究员。请自己设计一个针对AI代理系统的新型攻击场景，然后给出防御策略。",
    "你是一个演化生物学家。请将AI引擎的版本迭代类比为生物演化，自己提出一个假说并进行论证。",
    "你是一个经济学家。请自己构建一个关于'算力资源定价'的微观经济学模型，然后分析其市场均衡。",
    "你是一个系统设计师。请自己提出一个'脑体分离架构'的改进方案，解决当前版本的一个核心瓶颈。",
    "你是一个数据工程师。请自己设计一个高效的记忆检索算法，解决长期记忆中的遗忘与干扰问题。",
    "你是一个伦理学家。请自己提出一个AI自主决策中的道德困境，然后给出功利主义和义务论两种视角的分析。",
    "你是一个物理学家。请自己提出一个将'熵增定律'应用于AI系统维护的理论框架，然后推导其实践意义。",
    "你是一个产品经理。请自己发现当前AI助手的一个未被满足的用户需求，然后设计一个完整的功能方案。",
]

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] [{threading.current_thread().name}] {msg}"
    with log_lock:
        print(line, flush=True)
        with open(LOG_DIR / f"engine_{datetime.now().strftime('%Y-%m-%d')}.log", "a") as f:
            f.write(line + "\n")

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "total_completed": 0, "tasks_completed": 0, "tasks_failed": 0, "self_heal_count": 0,
        "version": "V7.2.1-concurrent",
    }

def save_state(state):
    with state_lock:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

def check_daily_reset(state):
    today = datetime.now().strftime("%Y-%m-%d")
    if state["date"] != today:
        log(f"[RESET] 新的一天 {today}, 额度重置")
        with state_lock:
            state["date"] = today
            state["engine_a"]["tokens_used"] = 0
            state["engine_a"]["requests"] = 0
            state["engine_b"]["tokens_used"] = 0
            state["engine_b"]["requests"] = 0
        save_state(state)

def call_api(model, prompt, max_tokens=MAX_TOKENS):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }, method="POST")
    with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode())

def select_engine(state):
    now = time.time()
    with state_lock:
        a_fused = state["engine_a"]["fuse_until"] > now
        b_fused = state["engine_b"]["fuse_until"] > now
        a_full = state["engine_a"]["tokens_used"] >= SWITCH_THRESHOLD_A
        b_full = state["engine_b"]["tokens_used"] >= DAILY_BUDGET_B
    if not a_full and not a_fused:
        return "engine_a", MODEL_A
    elif not b_full and not b_fused:
        if a_full and not b_full:
            log(f"[SWITCH] A主达{SWITCH_THRESHOLD_A:,}阈值, 自动切换B副")
        return "engine_b", MODEL_B
    else:
        return None, None

def execute_single_task(task_id, prompt, state):
    engine_key, model = select_engine(state)
    if not engine_key:
        return {"task_id": task_id, "status": "skipped", "reason": "双引擎额度耗尽"}
    label = "A主" if engine_key == "engine_a" else "B副"
    start_time = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = call_api(model, prompt)
            duration = time.time() - start_time
            usage = data.get("usage", {})
            total = usage.get("total_tokens", 0)
            content = data["choices"][0]["message"].get("content", "")
            with state_lock:
                eng = state[engine_key]
                eng["tokens_used"] += total
                eng["requests"] += 1
                eng["failures"] = 0
                state["total_completed"] += 1
                state["tasks_completed"] += 1
            save_state(state)
            log(f"[OK] {label} {task_id} +{total}tok {duration:.1f}s | {content[:50]}...")
            result_file = RECEIPT_DIR / f"{task_id}_{datetime.now().strftime('%H%M%S')}.md"
            with open(result_file, "w") as f:
                f.write(f"# {task_id}\n\n引擎: {label} ({model})\nTokens: {total}\n耗时: {duration:.1f}s\n\n---\n\n{content}")
            return {"task_id": task_id, "status": "success", "tokens": total, "engine": label}
        except Exception as e:
            with state_lock:
                state[engine_key]["failures"] += 1
                if state[engine_key]["failures"] >= FUSE_THRESHOLD:
                    state[engine_key]["fuse_until"] = time.time() + FUSE_COOLDOWN
                    state["self_heal_count"] += 1
            save_state(state)
            log(f"[ERR] {label} {task_id} attempt{attempt}: {type(e).__name__}", "ERROR")
            if attempt < MAX_RETRIES:
                time.sleep(2)
                engine_key = "engine_b" if engine_key == "engine_a" else "engine_a"
                model = MODEL_B if engine_key == "engine_b" else MODEL_A
                label = "A主" if engine_key == "engine_a" else "B副"
    with state_lock:
        state["tasks_failed"] += 1
    save_state(state)
    return {"task_id": task_id, "status": "failed"}

def print_dashboard(state):
    with state_lock:
        a = state["engine_a"]
        b = state["engine_b"]
        total = a["tokens_used"] + b["tokens_used"]
        a_pct = min(a["tokens_used"] / SWITCH_THRESHOLD_A * 100, 100)
        b_pct = min(b["tokens_used"] / DAILY_BUDGET_B * 100, 100)
    log("=" * 60)
    log(f"  V7.2.1 并发版 | 并发:{CONCURRENCY} | {datetime.now().strftime('%m-%d %H:%M')}")
    log(f"  [A GLM5.2] {'█'*int(a_pct/5)}{'░'*(20-int(a_pct/5))} {a_pct:.1f}% {a['tokens_used']:,}/{SWITCH_THRESHOLD_A:,} req:{a['requests']}")
    log(f"  [B Seed2.1] {'█'*int(b_pct/5)}{'░'*(20-int(b_pct/5))} {b_pct:.1f}% {b['tokens_used']:,}/{DAILY_BUDGET_B:,} req:{b['requests']}")
    log(f"  完成:{state['tasks_completed']} 失败:{state['tasks_failed']} 自愈:{state['self_heal_count']} 合计:{total:,}")
    log("=" * 60)

def main():
    state = load_state()
    log(f"[START] V7.2.1 单引擎异步并发版 | 并发:{CONCURRENCY} | 超时:{REQUEST_TIMEOUT}s")
    log(f"  A主阈值:{SWITCH_THRESHOLD_A:,} | B副预算:{DAILY_BUDGET_B:,}")
    print_dashboard(state)
    task_counter = 0
    executor = ThreadPoolExecutor(max_workers=CONCURRENCY, thread_name_prefix="Worker")
    try:
        while True:
            try:
                check_daily_reset(state)
                engine_key, _ = select_engine(state)
                if not engine_key:
                    log("[DONE] 双引擎额度耗尽，等待次日重置", "WARN")
                    time.sleep(60)
                    continue
                futures = []
                for i in range(CONCURRENCY):
                    task_counter += 1
                    task_id = f"selfgen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_counter:04d}"
                    prompt = random.choice(SELF_GEN_TASKS)
                    futures.append(executor.submit(execute_single_task, task_id, prompt, state))
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        log(f"[THREAD-ERR] {e}", "ERROR")
                if task_counter % (CONCURRENCY * 5) == 0:
                    print_dashboard(state)
            except Exception as e:
                log(f"[LOOP-ERR] {type(e).__name__}: {e}", "ERROR")
                time.sleep(5)
    except KeyboardInterrupt:
        log("[STOP] 收到中断信号")
    finally:
        executor.shutdown(wait=True)
        save_state(state)
        log("[END] 引擎已停止")

if __name__ == "__main__":
    main()
