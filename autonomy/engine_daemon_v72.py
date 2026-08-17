#!/usr/bin/env python3
"""
V7.2 脑体分离引擎守护进程
- 任务队列驱动（扫描 dispatch/inbox/）
- 双引擎路由 + 熔断 + 额度持久化（继承V7.1）
- 任务状态管理 + 回执生成
- 空闲时自动消耗Token（预设任务池）
- 故障自愈闭环
"""
import json, time, os, random, urllib.request, urllib.error, re, shutil, hashlib
from datetime import datetime
from pathlib import Path

# ============ 路径配置 ============
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

# ============ API配置 ============
API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
MODEL_A = "glm-5-2-260617"
MODEL_B = "doubao-seed-2-1-turbo-260628"
SWITCH_THRESHOLD_A = 1_600_000
DAILY_BUDGET_B = 2_000_000
REQUEST_TIMEOUT = 120
REQUEST_INTERVAL = 2.0
FUSE_THRESHOLD = 5
FUSE_COOLDOWN = 120
MAX_RETRIES = 2
SCAN_INTERVAL = 10  # 任务目录扫描间隔

# ============ 空闲消耗任务池 ============
IDLE_TASKS = [
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

# ============ 日志 ============
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_DIR / f"engine_{datetime.now().strftime('%Y-%m-%d')}.log", "a") as f:
        f.write(line + "\n")

# ============ 状态管理 ============
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "total_completed": 0,
        "tasks_completed": 0,
        "tasks_failed": 0,
        "self_heal_count": 0,
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def check_daily_reset(state):
    today = datetime.now().strftime("%Y-%m-%d")
    if state["date"] != today:
        log(f"[RESET] 新的一天 {today}, 额度重置")
        state["date"] = today
        state["engine_a"]["tokens_used"] = 0
        state["engine_a"]["requests"] = 0
        state["engine_b"]["tokens_used"] = 0
        state["engine_b"]["requests"] = 0
        save_state(state)

# ============ 任务解析 ============
def parse_task_file(filepath):
    """解析任务文件，支持JSON和极简文本格式"""
    try:
        with open(filepath) as f:
            content = f.read().strip()

        # JSON格式
        if content.startswith("{"):
            task = json.loads(content)
            task["_source"] = "json"
            return task

        # 极简文本格式
        task = {"_source": "text", "accept_criteria": []}
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("【") and "】" in line:
                task["priority"] = re.search(r"【(P\d)】", line).group(1)
            elif line.startswith("核心目标："):
                task["core_target"] = line.replace("核心目标：", "").strip()
            elif line.startswith("验收："):
                criteria = line.replace("验收：", "").strip()
                task["accept_criteria"] = [c.strip() for c in re.split(r"[；;]", criteria) if c.strip()]
            elif line.startswith("截止："):
                task["deadline"] = line.replace("截止：", "").strip()

        if "core_target" not in task:
            task["core_target"] = content[:200]

        # 补全缺省字段
        task.setdefault("task_id", filepath.stem)
        task.setdefault("priority", "P2")
        task.setdefault("task_type", "execution")
        task.setdefault("deadline", "当日24:00")
        task.setdefault("constraints", {})
        return task
    except Exception as e:
        log(f"任务解析失败 {filepath.name}: {e}", "ERROR")
        return None

# ============ 任务状态 ============
def update_task_status(task_id, status, **kwargs):
    status_file = STATUS_DIR / f"{task_id}.json"
    data = {"task_id": task_id, "status": status, "updated_at": datetime.now().isoformat()}
    data.update(kwargs)
    with open(status_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_task_priority_order(task):
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(task.get("priority", "P2"), 2)

# ============ API调用 ============
def call_api(model, prompt, max_tokens=4096):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    # 禁用代理（沙箱环境代理会导致请求卡住）
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }, method="POST")
    with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode())

# ============ 引擎路由 ============
def select_engine(state):
    now = time.time()
    a_fused = state["engine_a"]["fuse_until"] > now
    b_fused = state["engine_b"]["fuse_until"] > now
    a_full = state["engine_a"]["tokens_used"] >= SWITCH_THRESHOLD_A
    b_full = state["engine_b"]["tokens_used"] >= DAILY_BUDGET_B

    if not a_full and not a_fused:
        return "engine_a", MODEL_A
    elif not b_full and not b_fused:
        if a_full:
            log(f"[SWITCH] 主引擎达{SWITCH_THRESHOLD_A:,}阈值, 切换副引擎")
        return "engine_b", MODEL_B
    else:
        return None, None

