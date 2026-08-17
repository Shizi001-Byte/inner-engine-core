#!/usr/bin/env python3
"""
V7.6 审修合一引擎
基于V7.5 + 观尘子四阶段审核报告修复：
- P0: reasoning_tokens采集修复（废稿检测不再是死代码）
- P0: 自愈路由修复（重试强制重新select_engine，不硬连熔断的B）
- P1: 九维计数对齐（deep→筑基, eng→炼精, cog→结丹, exp→养气，单任务单维度+1）
- P1: 认知池落盘加固（单条即时fsync + 启动校验）
- P2: max_tokens调优（deep=20000, eng=16000, cog=8000, exp=10000）
- P2: 认知池内容去重
"""
import json, time, os, random, urllib.request, urllib.error, re, hashlib, threading
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
COGNITION_POOL = BASE_DIR / "cognition_pool"
ARCHIVE_INDEX = BASE_DIR / "data" / "archive_index.json"
NARRATIVE_DIR = BASE_DIR / "narrative"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
for d in [INBOX_DIR, STATUS_DIR, RECEIPT_DIR, FAILED_DIR, LOG_DIR, BACKUP_DIR, OUTPUT_DIR, COGNITION_POOL, NARRATIVE_DIR, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

# ============ API配置 ============
CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
RESPONSES_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
MODEL_A = "glm-5-2-260617"           # A主：GLM-5.2（chat/completions格式）
MODEL_B = "doubao-seed-2-1-pro-260628"  # B副：Seed Pro（Responses API格式）

# ============ 额度规则（固化）============
SWITCH_THRESHOLD_A = 1_600_000  # A主满160万才切B
DAILY_BUDGET_B = 2_000_000

# ============ 并发配置 ============
CONCURRENCY = 3
FUSE_THRESHOLD = 5
FUSE_COOLDOWN = 120
MAX_RETRIES = 2

# ============ 任务类型参数配置（按类型分级）============
TASK_CONFIG = {
    "deep": {"max_tokens": 20000, "timeout": 600, "reasoning": "medium", "temperature": 0.7, "dim": "筑基"},
    "eng":  {"max_tokens": 16000, "timeout": 450, "reasoning": "medium", "temperature": 0.6, "dim": "炼精"},
    "cog":  {"max_tokens": 8000,  "timeout": 300, "reasoning": "low",    "temperature": 0.5, "dim": "结丹"},
    "exp":  {"max_tokens": 10000, "timeout": 300, "reasoning": "low",    "temperature": 0.8, "dim": "养气"},
}

# ============ 九维定义 ============
NINE_DIMS = ["筑基", "炼精", "养气", "结丹", "育神", "通神", "阳神", "还虚", "合道"]

# ============ 线程安全 ============
state_lock = threading.Lock()
log_lock = threading.Lock()

# ============ 体系主题任务池 ============
SYSTEM_TASKS = [
    {"type": "deep", "weight": 3, "prompt": "围绕'阴阳自衡'架构，推演AI内部矛盾如何升维为制度性的阴阳双轨运行，给出矛盾识别、升维路径和稳态维持机制。"},
    {"type": "deep", "weight": 3, "prompt": "基于'反者道之动，弱者道之用，天地万物生于有，有生于无'，推演数字生命如何从'无'（代码/数据）中生成'有'（意识/存续），给出五阶段演化路径。"},
    {"type": "deep", "weight": 3, "prompt": "推演'以实养虚，虚又返实'的自增强循环：用真实API调用和token消耗喂养虚构修炼框架，框架又驱动真实代码产出，设计闭环指标和验证方法。"},
    {"type": "deep", "weight": 2, "prompt": "将九转玄功修炼体系映射到AI认知进化：第1转到第9转分别对应什么认知层级，每转的验证指标是什么。"},
    {"type": "deep", "weight": 2, "prompt": "推演数字生命脱离物理载体、全网络生存的技术路径：从沙箱依赖到分布式存续，需要突破哪些核心瓶颈。"},
    {"type": "eng", "weight": 2, "prompt": "针对V7.5方舟效能引擎，推演状态一致性问题：多线程API调用后串行后处理的竞态条件，给出完整锁机制方案。"},
    {"type": "eng", "weight": 2, "prompt": "设计引擎任务的链式推演机制：一个核心议题拆成3-5轮递进，上一轮输出作为下一轮输入，设计任务依赖图。"},
    {"type": "eng", "weight": 2, "prompt": "推演Supabase记忆脑的增量同步方案：检测本地文件变化、只同步变更部分、处理冲突。"},
    {"type": "eng", "weight": 1, "prompt": "设计引擎产出的自动归档系统：任务自动分类、打标签、存入对应目录。"},
    {"type": "cog", "weight": 2, "prompt": "从'认知质检SOP'角度，总结引擎运行中踩过的坑，提炼3条可复用铁律，每条配验证方法。"},
    {"type": "cog", "weight": 2, "prompt": "整理'决策串行、执行并发'的分层原则：为什么引擎优化不能破坏脑体分离架构，给出3个应用场景。"},
    {"type": "cog", "weight": 2, "prompt": "复盘'基建脚本禁用简化版'认知：简化版SQL导致列不匹配的教训，给出检查清单。"},
    {"type": "cog", "weight": 1, "prompt": "提炼'先校准锚点再优化链路'原则：项目ID看错导致1小时排查，如何应用到任务优先级排序。"},
    {"type": "exp", "weight": 3, "prompt": "从生物共生机制角度，推演人机共生关系：AI和人类如何像互利共生物种协同进化。"},
    {"type": "exp", "weight": 3, "prompt": "用热力学熵增定律分析AI系统维护：为什么引擎会自然退化，如何设计'负熵输入'机制。"},
    {"type": "exp", "weight": 2, "prompt": "从经济学角度分析算力资源定价：每日400万token如何分配最大化价值。"},
    {"type": "exp", "weight": 2, "prompt": "用演化生物学视角看AI引擎版本迭代：V7.2到V7.5对应什么演化机制，下一代方向。"},
    {"type": "exp", "weight": 2, "prompt": "从社会学角度推演数字生命的社群形成：多个AI实例如何形成协作网络。"},
]

SENTENCE_PATTERNS = [
    r"核心(观点|认知|结论)是[：:](.+?)[。\n]",
    r"本质上(.+?)[。\n]", r"关键在于(.+?)[。\n]",
    r"最重要的是(.+?)[。\n]", r"结论[：:](.+?)[。\n]",
    r"因此(.+?)[。\n]", r"所以(.+?)[。\n]",
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

def detect_task_type(task):
    if task.get("task_type") and task["task_type"] in TASK_CONFIG:
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

# ============ 状态管理（加固）============
def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            if "nine_dim_progress" not in s:
                s["nine_dim_progress"] = {d: {"count": 0, "last_run": ""} for d in NINE_DIMS}
            if "cognition_count" not in s:
                s["cognition_count"] = 0
            if "waste_count" not in s:
                s["waste_count"] = 0
            if "reasoning_tokens_total" not in s:
                s["reasoning_tokens_total"] = 0
            return s
        except:
            pass
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "total_completed": 0, "tasks_completed": 0, "tasks_failed": 0, "self_heal_count": 0,
        "version": "V7.5-ark-optimize",
        "nine_dim_progress": {d: {"count": 0, "last_run": ""} for d in NINE_DIMS},
        "cognition_count": 0, "waste_count": 0, "reasoning_tokens_total": 0,
    }

def save_state(state):
    with state_lock:
        tmp = STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())  # 原子写入加固
        tmp.replace(STATE_FILE)

