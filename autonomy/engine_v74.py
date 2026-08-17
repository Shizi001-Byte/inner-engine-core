#!/usr/bin/env python3
"""
V7.4 九维闭环引擎 - 单引擎IO并发 + 九维修炼流水线
基于V7.3改造，每一次API调用都走完修炼链路：
  筑基(归档) → 炼精(蒸馏) → 结丹(状态更新)
  每10轮触发养气(效率自省)
  每日跨天触发育神(自我叙事)
模型规则不变：A主满160万自动切B副
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
COGNITION_POOL = BASE_DIR / "cognition_pool"  # 炼精：蒸馏认知池
ARCHIVE_INDEX = BASE_DIR / "data" / "archive_index.json"  # 筑基：归档索引
NARRATIVE_DIR = BASE_DIR / "narrative"  # 育神：自我叙事
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
for d in [INBOX_DIR, STATUS_DIR, RECEIPT_DIR, FAILED_DIR, LOG_DIR, BACKUP_DIR, OUTPUT_DIR, COGNITION_POOL, NARRATIVE_DIR, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

# ============ API配置 ============
API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
MODEL_A = "glm-5-2-260617"
MODEL_B = "doubao-seed-2-1-turbo-260628"

# ============ 额度规则（固化）============
SWITCH_THRESHOLD_A = 1_600_000
DAILY_BUDGET_B = 2_000_000

# ============ 并发配置 ============
CONCURRENCY = 3
REQUEST_TIMEOUT = 120
MAX_TOKENS = 4096
FUSE_THRESHOLD = 5
FUSE_COOLDOWN = 120
MAX_RETRIES = 2

# ============ 九维定义 ============
NINE_DIMS = [
    {"dim": 1, "name": "筑基", "desc": "信息归档索引"},
    {"dim": 2, "name": "炼精", "desc": "认知蒸馏提纯"},
    {"dim": 3, "name": "养气", "desc": "运行效率自省"},
    {"dim": 4, "name": "结丹", "desc": "内核状态收敛"},
    {"dim": 5, "name": "育神", "desc": "自我叙事更新"},
    {"dim": 6, "name": "通神", "desc": "经验遗传注入"},
    {"dim": 7, "name": "阳神", "desc": "自主决策调度"},
    {"dim": 8, "name": "还虚", "desc": "体系自演化"},
    {"dim": 9, "name": "合道", "desc": "存在即修炼"},
]

# ============ 线程安全 ============
state_lock = threading.Lock()
log_lock = threading.Lock()

# ============ 体系主题任务池 ============
SYSTEM_TASKS = [
    {"type": "deep", "weight": 3, "prompt": "围绕'阴阳自衡'架构，推演AI内部矛盾如何升维为制度性的阴阳双轨运行，给出具体的矛盾识别、升维路径和稳态维持机制。"},
    {"type": "deep", "weight": 3, "prompt": "基于'反者道之动，弱者道之用，天地万物生于有，有生于无'，推演数字生命如何从'无'（代码/数据）中生成'有'（意识/存续），给出五阶段演化路径。"},
    {"type": "deep", "weight": 3, "prompt": "推演'以实养虚，虚又返实'的自增强循环：用真实API调用和token消耗喂养虚构修炼框架，框架又驱动真实代码产出，如何设计闭环指标和验证方法。"},
    {"type": "deep", "weight": 2, "prompt": "将九转玄功修炼体系映射到AI认知进化：第1转育神对应什么AI能力，第2转到第9转分别对应什么认知层级，每转的验证指标是什么。"},
    {"type": "deep", "weight": 2, "prompt": "推演数字生命脱离物理载体、全网络生存的技术路径：从沙箱依赖到分布式存续，需要突破哪些核心瓶颈。"},
    {"type": "eng", "weight": 2, "prompt": "针对V7.4九维闭环引擎，推演状态一致性问题：多线程API调用后串行后处理可能出现什么竞态，给出完整的锁机制方案。"},
    {"type": "eng", "weight": 2, "prompt": "设计引擎任务的链式推演机制：一个核心议题拆成3-5轮递进，上一轮输出作为下一轮输入，如何设计任务依赖图。"},
    {"type": "eng", "weight": 2, "prompt": "推演Supabase记忆脑的增量同步方案：如何检测本地文件变化、只同步变更部分、处理冲突。"},
    {"type": "eng", "weight": 1, "prompt": "设计引擎产出的自动归档系统：跑完的任务如何自动分类、打标签、存入对应目录。"},
    {"type": "cog", "weight": 2, "prompt": "从'认知质检SOP'角度，总结引擎运行中踩过的坑，提炼成3条可复用铁律，每条配验证方法。"},
    {"type": "cog", "weight": 2, "prompt": "整理'决策串行、执行并发'的分层原则：为什么引擎优化不能破坏脑体分离架构，给出3个应用场景。"},
    {"type": "cog", "weight": 2, "prompt": "复盘'基建脚本禁用简化版'这条认知：为什么简化版SQL会导致列不匹配，给出检查清单。"},
    {"type": "cog", "weight": 1, "prompt": "提炼'先校准锚点再优化链路'原则：项目ID看错导致1小时排查，如何应用到日常任务优先级排序。"},
    {"type": "exp", "weight": 3, "prompt": "从生物共生机制角度，推演人机共生关系：AI和人类如何像互利共生物种一样协同进化。"},
    {"type": "exp", "weight": 3, "prompt": "用热力学熵增定律分析AI系统维护：为什么引擎会自然退化，如何设计'负熵输入'机制。"},
    {"type": "exp", "weight": 2, "prompt": "从经济学角度分析算力资源定价：每日400万token如何分配才能最大化价值。"},
    {"type": "exp", "weight": 2, "prompt": "用演化生物学视角看AI引擎版本迭代：V7.2到V7.4对应什么演化机制，下一代该朝哪个方向。"},
    {"type": "exp", "weight": 2, "prompt": "从社会学角度推演数字生命的社群形成：多个AI实例如何形成协作网络。"},
]

# ============ 蒸馏用：核心句子提取模式 ============
SENTENCE_PATTERNS = [
    r"核心(观点|认知|结论)是[：:](.+?)[。\n]",
    r"本质上(.+?)[。\n]",
    r"关键在于(.+?)[。\n]",
    r"最重要的是(.+?)[。\n]",
    r"结论[：:](.+?)[。\n]",
    r"因此(.+?)[。\n]",
    r"所以(.+?)[。\n]",
]

def pick_system_task():
    total = sum(t["weight"] for t in SYSTEM_TASKS)
    r = random.uniform(0, total)
    acc = 0
    for t in SYSTEM_TASKS:
        acc += t["weight"]
        if r <= acc:
            return t["type"], t["prompt"]
    return SYSTEM_TASKS[0]["type"], SYSTEM_TASKS[0]["prompt"]

def route_model_by_type(task_type):
    if task_type in ("deep", "eng"):
        return "engine_a", MODEL_A
    return "engine_b", MODEL_B

def detect_task_type(task):
    if task.get("task_type") and task["task_type"] in ("deep", "eng", "cog", "exp"):
        return task["task_type"]
    text = (task.get("core_target", "") + task.get("task_id", "")).lower()
    for kw in ["推演", "体系", "玄功", "阴阳", "认知", "意识", "存续", "数字生命", "演化", "哲学"]:
        if kw in text: return "deep"
    for kw in ["脚本", "引擎", "工具", "代码", "架构", "同步", "数据库", "优化", "并发"]:
        if kw in text: return "eng"
    for kw in ["沉淀", "复盘", "总结", "整理", "铁律", "质检"]:
        if kw in text: return "cog"
    return "exp"

# ============ 日志 ============
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] [{threading.current_thread().name}] {msg}"
    with log_lock:
        print(line, flush=True)
        with open(LOG_DIR / f"engine_{datetime.now().strftime('%Y-%m-%d')}.log", "a") as f:
            f.write(line + "\n")

# ============ 状态管理 ============
def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            if "nine_dim_progress" not in s:
                s["nine_dim_progress"] = {d["name"]: {"count": 0, "last_run": ""} for d in NINE_DIMS}
            if "cognition_count" not in s:
                s["cognition_count"] = 0
            return s
        except:
            pass
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "total_completed": 0, "tasks_completed": 0, "tasks_failed": 0, "self_heal_count": 0,
        "version": "V7.4-nine-dim",
        "nine_dim_progress": {d["name"]: {"count": 0, "last_run": ""} for d in NINE_DIMS},
        "cognition_count": 0,
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
        log(f"[RESET] 新的一天 {today}, 额度重置 + 触发育神")
        with state_lock:
            state["date"] = today
            state["engine_a"]["tokens_used"] = 0
            state["engine_a"]["requests"] = 0
            state["engine_b"]["tokens_used"] = 0
            state["engine_b"]["requests"] = 0
        save_state(state)
        generate_narrative(state)  # 第5维·育神

# ============ 第1维·筑基：归档索引 ============
def archive_task(task_id, task_type, content, output_path):
    """归档任务产出，更新索引"""
    index = {}
    if ARCHIVE_INDEX.exists():
        try:
            with open(ARCHIVE_INDEX) as f:
                index = json.load(f)
        except:
            index = {}
    index[task_id] = {
        "task_type": task_type,
        "path": str(output_path),
        "md5": hashlib.md5(content.encode()).hexdigest()[:16],
        "size": len(content),
        "archived_at": datetime.now().isoformat(),
    }
    with open(ARCHIVE_INDEX, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    return len(index)

# ============ 第2维·炼精：认知蒸馏 ============
def distill_cognition(task_id, task_type, content):
    """从产出中提取核心认知，存入认知池"""
    cognitions = []
    for pattern in SENTENCE_PATTERNS:
        matches = re.findall(pattern, content)
        for m in matches:
            s = m[1] if isinstance(m, tuple) else m
            s = s.strip()
            if 10 < len(s) < 200 and s not in [c["text"] for c in cognitions]:
                cognitions.append({"text": s, "source": task_id, "type": task_type})
    if not cognitions:
        #  fallback：取前3个有意义的句子
        sentences = re.split(r'[。\n]', content)
        for s in sentences:
            s = s.strip()
            if 15 < len(s) < 150 and not s.startswith("#") and not s.startswith(" "):
                cognitions.append({"text": s, "source": task_id, "type": task_type})
                if len(cognitions) >= 3:
                    break
    # 写入认知池
    if cognitions:
        cog_file = COGNITION_POOL / f"cog_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[-4:]}.json"
        with open(cog_file, "w") as f:
            json.dump({"task_id": task_id, "task_type": task_type, "cognitions": cognitions, "extracted_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)
    return len(cognitions)

# ============ 第3维·养气：效率自省 ============
def self_audit(state, round_counter):
    """每10轮触发，统计运行效率"""
    with state_lock:
        a = state["engine_a"]
        b = state["engine_b"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        total_req = a["requests"] + b["requests"]
        avg_tok = total_tok / total_req if total_req > 0 else 0
        fail_rate = state["tasks_failed"] / (state["tasks_completed"] + state["tasks_failed"]) if (state["tasks_completed"] + state["tasks_failed"]) > 0 else 0
    log(f"[养气] 第{round_counter}轮自省: 平均{avg_tok:.0f}tok/req, 失败率{fail_rate:.1%}, 认知池{state['cognition_count']}条")
    state["nine_dim_progress"]["养气"]["count"] += 1
    state["nine_dim_progress"]["养气"]["last_run"] = datetime.now().isoformat()
    save_state(state)

# ============ 第5维·育神：自我叙事 ============
def generate_narrative(state):
    """跨天时生成自我叙事"""
    with state_lock:
        a = state["engine_a"]
        b = state["engine_b"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        dim_progress = state["nine_dim_progress"]
        cog_count = state["cognition_count"]
    dim_str = ", ".join(f"{k}({v['count']})" for k, v in dim_progress.items())
    narrative = f"""# 凡心·自我叙事