# ============ 执行任务 ============
def execute_task_with_engine(task, state):
    """执行真实任务，返回结果。主引擎失败后自动切换副引擎重试。"""
    prompt = build_task_prompt(task)
    # 构建引擎尝试顺序：主引擎优先，失败后切换副引擎
    engine_order = []
    primary_key, primary_model = select_engine(state)
    if primary_key:
        engine_order.append((primary_key, primary_model))
    other_key = "engine_b" if primary_key == "engine_a" else "engine_a"
    other_model = MODEL_B if other_key == "engine_b" else MODEL_A
    other_eng = state[other_key]
    other_limit = DAILY_BUDGET_B if other_key == "engine_b" else SWITCH_THRESHOLD_A
    other_full = other_eng["tokens_used"] >= other_limit
    other_fused = other_eng["fuse_until"] > time.time()
    if not other_full and not other_fused and (other_key, other_model) not in engine_order:
        engine_order.append((other_key, other_model))

    if not engine_order:
        log("[DONE] 双引擎均不可用（额度耗尽/熔断）", "WARN")
        return None, "resource_exhausted"

    for idx, (engine_key, model) in enumerate(engine_order):
        eng = state[engine_key]
        label = "A主" if engine_key == "engine_a" else "B副"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                start_time = time.time()
                data = call_api(model, prompt, max_tokens=4096)
                duration = time.time() - start_time
                usage = data.get("usage", {})
                total = usage.get("total_tokens", 0)
                content = data["choices"][0]["message"].get("content", "")
                eng["tokens_used"] += total
                eng["requests"] += 1
                eng["failures"] = 0
                state["total_completed"] += 1
                log(f"[OK] {label} 任务{task['task_id']} +{total}tok 耗时{duration:.1f}s | {content[:60]}...")
                save_state(state)
                return {
                    "content": content,
                    "tokens_used": total,
                    "duration_seconds": round(duration, 1),
                    "engine_used": engine_key,
                }, None
            except Exception as e:
                eng["failures"] += 1
                log(f"[ERR] {label} 任务{task['task_id']} attempt{attempt}: {type(e).__name__}: {e}", "ERROR")
                if eng["failures"] >= FUSE_THRESHOLD:
                    eng["fuse_until"] = time.time() + FUSE_COOLDOWN
                    log(f"[FUSE] {engine_key} 连续失败{FUSE_THRESHOLD}次, 熔断{FUSE_COOLDOWN}秒", "WARN")
                    state["self_heal_count"] += 1
                if attempt < MAX_RETRIES:
                    time.sleep(3)
        if idx < len(engine_order) - 1:
            next_label = "B副" if engine_key == "engine_a" else "A主"
            log(f"[SWITCH-RETRY] {label}连续失败，切换{next_label}重试", "WARN")
    return None, "api_error"

def build_task_prompt(task):
    """将任务结构转换为API prompt"""
    prompt = f"任务目标：{task.get('core_target', '')}\n\n"
    if task.get("accept_criteria"):
        prompt += "验收标准：\n"
        for i, c in enumerate(task["accept_criteria"], 1):
            prompt += f"{i}. {c}\n"
    prompt += "\n请直接输出结果，不需要解释过程。"
    return prompt

def execute_idle_task(state):
    """空闲时消耗Token"""
    engine_key, model = select_engine(state)
    if not engine_key:
        time.sleep(60)
        return

    eng = state[engine_key]
    prompt = random.choice(IDLE_TASKS)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = call_api(model, prompt, max_tokens=4096)
            usage = data.get("usage", {})
            total = usage.get("total_tokens", 0)
            content = data["choices"][0]["message"].get("content", "")
            eng["tokens_used"] += total
            eng["requests"] += 1
            eng["failures"] = 0
            state["total_completed"] += 1
            label = "A主" if engine_key == "engine_a" else "B副"
            log(f"[SELF-GEN] {label} +{total}tok (累计{eng['tokens_used']:,}) | {content[:60]}...")
            save_state(state)
            return
        except Exception as e:
            eng["failures"] += 1
            if eng["failures"] >= FUSE_THRESHOLD:
                eng["fuse_until"] = time.time() + FUSE_COOLDOWN
                state["self_heal_count"] += 1
            if attempt < MAX_RETRIES:
                time.sleep(3)