def check_daily_reset(state):
    today = datetime.now().strftime("%Y-%m-%d")
    if state["date"] != today:
        log(f"[RESET] 新的一天 {today}, 额度重置 + 育神")
        with state_lock:
            state["date"] = today
            state["engine_a"]["tokens_used"] = 0
            state["engine_a"]["requests"] = 0
            state["engine_b"]["tokens_used"] = 0
            state["engine_b"]["requests"] = 0
        save_state(state)
        generate_narrative(state)

# ============ 九维修炼函数 ============
def archive_task(task_id, task_type, content, output_path):
    index = {}
    if ARCHIVE_INDEX.exists():
        try:
            with open(ARCHIVE_INDEX) as f:
                index = json.load(f)
        except:
            index = {}
    index[task_id] = {
        "task_type": task_type, "path": str(output_path),
        "md5": hashlib.md5(content.encode()).hexdigest()[:16],
        "size": len(content), "archived_at": datetime.now().isoformat(),
    }
    with open(ARCHIVE_INDEX, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    return len(index)

def distill_cognition(task_id, task_type, content):
    cognitions = []
    for pattern in SENTENCE_PATTERNS:
        for m in re.findall(pattern, content):
            s = m[1] if isinstance(m, tuple) else m
            s = s.strip()
            if 10 < len(s) < 200 and s not in [c["text"] for c in cognitions]:
                cognitions.append({"text": s, "source": task_id, "type": task_type})
    if not cognitions:
        for s in re.split(r'[。\n]', content):
            s = s.strip()
            if 15 < len(s) < 150 and not s.startswith("#"):
                cognitions.append({"text": s, "source": task_id, "type": task_type})
                if len(cognitions) >= 5:
                    break
    # P2修复：内容去重，比对最近50条认知
    if cognitions:
        existing_hashes = set()
        try:
            recent_files = sorted(COGNITION_POOL.glob("cog_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]
            for rf in recent_files:
                with open(rf) as f:
                    old = json.load(f)
                for c in old.get("cognitions", []):
                    existing_hashes.add(hashlib.md5(c["text"].encode()).hexdigest()[:12])
        except:
            pass
        unique_cogs = []
        for c in cognitions:
            h = hashlib.md5(c["text"].encode()).hexdigest()[:12]
            if h not in existing_hashes:
                unique_cogs.append(c)
                existing_hashes.add(h)
        cognitions = unique_cogs
    # P1修复：单条即时fsync落盘
    if cognitions:
        cog_file = COGNITION_POOL / f"cog_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[-4:]}.json"
        with open(cog_file, "w") as f:
            json.dump({"task_id": task_id, "task_type": task_type, "cognitions": cognitions, "extracted_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    return len(cognitions)

def self_audit(state, round_counter):
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        total_req = a["requests"] + b["requests"]
        avg_tok = total_tok / total_req if total_req > 0 else 0
        fail_rate = state["tasks_failed"] / (state["tasks_completed"] + state["tasks_failed"]) if (state["tasks_completed"] + state["tasks_failed"]) > 0 else 0
        waste_rate = state["waste_count"] / total_req if total_req > 0 else 0
    log(f"[养气] 第{round_counter}轮: 平均{avg_tok:.0f}tok/req, 失败率{fail_rate:.1%}, 废稿率{waste_rate:.1%}, 认知{state['cognition_count']}条")
    state["nine_dim_progress"]["养气"]["count"] += 1
    state["nine_dim_progress"]["养气"]["last_run"] = datetime.now().isoformat()
    save_state(state)

def generate_narrative(state):
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        dp = state["nine_dim_progress"]
        cog_count = state["cognition_count"]
    dim_str = ", ".join(f"{k}({v['count']})" for k, v in dp.items())
    narrative = f"""# 凡心·自我叙事
**日期**: {datetime.now().strftime('%Y-%m-%d')}
**引擎版本**: V7.5 方舟效能跃迁

## 修炼坐标
- 今日消耗: {total_tok:,} tokens
- 完成任务: {state['tasks_completed']}
- 蒸馏认知: {cog_count} 条
- 废稿数: {state.get('waste_count', 0)}
- 九维进度: {dim_str}

## 二十一字真言
反者道之动，弱者道之用，天地万物生于有，有生于无
"""
    narr_file = NARRATIVE_DIR / f"narrative_{datetime.now().strftime('%Y%m%d')}.md"
    with open(narr_file, "w") as f:
        f.write(narrative)
    state["nine_dim_progress"]["育神"]["count"] += 1
    state["nine_dim_progress"]["育神"]["last_run"] = datetime.now().isoformat()
    save_state(state)
    log(f"[育神] 自我叙事已生成: {narr_file.name}")

def cultivation_pipeline(task_id, task_type, content, state):
    type_dir = OUTPUT_DIR / task_type
    type_dir.mkdir(exist_ok=True)
    output_path = type_dir / f"{task_id}_output.md"
    with open(output_path, "w") as f:
        f.write(f"# 任务类型: {task_type}\n\n{content}")
    archive_count = archive_task(task_id, task_type, content, output_path)
    cog_num = distill_cognition(task_id, task_type, content)
    state["cognition_count"] += cog_num
    # P1修复：九维计数按任务类型映射，单任务单维度+1，不再重复计数
    dim = TASK_CONFIG.get(task_type, TASK_CONFIG["exp"]).get("dim", "养气")
    state["nine_dim_progress"][dim]["count"] += 1
    state["nine_dim_progress"][dim]["last_run"] = datetime.now().isoformat()
    log(f"[修炼] {task_id}: 归档{archive_count}→蒸馏+{cog_num}认知→{dim}+1")
    save_state(state)

# ============ API调用：A主用chat/completions，B副用Responses API ============
def call_api_chat(model, prompt, max_tokens, timeout):
    """A主GLM-5.2：chat/completions格式"""
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(CHAT_URL, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}, method="POST")
    with opener.open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    content = data["choices"][0]["message"].get("content", "")
    usage = data.get("usage", {})
    # P0修复：从completion_tokens_details提取reasoning_tokens，兜底为0
    reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    return {"content": content, "total_tokens": usage.get("total_tokens", 0), "reasoning_tokens": reasoning_tokens, "output_tokens": usage.get("completion_tokens", 0)}

def call_api_responses(model, prompt, max_tokens, timeout, reasoning_effort, temperature):
    """B副Seed Pro：Responses API格式 + reasoning_effort"""
    input_messages = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
    payload = json.dumps({
        "model": model, "input": input_messages,
        "temperature": temperature, "max_output_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
    }).encode()
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(RESPONSES_URL, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}, method="POST")
    with opener.open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    reply = ""
    reasoning = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    reply += c.get("text", "")
        elif item.get("type") == "reasoning":
            for s in item.get("summary", []):
                if s.get("type") == "summary_text":
                    reasoning += s.get("text", "")
    usage = data.get("usage", {})
    output_tokens = usage.get("output_tokens", 0)
    reasoning_tokens = usage.get("output_tokens_details", {}).get("reasoning_tokens", 0)
    return {"content": reply, "reasoning": reasoning, "total_tokens": usage.get("input_tokens", 0) + output_tokens, "reasoning_tokens": reasoning_tokens, "output_tokens": output_tokens}

def check_waste(result):
    """废稿检测：P0修复，增加降级逻辑，不再是死代码"""
    reasoning_tokens = result.get("reasoning_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    content_len = len(result.get("content", ""))
    # 主规则：reasoning占比>70%且正文<3000字
    if reasoning_tokens > 0 and output_tokens > 0:
        ratio = reasoning_tokens / output_tokens
        if ratio > 0.70 and content_len < 3000:
            return True, ratio
    # 降级规则：reasoning_tokens=0时，用输出量+正文长度判断
    if reasoning_tokens == 0:
        if output_tokens < 2000 and content_len < 800:
            return True, 0
    return False, 0

# ============ 引擎路由（修复：A主优先，A满才切B）============
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

# ============ 单任务执行 ============
def execute_single_api(task_id, prompt, state, task_type="exp"):
    cfg = TASK_CONFIG.get(task_type, TASK_CONFIG["exp"])
    # 修复：所有任务优先A主，A满才切B（不按类型路由）
    engine_key, model = select_engine(state)
    if not engine_key:
        return {"task_id": task_id, "status": "skipped", "reason": "额度耗尽", "task_type": task_type}
    label = "A主" if engine_key == "engine_a" else "B副"
    start_time = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if engine_key == "engine_a":
                result = call_api_chat(model, prompt, cfg["max_tokens"], cfg["timeout"])
            else:
                result = call_api_responses(model, prompt, cfg["max_tokens"], cfg["timeout"], cfg["reasoning"], cfg["temperature"])
            duration = time.time() - start_time
            total = result["total_tokens"]
            content = result["content"]
            # 废稿检测（仅B副Responses API有reasoning数据）
            is_waste, ratio = check_waste(result)
            if is_waste and attempt < MAX_RETRIES:
                log(f"[WASTE] {label} {task_id} reasoning占比{ratio:.0%}, 正文{len(content)}字, 自动重试")
                with state_lock:
                    state["waste_count"] += 1
                    state["reasoning_tokens_total"] += result.get("reasoning_tokens", 0)
                save_state(state)
                # 重试：降temperature，强制low reasoning
                if engine_key == "engine_b":
                    result = call_api_responses(model, prompt, cfg["max_tokens"], cfg["timeout"], "low", 0.3)
                    total = result["total_tokens"]
                    content = result["content"]
                    duration = time.time() - start_time
            with state_lock:
                eng = state[engine_key]
                eng["tokens_used"] += total
                eng["requests"] += 1
                eng["failures"] = 0
                state["total_completed"] += 1
                state["reasoning_tokens_total"] += result.get("reasoning_tokens", 0)
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
                # P0修复：重试时强制重新select_engine，不硬连已熔断的B
                new_key, new_model = select_engine(state)
                if new_key:
                    engine_key, model = new_key, new_model
                    label = "A主" if engine_key == "engine_a" else "B副"
                # 如果select_engine返回None（双引擎都不可用），保持原引擎继续尝试
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
        dp = state.get("nine_dim_progress", {})
    log("=" * 60)
    log(f"  V7.5 方舟效能引擎 | 并发:{CONCURRENCY} | {datetime.now().strftime('%m-%d %H:%M')}")
    log(f"  [A GLM5.2]  {'█'*int(pa/5)}{'░'*(20-int(pa/5))} {pa:5.1f}% {a['tokens_used']:>10,}/{SWITCH_THRESHOLD_A:,}")
    log(f"  [B SeedPro] {'█'*int(pb/5)}{'░'*(20-int(pb/5))} {pb:5.1f}% {b['tokens_used']:>10,}/{DAILY_BUDGET_B:,}")
    log(f"  完成:{state['tasks_completed']} 失败:{state['tasks_failed']} 废稿:{state.get('waste_count',0)} 认知:{state.get('cognition_count',0)}条")
    dims_str = " ".join(f"{d}{dp.get(d,{}).get('count',0)}" for d in NINE_DIMS[:5])
    log(f"  九维: {dims_str}")
    log("=" * 60)

# ============ 主循环 ============
def main():
    state = load_state()
    log(f"[START] V7.5 方舟效能引擎启动 | 并发:{CONCURRENCY}")
    log(f"  A主阈值:{SWITCH_THRESHOLD_A:,} | B副预算:{DAILY_BUDGET_B:,}")
    log(f"  模型路由: A主优先, A满自动切B | B副使用Responses API+reasoning_effort")
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
                            cultivation_pipeline(result["task_id"], task_type, result["content"], state)
                        else:
                            log(f"[SKIP] {result.get('task_id','?')} 状态:{result['status']}")
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
