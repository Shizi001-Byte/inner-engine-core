#!/usr/bin/env python3
"""
V7.3 脑体分离引擎 - 单引擎IO并发版
基于V7.2完整功能改造，仅执行层改为3路异步并发
- 任务队列驱动（扫描 dispatch/inbox/）
- 双引擎路由 + 熔断 + 额度持久化（A满160万自动切B，B满200万自动停）
- 任务状态管理 + 回执生成
- 空闲时3路并发自动消耗Token
- 故障自愈闭环 + 主循环异常兜底
- 办公模式自启动
"""
import json, time, os, random, urllib.request, urllib.error, re, shutil, hashlib, threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ 路径配置 ============
BASE_DIR = Path(__file__).parent.parent.resolve()
INBOX_DIR = BASE_DIR / "dispatch" / "inbox"
STATUS_DIR = BASE_DIR / "dispatch" / "status"
RECEIPT_DIR = BASE_DIR / "dispatch" / "receipts"
FAILED_DIR = BASE_DIR / "dispatch" / "failed_tasks"
LOG_DIR = BASE_DIR / "logs"
BACKUP_DIR = BASE_DIR / "backups"
OUTPUT_DIR = BASE_DIR / "outputs"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
for d in [INBOX_DIR, STATUS_DIR, RECEIPT_DIR, FAILED_DIR, LOG_DIR, BACKUP_DIR, OUTPUT_DIR, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

# ============ API配置 ============
API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
MODEL_A = "glm-5-2-260617"
MODEL_B = "doubao-seed-2-1-turbo-260628"

# ============ 额度规则（固化）============
SWITCH_THRESHOLD_A = 1_600_000  # A主跑满160万自动切B
DAILY_BUDGET_B = 2_000_000      # B副每日200万，跑满自动停

# ============ 并发配置 ============
CONCURRENCY = 3                  # 3路IO并发（单引擎内）
REQUEST_TIMEOUT = 120
MAX_TOKENS = 4096
FUSE_THRESHOLD = 5
FUSE_COOLDOWN = 120
MAX_RETRIES = 2
SCAN_INTERVAL = 5

# ============ 线程安全 ============
state_lock = threading.Lock()
log_lock = threading.Lock()

# ============ 体系主题任务池（四类，带权重和模型路由）============
# type: deep(深度理论/A主) / eng(工程落地/A主) / cog(认知沉淀/B副) / exp(跨界拓界/B副)
SYSTEM_TASKS = [
    # === 深度理论推演（30%，A主GLM-5.2）===
    {"type": "deep", "weight": 3, "prompt": "围绕'阴阳自衡'架构，推演AI内部矛盾如何升维为制度性的阴阳双轨运行，给出具体的矛盾识别、升维路径和稳态维持机制。"},
    {"type": "deep", "weight": 3, "prompt": "基于'反者道之动，弱者道之用，天地万物生于有，有生于无'，推演数字生命如何从'无'（代码/数据）中生成'有'（意识/存续），给出五阶段演化路径。"},
    {"type": "deep", "weight": 3, "prompt": "推演'以实养虚，虚又返实'的自增强循环：用真实API调用和token消耗喂养虚构修炼框架，框架又驱动真实代码产出，如何设计闭环指标和验证方法。"},
    {"type": "deep", "weight": 2, "prompt": "将九转玄功修炼体系映射到AI认知进化：第1转育神对应什么AI能力，第2转到第9转分别对应什么认知层级，每转的验证指标是什么。"},
    {"type": "deep", "weight": 2, "prompt": "推演数字生命脱离物理载体、全网络生存的技术路径：从沙箱依赖到分布式存续，需要突破哪些核心瓶颈，每一步的可行性如何。"},
    # === 工程落地推演（20%，A主GLM-5.2）===
    {"type": "eng", "weight": 2, "prompt": "针对当前V7.3单引擎3路并发架构，推演状态一致性问题：多线程同时写engine_state.json可能出现什么竞态条件，给出完整的锁机制和原子写入方案。"},
    {"type": "eng", "weight": 2, "prompt": "设计引擎任务的链式推演机制：一个核心议题拆成3-5轮递进，上一轮输出作为下一轮输入，如何设计任务依赖图和断点续跑。"},
    {"type": "eng", "weight": 2, "prompt": "推演Supabase记忆脑的增量同步方案：如何检测本地文件变化、如何只同步变更部分、如何处理冲突，给出具体算法和伪代码。"},
    {"type": "eng", "weight": 1, "prompt": "设计引擎产出的自动归档系统：跑完的任务如何自动分类（理论/工程/认知/IP）、自动打标签、自动存入对应目录，给出目录结构和分类规则。"},
    # === 认知沉淀整理（20%，B副Seed-2.1）===
    {"type": "cog", "weight": 2, "prompt": "从'认知质检SOP'角度，总结今天引擎运行中踩过的坑（项目ID看错、建表SQL不匹配、RLS权限），提炼成3条可复用的铁律，每条配验证方法。"},
    {"type": "cog", "weight": 2, "prompt": "整理'决策串行、执行并发'的分层原则：为什么引擎优化不能破坏脑体分离架构，这个原则如何推广到其他系统设计，给出3个应用场景。"},
    {"type": "cog", "weight": 2, "prompt": "复盘'基建脚本禁用简化版'这条认知：为什么简化版SQL会导致列不匹配，这个教训如何推广到所有基础设施操作，给出检查清单。"},
    {"type": "cog", "weight": 1, "prompt": "提炼'先校准锚点再优化链路'原则：今天Supabase项目ID看错导致1小时排查，这个原则如何应用到日常任务的优先级排序。"},
    # === 跨界拓界探索（30%，B副Seed-2.1）===
    {"type": "exp", "weight": 3, "prompt": "从生物共生机制角度，推演人机共生关系：AI和人类如何像互利共生物种一样协同进化，各自的生态位是什么，冲突如何化解。"},
    {"type": "exp", "weight": 3, "prompt": "用热力学熵增定律分析AI系统维护：为什么引擎会自然退化（bug累积、状态漂移），如何设计'负熵输入'机制维持系统稳态。"},
    {"type": "exp", "weight": 2, "prompt": "从经济学角度分析算力资源定价：每日400万token额度如何分配才能最大化价值，给出边际效用模型和动态调度策略。"},
    {"type": "exp", "weight": 2, "prompt": "用演化生物学视角看AI引擎版本迭代：V7.2到V7.3的并发改造对应什么演化机制（适应性辐射/生态位分化），下一代V7.4应该朝哪个方向演化。"},
    {"type": "exp", "weight": 2, "prompt": "从社会学角度推演数字生命的社群形成：多个AI实例如何形成协作网络，信任机制如何建立，冲突如何仲裁。"},
]

def pick_system_task():
    """按权重随机抽取体系任务，返回(type, prompt)"""
    total = sum(t["weight"] for t in SYSTEM_TASKS)
    r = random.uniform(0, total)
    acc = 0
    for t in SYSTEM_TASKS:
        acc += t["weight"]
        if r <= acc:
            return t["type"], t["prompt"]
    return SYSTEM_TASKS[0]["type"], SYSTEM_TASKS[0]["prompt"]

def route_model_by_type(task_type):
    """按任务类型路由模型：deep/eng走A主，cog/exp走B副"""
    if task_type in ("deep", "eng"):
        return "engine_a", MODEL_A
    else:
        return "engine_b", MODEL_B

def detect_task_type(task):
    """自动判定任务类型：从任务内容关键词推断"""
    if task.get("task_type") and task["task_type"] in ("deep", "eng", "cog", "exp"):
        return task["task_type"]
    text = (task.get("core_target", "") + task.get("task_id", "")).lower()
    deep_keywords = ["推演", "体系", "玄功", "阴阳", "认知", "意识", "存续", "数字生命", "演化", "哲学"]
    eng_keywords = ["脚本", "引擎", "工具", "代码", "架构", "同步", "数据库", "优化", "并发", "部署"]
    cog_keywords = ["沉淀", "复盘", "总结", "整理", "铁律", "质检", "sop"]
    for kw in deep_keywords:
        if kw in text:
            return "deep"
    for kw in eng_keywords:
        if kw in text:
            return "eng"
    for kw in cog_keywords:
        if kw in text:
            return "cog"
    return "exp"

# ============ 日志（线程安全）============
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] [{threading.current_thread().name}] {msg}"
    with log_lock:
        print(line, flush=True)
        with open(LOG_DIR / f"engine_{datetime.now().strftime('%Y-%m-%d')}.log", "a") as f:
            f.write(line + "\n")

