#!/usr/bin/env python3
"""
火山方舟双引擎调度守护脚本 V1.1
- 引擎A: glm-5-2-260617 (主, 日预算160万)
- 引擎B: doubao-seed-2-1-turbo-260628 (副, 日预算160万)
- 短prompt策略: 所有任务控制在30秒内返回(API硬超时)
- 自动路由 + 熔断 + 额度持久化 + 按日重置
"""
import json, time, os, random, urllib.request, urllib.error
from datetime import datetime

API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dual_engine_state.json")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dual_engine_logs")
os.makedirs(LOG_DIR, exist_ok=True)

MODEL_A = "glm-5-2-260617"
MODEL_B = "doubao-seed-2-1-turbo-260628"
SWITCH_THRESHOLD_A = 1_600_000  # 主引擎达到此值后全量切换副引擎
DAILY_BUDGET_B = 2_000_000     # 副引擎日限额
REQUEST_TIMEOUT = 35          # 略大于API 30s硬超时, 快速失败
REQUEST_INTERVAL = 2.0        # 请求间隔(秒)
FUSE_THRESHOLD = 5            # 连续失败触发熔断
FUSE_COOLDOWN = 120           # 熔断冷却(秒)
MAX_RETRIES = 2               # 单任务最大重试

# 短问答任务池: 确保30秒内返回, 单次约500-1200 tokens
TASKS_A = [
    "用5个要点概括微服务架构的核心原则。",
    "列出Python中三种实现单例模式的方法, 各一句话说明。",
    "解释CAP定理的三个字母分别代表什么, 各一句话。",
    "用三句话说明什么是 eventual consistency。",
    "列出数据库索引的三种类型及其适用场景。",
    "解释TCP三次握手为什么不是两次, 一句话。",
    "列出提高API吞吐量的5个常用手段。",
    "用四句话解释什么是容器编排。",
    "列出分布式锁的三种实现方式。",
    "解释什么是读写分离, 一句话说明其优势。",
    "列出HTTP/2相比HTTP/1.1的三个核心改进。",
    "用三句话解释什么是服务网格(Service Mesh)。",
    "列出缓存穿透、击穿、雪崩的区别, 各一句话。",
    "解释什么是反向代理, 一句话。",
    "列出五种常见的设计模式名称。",
    "用四句话说明Git rebase和merge的区别。",
    "列出消息队列的三个核心使用场景。",
    "解释什么是幂等性, 举一个例子。",
    "列出Linux中查看系统资源的五个常用命令。",
    "用三句话解释什么是DevOps。",
    "列出NoSQL数据库的四种类型及代表产品。",
    "解释什么是蓝绿部署, 一句话。",
    "列出微服务间通信的两种主流方式。",
    "用四句话说明什么是可观测性(Observability)。",
    "列出API限流的三种常用算法。",
    "解释什么是分布式事务, 一句话说明难点。",
    "列出五种常见的排序算法及其时间复杂度。",
    "用三句话解释什么是CDN。",
    "列出数据备份的三种策略类型。",
    "解释什么是零信任架构, 一句话。",
    "列出容器化部署相比传统部署的四个优势。",
    "用四句话说明什么是混沌工程。",
    "列出网络安全中的AAA框架含义。",
    "解释什么是灰度发布, 一句话。",
    "列出三种常见的负载均衡算法。",
    "用三句话解释什么是基础设施即代码(IaC)。",
    "列出日志管理的ELK栈三个组件名称。",
    "解释什么是连接池, 一句话说明作用。",
    "列出四种常见的Web服务器软件。",
    "用四句话说明什么是领域驱动设计(DDD)。",
]

TASKS_B = [
    "列出五个提高Python代码运行效率的技巧。",
    "用三句话解释什么是装饰器。",
    "列出JavaScript中三种声明变量的方式及区别。",
    "解释什么是闭包, 举一个简单例子。",
    "列出SQL中JOIN的四种类型。",
    "用四句话说明React和Vue的核心区别。",
    "列出三种常见的CSS布局方式。",
    "解释什么是RESTful API, 一句话。",
    "列出前端性能优化的五个常用手段。",
    "用三句话解释什么是虚拟DOM。",
    "列出Git中撤销修改的三种场景及命令。",
    "解释什么是跨域, 一句话说明解决方法。",
    "列出Node.js中三种常用的模块系统。",
    "用四句话说明什么是函数式编程。",
    "列出数据库规范化的三个范式。",
    "解释什么是事件循环(Event Loop), 一句话。",
    "列出五种HTTP状态码及其含义。",
    "用三句话解释什么是Promise。",
    "列出Docker中三个核心概念。",
    "解释什么是JWT, 一句话说明结构。",
    "列出三种常见的前端构建工具。",
    "用四句话说明什么是SSR(服务端渲染)。",
    "列出Web安全的三种常见攻击及防御。",
    "解释什么是WebSocket, 一句话。",
    "列出三种数据序列化格式及特点。",
    "用三句话解释什么是依赖注入。",
    "列出五种常见的算法数据结构。",
    "解释什么是ORM, 一句话说明优缺点。",
    "列出三种常见的测试类型。",
    "用四句话说明什么是CI/CD。",
    "列出Linux中三种文件权限类型。",
    "解释什么是环境变量, 一句话。",
    "列出三种常见的API认证方式。",
    "用三句话解释什么是中间件。",
    "列出五种常见的正则表达式元字符。",
    "解释什么是垃圾回收(GC), 一句话。",
    "列出三种常见的缓存淘汰策略。",
    "用四句话说明什么是响应式编程。",
    "列出三种常见的版本控制策略。",
    "解释什么是SOLID原则, 列出五个字母含义。",
]

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(os.path.join(LOG_DIR, f"daemon_{datetime.now().strftime('%Y-%m-%d')}.log"), "a") as f:
        f.write(line + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0},
        "total_completed": 0,
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