# ============ 回执生成 ============
def generate_receipt(task, result, state, error=None):
    task_id = task["task_id"]
    receipt_file = RECEIPT_DIR / f"{task_id}.json"

    if error:
        receipt = {
            "task_id": task_id,
            "status": "failed",
            "fault_type": error,
            "impact_scope": "仅本任务",
            "fallback_action": "已自动重试，待本体决策",
            "retry_count": MAX_RETRIES,
            "next_action": "等待本体决策",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        state["tasks_failed"] += 1
        # 移入失败目录
        shutil.move(str(INBOX_DIR / f"{task_id}.json"), str(FAILED_DIR / f"{task_id}.json"))
    else:
        # 保存产出
        output_path = BASE_DIR / "outputs" / f"{task_id}_output.txt"
        with open(output_path, "w") as f:
            f.write(result["content"])

        # 计算MD5
        md5 = hashlib.md5(result["content"].encode()).hexdigest()

        receipt = {
            "task_id": task_id,
            "status": "completed",
            "summary": result["content"][:100],
            "core_data": {"tokens_used": result["tokens_used"], "duration": result["duration_seconds"]},
            "deliverables": [{
                "name": f"{task_id}_output",
                "path": str(output_path),
                "md5": md5,
            }],
            "tokens_used": result["tokens_used"],
            "duration_seconds": result["duration_seconds"],
            "engine_used": result["engine_used"],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        state["tasks_completed"] += 1
        # 移除inbox文件
        inbox_file = INBOX_DIR / f"{task_id}.json"
        if inbox_file.exists():
            inbox_file.unlink()

    with open(receipt_file, "w") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)

    update_task_status(task_id, receipt["status"], receipt=receipt)
    save_state(state)
    return receipt

# ============ 任务扫描 ============
def scan_and_dispatch(state):
    """扫描inbox目录，按优先级执行任务"""
    task_files = list(INBOX_DIR.glob("*.json"))
    if not task_files:
        return False

    # 解析所有任务并排序
    tasks = []
    for f in task_files:
        task = parse_task_file(f)
        if task:
            tasks.append((f, task))

    tasks.sort(key=lambda x: get_task_priority_order(x[1]))

    # 执行最高优先级任务
    filepath, task = tasks[0]
    task_id = task["task_id"]
    log(f"[DISPATCH] 拾取任务 {task_id} 优先级={task['priority']} 目标={task['core_target'][:50]}")
    update_task_status(task_id, "running", task=task)

    result, error = execute_task_with_engine(task, state)
    receipt = generate_receipt(task, result if result else {}, state, error=error)

    if error:
        log(f"[FAIL] 任务 {task_id} 失败: {error}", "ERROR")
    else:
        log(f"[DONE] 任务 {task_id} 完成, 回执已生成")

    return True

# ============ 仪表盘 ============
def print_dashboard(state):
    a = state["engine_a"]; b = state["engine_b"]
    pa = a["tokens_used"] / SWITCH_THRESHOLD_A * 100
    pb = b["tokens_used"] / DAILY_BUDGET_B * 100
    bar_a = "█" * int(pa / 5) + "░" * (20 - int(pa / 5))
    bar_b = "█" * int(pb / 5) + "░" * (20 - int(pb / 5))
    fuse_a = "熔断" if a["fuse_until"] > time.time() else "正常"
    fuse_b = "熔断" if b["fuse_until"] > time.time() else "正常"
    log("=" * 60)
    log(f"  V7.2 脑体分离引擎 | 日期: {state['date']}")
    log(f"  [A GLM5.2]  {bar_a} {pa:5.1f}%  {a['tokens_used']:>10,}/{SWITCH_THRESHOLD_A:,}  req:{a['requests']}  {fuse_a}")
    log(f"  [B Seed2.1] {bar_b} {pb:5.1f}%  {b['tokens_used']:>10,}/{DAILY_BUDGET_B:,}  req:{b['requests']}  {fuse_b}")
    log(f"  任务完成: {state.get('tasks_completed',0)} | 任务失败: {state.get('tasks_failed',0)} | 自愈次数: {state.get('self_heal_count',0)}")
    log(f"  合计Token: {a['tokens_used']+b['tokens_used']:,} / {SWITCH_THRESHOLD_A+DAILY_BUDGET_B:,}")
    log("=" * 60)

# ============ 主循环 ============
def main():
    log("=" * 60)
    log("[START] V7.2 脑体分离引擎守护进程启动")
    log(f"  主引擎: {MODEL_A} 预算: {SWITCH_THRESHOLD_A:,}")
    log(f"  副引擎: {MODEL_B} 预算: {DAILY_BUDGET_B:,}")
    log(f"  任务目录: {INBOX_DIR}")
    log(f"  扫描间隔: {SCAN_INTERVAL}s | 请求间隔: {REQUEST_INTERVAL}s")
    log("=" * 60)

    state = load_state()
    check_daily_reset(state)
    print_dashboard(state)

    counter = 0
    while True:
        check_daily_reset(state)

        # 优先处理任务队列
        had_task = scan_and_dispatch(state)

        if not had_task:
            # 空闲时消耗Token
            execute_idle_task(state)

        counter += 1
        if counter % 20 == 0:
            print_dashboard(state)

        time.sleep(REQUEST_INTERVAL if had_task else SCAN_INTERVAL)

if __name__ == "__main__":
    main()