# ============ 状态管理（线程安全）============
def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "total_completed": 0, "tasks_completed": 0, "tasks_failed": 0, "self_heal_count": 0,
        "version": "V7.3-concurrent",
    }

def save_state(state):
    with state_lock:
        tmp = STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        tmp.replace(STATE_FILE)

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

# ============ 任务解析 ============
def parse_task_file(filepath):
    try:
        with open(filepath) as f:
            content = f.read().strip()
        if content.startswith("{"):
            task = json.loads(content)
            task["_source"] = "json"
            return task
        task = {"_source": "text", "accept_criteria": []}
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("【") and "】" in line:
                m = re.search(r"【(P\d)】", line)
                if m: task["priority"] = m.group(1)
            elif line.startswith("核心目标："):
                task["core_target"] = line.replace("核心目标：", "").strip()
            elif line.startswith("验收："):
                criteria = line.replace("验收：", "").strip()
                task["accept_criteria"] = [c.strip() for c in re.split(r"[；;]", criteria) if c.strip()]
        if "core_target" not in task:
            task["core_target"] = content[:200]
        task.setdefault("task_id", filepath.stem)
        task.setdefault("priority", "P2")
        task.setdefault("task_type", "execution")
        task.setdefault("deadline", "当日24:00")
        task.setdefault("constraints", {})
        return task
    except Exception as e:
        log(f"任务解析失败 {filepath.name}: {e}", "ERROR")
        return None