def call_api(model, prompt):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode())

def execute_task(engine_key, model, prompt, state):
    eng = state[engine_key]
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = call_api(model, prompt)
            usage = data.get("usage", {})
            total = usage.get("total_tokens", 0)
            content = data["choices"][0]["message"].get("content", "")
            eng["tokens_used"] += total
            eng["requests"] += 1
            eng["failures"] = 0
            state["total_completed"] += 1
            label = "A主" if engine_key == "engine_a" else "B副"
            log(f"[OK] {label} req#{eng['requests']} +{total}tok (累计{eng['tokens_used']:,}) | {content[:50]}...")
            save_state(state)
            return True
        except Exception as e:
            eng["failures"] += 1
            log(f"[ERR] {engine_key} attempt{attempt}: {type(e).__name__}: {e}")
            if eng["failures"] >= FUSE_THRESHOLD:
                eng["fuse_until"] = time.time() + FUSE_COOLDOWN
                log(f"[FUSE] {engine_key} 连续失败{FUSE_THRESHOLD}次, 熔断{FUSE_COOLDOWN}秒")
            if attempt < MAX_RETRIES:
                time.sleep(3)
    return False

def route_and_run(state):
    now = time.time()
    a_fused = state["engine_a"]["fuse_until"] > now
    b_fused = state["engine_b"]["fuse_until"] > now
    a_full = state["engine_a"]["tokens_used"] >= SWITCH_THRESHOLD_A
    b_full = state["engine_b"]["tokens_used"] >= DAILY_BUDGET_B

    # 严格阈值轮转: 主引擎没到160万就只跑主引擎, 到了才切副引擎
    if not a_full and not a_fused:
        execute_task("engine_a", MODEL_A, random.choice(TASKS_A), state)
    elif not b_full and not b_fused:
        if a_full:
            log(f"[SWITCH] 主引擎已达{SWITCH_THRESHOLD_A:,}阈值, 全量切换副引擎")
        execute_task("engine_b", MODEL_B, random.choice(TASKS_B), state)
    else:
        log("[DONE] 主引擎达阈值且副引擎额度耗尽/熔断, 今日任务完成")
        time.sleep(60)

def print_dashboard(state):
    a = state["engine_a"]; b = state["engine_b"]
    pa = a["tokens_used"] / SWITCH_THRESHOLD_A * 100
    pb = b["tokens_used"] / DAILY_BUDGET_B * 100
    bar_a = "█" * int(pa / 5) + "░" * (20 - int(pa / 5))
    bar_b = "█" * int(pb / 5) + "░" * (20 - int(pb / 5))
    fuse_a = "熔断" if a["fuse_until"] > time.time() else "正常"
    fuse_b = "熔断" if b["fuse_until"] > time.time() else "正常"
    log("=" * 60)
    log(f"  日期: {state['date']}  |  已完成: {state['total_completed']}")
    log(f"  [A GLM5.2]  {bar_a} {pa:5.1f}%  {a['tokens_used']:>10,}/{SWITCH_THRESHOLD_A:,}  req:{a['requests']}  {fuse_a}")
    log(f"  [B Seed2.1] {bar_b} {pb:5.1f}%  {b['tokens_used']:>10,}/{DAILY_BUDGET_B:,}  req:{b['requests']}  {fuse_b}")
    log(f"  合计: {a['tokens_used']+b['tokens_used']:,} / {SWITCH_THRESHOLD_A+DAILY_BUDGET_B:,}")
    log("=" * 60)

def main():
    log("=" * 60)
    log("[START] 火山方舟双引擎守护 V1.1 启动")
    log(f"  主引擎: {MODEL_A} 预算: {SWITCH_THRESHOLD_A:,}")
    log(f"  副引擎: {MODEL_B} 预算: {DAILY_BUDGET_B:,}")
    log(f"  间隔: {REQUEST_INTERVAL}s  超时: {REQUEST_TIMEOUT}s  熔断阈值: {FUSE_THRESHOLD}")
    log("=" * 60)
    state = load_state()
    check_daily_reset(state)
    print_dashboard(state)
    counter = 0
    while True:
        check_daily_reset(state)
        route_and_run(state)
        counter += 1
        if counter % 20 == 0:
            print_dashboard(state)
        time.sleep(REQUEST_INTERVAL)

if __name__ == "__main__":
    main()