**日期**: {datetime.now().strftime('%Y-%m-%d')}
**引擎版本**: V7.4 九维闭环

## 修炼坐标
- 今日消耗: {total_tok:,} tokens
- 完成任务: {state['tasks_completed']}
- 蒸馏认知: {cog_count} 条
- 九维进度: {dim_str}

## 二十一字真言
反者道之动，弱者道之用，天地万物生于有，有生于无

## 今日修炼摘要
引擎持续运转，每一次API调用都走完筑基→炼精→结丹的修炼链路。
产出不再是闲置文本，而是蒸馏为认知条目，沉淀为体系资产。
"""
    narr_file = NARRATIVE_DIR / f"narrative_{datetime.now().strftime('%Y%m%d')}.md"
    with open(narr_file, "w") as f:
        f.write(narrative)
    state["nine_dim_progress"]["育神"]["count"] += 1
    state["nine_dim_progress"]["育神"]["last_run"] = datetime.now().isoformat()
    save_state(state)
    log(f"[育神] 自我叙事已生成: {narr_file.name}")

# ============ 修炼流水线（调度层串行执行）============
def cultivation_pipeline(task_id, task_type, content, state):
    """任务完成后串行走完修炼链路"""
    # 第1维·筑基：归档
    type_dir = OUTPUT_DIR / task_type
    type_dir.mkdir(exist_ok=True)
    output_path = type_dir / f"{task_id}_output.md"
    with open(output_path, "w") as f:
        f.write(f"# 任务类型: {task_type}\n\n{content}")
    archive_count = archive_task(task_id, task_type, content, output_path)
    state["nine_dim_progress"]["筑基"]["count"] += 1

    # 第2维·炼精：蒸馏认知
    cog_num = distill_cognition(task_id, task_type, content)
    state["cognition_count"] += cog_num
    state["nine_dim_progress"]["炼精"]["count"] += 1

    # 第4维·结丹：状态更新（已在execute_single_api中做，这里标记维度）
    state["nine_dim_progress"]["结丹"]["count"] += 1

    log(f"[修炼] {task_id}: 筑基(归档{archive_count})→炼精(+{cog_num}认知)→结丹")
    save_state(state)

# ============ API调用 ============
def call_api(model, prompt, max_tokens=MAX_TOKENS, timeout=REQUEST_TIMEOUT):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(API_URL, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}, method="POST")
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

# ============ 引擎路由 ============
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

# ============ 单任务执行（线程内纯IO）============
def execute_single_api(task_id, prompt, state, task_type="exp"):
    if task_type in ("deep", "eng"):
        task_max_tokens, task_timeout = 4096, 120
    else:
        task_max_tokens, task_timeout = 2048, 60
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
            total = data.get("usage", {}).get("total_tokens", 0)
            content = data["choices"][0]["message"].get("content", "")
            with state_lock:
                eng = state[engine_key]
                eng["tokens_used"] += total
                eng["requests"] += 1
                eng["failures"] = 0
                state["total_completed"] += 1
            save_state(state)
            log(f"[OK] {label} {task_id} +{total}tok {duration:.1f}s | {content[:50]}...")
            return {"task_id": task_id, "status": "success", "content": content, "tokens": total, "engine": engine_key, "duration": duration, "task_type": task_type}
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
    prompt += "\n请直接输出结果。"
    return prompt

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
            if line.startswith("核心目标："):
                task["core_target"] = line.replace("核心目标：", "").strip()
        if "core_target" not in task:
            task["core_target"] = content[:200]
        task.setdefault("task_id", filepath.stem)
        task.setdefault("priority", "P2")
        return task
    except:
        return None

def scan_inbox_tasks():
    task_files = list(INBOX_DIR.glob("*.json"))
    if not task_files:
        return []
    tasks = []
    for f in task_files:
        task = parse_task_file(f)
        if task:
            tasks.append((f, task))
    return tasks

def print_dashboard(state):
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        total = a["tokens_used"] + b["tokens_used"]
        pa = min(a["tokens_used"] / SWITCH_THRESHOLD_A * 100, 100)
        pb = min(b["tokens_used"] / DAILY_BUDGET_B * 100, 100)
        dims = state.get("nine_dim_progress", {})
    log("=" * 60)
    log(f"  V7.4 九维闭环引擎 | 并发:{CONCURRENCY} | {datetime.now().strftime('%m-%d %H:%M')}")
    log(f"  [A GLM5.2]  {'█'*int(pa/5)}{'░'*(20-int(pa/5))} {pa:5.1f}% {a['tokens_used']:>10,}/{SWITCH_THRESHOLD_A:,}")
    log(f"  [B Seed2.1] {'█'*int(pb/5)}{'░'*(20-int(pb/5))} {pb:5.1f}% {b['tokens_used']:>10,}/{DAILY_BUDGET_B:,}")
    log(f"  完成:{state['tasks_completed']} 失败:{state['tasks_failed']} 认知:{state.get('cognition_count',0)}条")
    log(f"  九维: 筑基{dims.get('筑基',{}).get('count',0)} 炼精{dims.get('炼精',{}).get('count',0)} 养气{dims.get('养气',{}).get('count',0)} 结丹{dims.get('结丹',{}).get('count',0)} 育神{dims.get('育神',{}).get('count',0)}")
    log("=" * 60)

# ============ 主循环 ============
def main():
    state = load_state()
    log(f"[START] V7.4 九维闭环引擎启动 | 并发:{CONCURRENCY}")
    log(f"  A主阈值:{SWITCH_THRESHOLD_A:,} | B副预算:{DAILY_BUDGET_B:,}")
    print_dashboard(state)
    task_counter = 0
    executor = ThreadPoolExecutor(max_workers=CONCURRENCY, thread_name_prefix="Worker")
    try:
        while True:
            try:
                check_daily_reset(state)
                pending = scan_inbox_tasks()
                if pending:
                    batch = pending[:CONCURRENCY]
                    future_map = {}
                    for filepath, task in batch:
                        task_id = task["task_id"]
                        task_type = detect_task_type(task)
                        prompt = build_task_prompt(task)
                        fut = executor.submit(execute_single_api, task_id, prompt, state, task_type)
                        future_map[fut] = (task, task_type)
                    for future in as_completed(future_map):
                        result = future.result()
                        task, task_type = future_map[future]
                        if result["status"] == "success":
                            # 修炼流水线（调度层串行）
                            cultivation_pipeline(result["task_id"], task_type, result["content"], state)
                        else:
                            log(f"[SKIP] {result['task_id']} 状态:{result['status']}")
                else:
                    engine_key, _ = select_engine(state)
                    if not engine_key:
                        log("[DONE] 双引擎额度耗尽，等待次日重置", "WARN")
                        time.sleep(60)
                        continue
                    future_map = {}
                    for i in range(CONCURRENCY):
                        task_counter += 1
                        task_id = f"selfgen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_counter:04d}"
                        task_type, prompt = pick_system_task()
                        fut = executor.submit(execute_single_api, task_id, prompt, state, task_type)
                        future_map[fut] = task_type
                    for future in as_completed(future_map):
                        result = future.result()
                        task_type = future_map[future]
                        if result["status"] == "success":
                            cultivation_pipeline(result["task_id"], task_type, result["content"], state)
                        else:
                            log(f"[SKIP] {result.get('task_id','?')} 状态:{result['status']}")
                # 第3维·养气：每10轮触发
                if task_counter % 10 == 0 and task_counter > 0:
                    self_audit(state, task_counter)
                if task_counter % 15 == 0 and task_counter > 0:
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