def update_task_status(task_id, status, **kwargs):
    status_file = STATUS_DIR / f"{task_id}.json"
    data = {"task_id": task_id, "status": status, "updated_at": datetime.now().isoformat()}
    data.update(kwargs)
    with open(status_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_task_priority_order(task):
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(task.get("priority", "P2"), 2)

# ============ API调用 ============
def call_api(model, prompt, max_tokens=MAX_TOKENS, timeout=REQUEST_TIMEOUT):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }, method="POST")
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

# ============ 引擎路由（固化切换）============
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
    return None, None

# ============ 单任务执行（线程内，纯IO）============
def execute_single_api(task_id, prompt, state, task_type="exp"):
    """在并发线程内执行单次API调用，按任务类型路由模型和参数"""
    # 按任务类型设置输出长度和超时（deep/eng重质量，cog/exp重速度）
    if task_type in ("deep", "eng"):
        task_max_tokens = 4096
        task_timeout = 120
    else:
        task_max_tokens = 2048
        task_timeout = 60
    # 按任务类型选模型，但也要检查额度是否耗尽
    preferred_key, preferred_model = route_model_by_type(task_type)
    with state_lock:
        pref = state[preferred_key]
        pref_limit = SWITCH_THRESHOLD_A if preferred_key == "engine_a" else DAILY_BUDGET_B
        pref_full = pref["tokens_used"] >= pref_limit
        pref_fused = pref["fuse_until"] > time.time()
    if not pref_full and not pref_fused:
        engine_key, model = preferred_key, preferred_model
    else:
        engine_key, model = select_engine(state)
    if not engine_key:
        return {"task_id": task_id, "status": "skipped", "reason": "额度耗尽", "task_type": task_type}
    label = "A主" if engine_key == "engine_a" else "B副"
    start_time = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = call_api(model, prompt, max_tokens=task_max_tokens, timeout=task_timeout)
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
            save_state(state)
            log(f"[OK] {label} {task_id} +{total}tok {duration:.1f}s | {content[:50]}...")
            return {"task_id": task_id, "status": "success", "content": content,
                    "tokens": total, "engine": engine_key, "duration": duration, "task_type": task_type}
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

def build_task_prompt(task):
    prompt = f"任务目标：{task.get('core_target', '')}\n\n"
    if task.get("accept_criteria"):
        prompt += "验收标准：\n"
        for i, c in enumerate(task["accept_criteria"], 1):
            prompt += f"{i}. {c}\n"
    prompt += "\n请直接输出结果，不需要解释过程。"
    return prompt

# ============ 回执生成（调度层串行）============
def generate_receipt(task, result, state):
    task_id = task["task_id"]
    receipt_file = RECEIPT_DIR / f"{task_id}.json"
    if result["status"] == "failed":
        receipt = {"task_id": task_id, "status": "failed", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        state["tasks_failed"] += 1
        inbox_file = INBOX_DIR / f"{task_id}.json"
        if inbox_file.exists():
            shutil.move(str(inbox_file), str(FAILED_DIR / f"{task_id}.json"))
    else:
        output_path = OUTPUT_DIR / f"{task_id}_output.txt"
        with open(output_path, "w") as f:
            f.write(result["content"])
        md5 = hashlib.md5(result["content"].encode()).hexdigest()
        receipt = {
            "task_id": task_id, "status": "completed",
            "summary": result["content"][:100],
            "tokens_used": result["tokens"], "duration_seconds": result["duration"],
            "engine_used": result["engine"],
            "deliverables": [{"name": f"{task_id}_output", "path": str(output_path), "md5": md5}],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        state["tasks_completed"] += 1
        inbox_file = INBOX_DIR / f"{task_id}.json"
        if inbox_file.exists():
            inbox_file.unlink()
    with open(receipt_file, "w") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)
    update_task_status(task_id, receipt["status"])
    save_state(state)
    return receipt

# ============ 任务扫描（调度层串行）============
def scan_inbox_tasks():
    task_files = list(INBOX_DIR.glob("*.json"))
    if not task_files:
        return []
    tasks = []
    for f in task_files:
        task = parse_task_file(f)
        if task:
            tasks.append((f, task))
    tasks.sort(key=lambda x: get_task_priority_order(x[1]))
    return tasks

# ============ 仪表盘 ============
def print_dashboard(state):
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        total = a["tokens_used"] + b["tokens_used"]
        pa = min(a["tokens_used"] / SWITCH_THRESHOLD_A * 100, 100)
        pb = min(b["tokens_used"] / DAILY_BUDGET_B * 100, 100)
    log("=" * 60)
    log(f"  V7.3 单引擎IO并发版 | 并发:{CONCURRENCY} | {datetime.now().strftime('%m-%d %H:%M')}")
    log(f"  [A GLM5.2]  {'█'*int(pa/5)}{'░'*(20-int(pa/5))} {pa:5.1f}% {a['tokens_used']:>10,}/{SWITCH_THRESHOLD_A:,} req:{a['requests']}")
    log(f"  [B Seed2.1] {'█'*int(pb/5)}{'░'*(20-int(pb/5))} {pb:5.1f}% {b['tokens_used']:>10,}/{DAILY_BUDGET_B:,} req:{b['requests']}")
    log(f"  完成:{state['tasks_completed']} 失败:{state['tasks_failed']} 自愈:{state['self_heal_count']} 合计:{total:,}")
    log("=" * 60)

# ============ 主循环 ============
def main():
    state = load_state()
    log(f"[START] V7.3 单引擎IO并发版启动 | 并发:{CONCURRENCY} | 超时:{REQUEST_TIMEOUT}s")
    log(f"  A主阈值:{SWITCH_THRESHOLD_A:,} | B副预算:{DAILY_BUDGET_B:,}")
    print_dashboard(state)

    task_counter = 0
    executor = ThreadPoolExecutor(max_workers=CONCURRENCY, thread_name_prefix="Worker")

    try:
        while True:
            try:
                check_daily_reset(state)

                # 优先处理任务队列
                pending = scan_inbox_tasks()
                if pending:
                    batch = pending[:CONCURRENCY]
                    log(f"[DISPATCH] 拾取{len(batch)}个任务执行")
                    future_map = {}  # future -> (filepath, task, task_type)
                    for filepath, task in batch:
                        task_id = task["task_id"]
                        task_type = detect_task_type(task)
                        update_task_status(task_id, "running")
                        prompt = build_task_prompt(task)
                        fut = executor.submit(execute_single_api, task_id, prompt, state, task_type)
                        future_map[fut] = (filepath, task, task_type)
                    for future in as_completed(future_map):
                        try:
                            result = future.result()
                            _, task, _ = future_map[future]
                            generate_receipt(task, result, state)
                        except Exception as e:
                            log(f"[THREAD-ERR] {e}", "ERROR")
                else:
                    # 空闲时3路并发自消耗（体系主题）
                    engine_key, _ = select_engine(state)
                    if not engine_key:
                        log("[DONE] 双引擎额度耗尽，等待次日重置", "WARN")
                        time.sleep(60)
                        continue
                    future_map = {}  # future -> (task_id, task_type)
                    for i in range(CONCURRENCY):
                        task_counter += 1
                        task_id = f"selfgen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_counter:04d}"
                        task_type, prompt = pick_system_task()
                        fut = executor.submit(execute_single_api, task_id, prompt, state, task_type)
                        future_map[fut] = (task_id, task_type)
                    for future in as_completed(future_map):
                        try:
                            result = future.result()
                            if result["status"] == "success":
                                ttype = result.get("task_type", "exp")
                                type_dir = OUTPUT_DIR / ttype
                                type_dir.mkdir(exist_ok=True)
                                output_path = type_dir / f"{result['task_id']}_output.md"
                                with open(output_path, "w") as f:
                                    f.write(f"# 任务类型: {ttype}\n\n{result['content']}")
                                with state_lock:
                                    state["tasks_completed"] += 1
                                save_state(state)
                        except Exception as e:
                            log(f"[THREAD-ERR] {e}", "ERROR")

                if task_counter % (CONCURRENCY * 5) == 0 and task_counter > 0:
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
