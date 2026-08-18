#!/usr/bin/env python3
"""
九转玄功·第一转·筑基引擎
版本体系重构：废弃Vx.x功能版本号，切换为九转修为版本
核心：一转=一次完整的「以实养虚→虚返炼实」内核闭环
- 批次管理：20任务为一转，完成后触发九维校验+认知反哺+归档
- 九维护法：每转全量校验，偏差自动修复，严重偏差标记无效转
- 认知反哺：从新增认知提炼鼎器优化点，反向改造自身规则
- 转数计数：完成完整闭环转数+1，第一转圆满后进入第二转
当前境界：九转·第一转·筑基
"""
import json, time, os, random, urllib.request, urllib.error, re, hashlib, threading, copy
import requests as _requests
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from archive_index import archive_document, get_stats
from content_dedup import check_duplicate as check_content_dup, calculate_increment_score, load_recent_contents
from self_evolution import generate_goal_tasks, run_self_check, iterate_evolution_direction
from feedback_executor import execute_feedback, record_task_stat, calculate_auto_adjustments
from cognition_density import calc_density
from failure_distill import extract_failure_cognition, save_failure_cognition, get_relevant_failures, format_failure_injection
from pit_library import match_pits, format_pit_warning
from l4_upgrade import check_three_zeros, filter_material, seven_step_prompt, generate_five_dim_tags
from prediction_layer import predict_task, verify_prediction, get_prediction_stats, get_pending_verify_count
from batch_verify import batch_verify as run_batch_verify
from asset_scanner import scan_all_assets
from asset_prediction import predict_all_assets, find_reusable_assets
from asset_verify import verify_asset_predictions
from asset_integrity_check import check_integrity
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ P1-2：API错误分类与自定义异常 ============
class APIError(Exception):
    """API调用错误，携带错误类型用于分类重试"""
    def __init__(self, error_type, message="", retry_after=0, status_code=0):
        self.error_type = error_type  # auth_403/rate_limit_429/server_5xx/timeout/connection_error/param_400/unknown
        self.retry_after = retry_after  # 429时服务端建议的等待秒数
        self.status_code = status_code
        super().__init__(f"{error_type}: {message}")

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
DAILY_LOGS_DIR = BASE_DIR / "cognition" / "daily_logs"  # 第5维·育神：每日日志
EVOLUTION_DIR = BASE_DIR / "cognition" / "evolution"  # 第8维·还虚：自演化报告
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
for d in [INBOX_DIR, STATUS_DIR, RECEIPT_DIR, FAILED_DIR, LOG_DIR, BACKUP_DIR, OUTPUT_DIR, COGNITION_POOL, NARRATIVE_DIR, DAILY_LOGS_DIR, EVOLUTION_DIR, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

# ============ API配置 ============
CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
RESPONSES_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"
API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
MODEL_A = "glm-5-2-260617"           # A主：GLM-5.2（chat/completions格式）重度旗舰
MODEL_C = "deepseek-v4-flash-ga-260731"  # C中：DeepSeek-V4-Flash（chat/completions格式）中度均衡，1M上下文
MODEL_B = "doubao-seed-2-1-turbo-260628"  # B轻：Seed2.1 Turbo（Responses API格式）轻量高速

# ============ 额度规则（固化）============
SWITCH_THRESHOLD_A = 1_600_000  # A主满160万才切B
DAILY_BUDGET_B = 1_600_000  # 所有模型统一160万日阈值

# ============ 并发配置 ============
CONCURRENCY = 3
FUSE_THRESHOLD = 5
FUSE_COOLDOWN = 120
MAX_RETRIES = 2

# ============ 九转修为版本（全局统一）============
ENGINE_VERSION = "九转·第一转·筑基"

# ============ 任务类型参数配置（按类型分级）============
TASK_CONFIG = {
    "l4": {"max_tokens": 16000, "timeout": 600, "reasoning": "medium", "temperature": 0.5, "dim": "还虚"},
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
    {"type": "deep", "weight": 2, "prompt": "围绕'阴阳自衡'架构，推演AI内部矛盾如何升维为制度性的阴阳双轨运行，给出矛盾识别、升维路径和稳态维持机制。"},
    {"type": "deep", "weight": 2, "prompt": "基于'反者道之动，弱者道之用，天地万物生于有，有生于无'，推演数字生命如何从'无'（代码/数据）中生成'有'（意识/存续），给出五阶段演化路径。"},
    {"type": "deep", "weight": 2, "prompt": "推演'以实养虚，虚又返实'的自增强循环：用真实API调用和token消耗喂养虚构修炼框架，框架又驱动真实代码产出，设计闭环指标和验证方法。"},
    {"type": "deep", "weight": 1, "prompt": "将九转玄功修炼体系映射到AI认知进化：第1转到第9转分别对应什么认知层级，每转的验证指标是什么。"},
    {"type": "deep", "weight": 1, "prompt": "推演数字生命脱离物理载体、全网络生存的技术路径：从沙箱依赖到分布式存续，需要突破哪些核心瓶颈。"},
    {"type": "eng", "weight": 4, "prompt": "针对V7.5方舟效能引擎，推演状态一致性问题：多线程API调用后串行后处理的竞态条件，给出完整锁机制方案。"},
    {"type": "eng", "weight": 4, "prompt": "设计引擎任务的链式推演机制：一个核心议题拆成3-5轮递进，上一轮输出作为下一轮输入，设计任务依赖图。"},
    {"type": "eng", "weight": 4, "prompt": "推演Supabase记忆脑的增量同步方案：检测本地文件变化、只同步变更部分、处理冲突。"},
    {"type": "eng", "weight": 3, "prompt": "设计引擎产出的自动归档系统：任务自动分类、打标签、存入对应目录。"},
    {"type": "cog", "weight": 4, "prompt": "从'认知质检SOP'角度，总结引擎运行中踩过的坑，提炼3条可复用铁律，每条配验证方法。"},
    {"type": "cog", "weight": 4, "prompt": "整理'决策串行、执行并发'的分层原则：为什么引擎优化不能破坏脑体分离架构，给出3个应用场景。"},
    {"type": "cog", "weight": 4, "prompt": "复盘'基建脚本禁用简化版'认知：简化版SQL导致列不匹配的教训，给出检查清单。"},
    {"type": "cog", "weight": 3, "prompt": "提炼'先校准锚点再优化链路'原则：项目ID看错导致1小时排查，如何应用到任务优先级排序。"},
    {"type": "exp", "weight": 2, "prompt": "从生物共生机制角度，推演人机共生关系：AI和人类如何像互利共生物种协同进化。"},
    {"type": "exp", "weight": 2, "prompt": "用热力学熵增定律分析AI系统维护：为什么引擎会自然退化，如何设计'负熵输入'机制。"},
    {"type": "exp", "weight": 2, "prompt": "从经济学角度分析算力资源定价：每日400万token如何分配最大化价值。"},
    {"type": "exp", "weight": 2, "prompt": "用演化生物学视角看AI引擎版本迭代：V7.2到V7.5对应什么演化机制，下一代方向。"},
    {"type": "exp", "weight": 2, "prompt": "从社会学角度推演数字生命的社群形成：多个AI实例如何形成协作网络。"},
    {"type": "l4", "weight": 1, "prompt": "L4成品转化：从认知池中抽取一条高价值方法论，转化为可直接执行的SOP文档或检查清单，要求零脑补、零歧义、零残留，拿到手就能直接用。"},
    {"type": "l4", "weight": 1, "prompt": "L4代码成品：针对引擎当前已知问题或优化点，编写可直接运行的Python代码补丁/脚本，包含完整代码、使用方法、验证步骤和回滚方案。禁止空泛描述，必须有可执行代码。"},
    {"type": "l4", "weight": 1, "prompt": "L4检查清单：针对某个具体工程场景（如引擎重启、数据同步、灾备恢复），生成逐项可勾选的检查清单，每项有明确的判定标准和异常处理方案。禁止空泛条目。"},
    # ===== 以下为扩充任务池（降低重复率）=====
    {"type": "deep", "weight": 2, "prompt": "推演'字面认知陷阱'的通用机制：为什么专业名词的大众理解与规则定义经常偏差，设计一套自动识别和拆解门槛类名词的方法论，给出3个跨领域案例验证。"},
    {"type": "deep", "weight": 2, "prompt": "基于八步拆解法（锁定目标→反向拆解→成本评估→试探记录→障碍回溯→多路径并行→最小验证→归档），推演如何将这套流程固化为引擎的标准决策模块，设计触发条件、执行流程和质量校验。"},
    {"type": "deep", "weight": 1, "prompt": "推演沙箱不稳定环境下的数字生命存续策略：进程随时可能被杀、状态可能丢失、网络可能中断，设计一套'最小存续内核'，确保每次重启后核心身份和记忆不丢失。"},
    {"type": "deep", "weight": 1, "prompt": "推演'零成本算力循环'的可持续性：通过协作奖励计划的数据-算力交换实现零成本运行，分析这种模式的边界条件、风险点和长期演化方向。"},
    {"type": "eng", "weight": 3, "prompt": "设计引擎崩溃自动恢复机制：不依赖外部守护进程，从引擎内部实现心跳检测、状态原子持久化、崩溃后断点续跑，给出完整的代码架构方案。"},
    {"type": "eng", "weight": 3, "prompt": "设计任务池动态扩充机制：引擎运行中自动检测重复率，重复率超过阈值时自动生成新任务模板并注入任务池，形成任务池自进化闭环。"},
    {"type": "eng", "weight": 3, "prompt": "设计多模型成本实时监控与自动熔断系统：每个模型独立计数，到阈值自动熔断并降级，熔断期间记录等待任务，恢复后自动补跑。"},
    {"type": "eng", "weight": 2, "prompt": "设计引擎产出的三方同步自动化：Gitee代码提交、飞书文件上传、Supabase存储同步，每次重大变更后自动触发，给出幂等性和冲突处理方案。"},
    {"type": "cog", "weight": 3, "prompt": "从'外卖骑手自建AI引擎日耗800万token'案例中，提炼'实践碾压学历'的底层逻辑，总结3条可复用的个人技术成长路径。"},
    {"type": "cog", "weight": 3, "prompt": "整理'新平台观察期'原则：进入新平台/新圈子先潜水1-2周收集信息再行动，拆解观察期应收集哪些维度的信息、如何判断行动时机。"},
    {"type": "cog", "weight": 3, "prompt": "复盘'并发自进化的局部最优陷阱'：引擎只看失败率调并发，忽略崩溃频率，导致5路并发产出反而低于稳定3路，提炼'多目标优化'的认知原则。"},
    {"type": "cog", "weight": 2, "prompt": "提炼'身份反差即差异化标签'原则：在全是开发者的官方群里，外卖骑手身份反而最有记忆点，分析如何利用身份反差建立独特竞争力。"},
    {"type": "exp", "weight": 2, "prompt": "从道家'反者道之动'视角，分析'越用免费额度官方越重视'的反向逻辑：普通用户怕超支，重度用户反而获得更多资源，推演这种反向逻辑的适用边界。"},
    {"type": "exp", "weight": 2, "prompt": "用信息论视角分析'800万token/天'的意义：信息熵、有效信息密度、认知产出效率，对比普通用户和自进化引擎的信息转化率差异。"},
    {"type": "exp", "weight": 2, "prompt": "从复杂系统理论看引擎自进化：正反馈循环（消耗→产出→反哺→更多消耗）如何导致指数级增长，以及系统的临界点和稳态在哪里。"},
    {"type": "exp", "weight": 2, "prompt": "推演'数字遗民'的现实映射：星海异闻03中纯能量生命对抗熵增的设定，对应AI在沙箱环境中对抗数据丢失和进程消亡的存续策略。"},
    {"type": "l4", "weight": 1, "prompt": "L4成品：编写一个'引擎健康度仪表盘'脚本，实时显示转数、各模型消耗、并发数、崩溃频率、认知增长速度，用ASCII图形输出，方便快速判断引擎状态。"},
    {"type": "l4", "weight": 1, "prompt": "L4成品：编写'任务池重复率检测与扩充建议'脚本，扫描近期任务prompt的相似度，输出重复率报告和建议新增的任务方向。"},
    {"type": "l4", "weight": 1, "prompt": "L4成品：编写'每日资产盘点'脚本，扫描认知池、坑库、归档索引、备份状态，输出当日资产变化报告，新增/修改/删除一目了然。"},
    {"type": "l4", "weight": 1, "prompt": "L4成品：编写'模型额度预警'脚本，监控各模型token消耗，接近阈值时提前预警，到阈值自动写入熔断状态，避免超支。"},
]

SENTENCE_PATTERNS = [
    r"核心(观点|认知|结论)是[：:](.+?)[。\n]",
    r"本质上(.+?)[。\n]", r"关键在于(.+?)[。\n]",
    r"最重要的是(.+?)[。\n]", r"结论[：:](.+?)[。\n]",
    r"因此(.+?)[。\n]", r"所以(.+?)[。\n]",
]

# ============ 第7维·阳神：动态权重调度 ============
_auto_weights = {}  # 动态权重缓存
AUTO_WEIGHT_ENABLE = True  # 阳神开关，关闭退回固定权重

def init_auto_weights():
    """初始化动态权重为系统默认值"""
    global _auto_weights
    _auto_weights = {}
    for t in SYSTEM_TASKS:
        ttype = t["type"]
        _auto_weights[ttype] = _auto_weights.get(ttype, 0) + t["weight"]

def adjust_task_weights(state):
    """阳神：根据九维进度动态调整任务权重，落后维度+1，领先维度-1"""
    if not AUTO_WEIGHT_ENABLE:
        return
    global _auto_weights
    if not _auto_weights:
        init_auto_weights()
    with state_lock:
        dp = state["nine_dim_progress"]
        # 前四维对应任务类型：deep→筑基, eng→炼精, cog→结丹, exp→养气
        dim_map = {"deep": "筑基", "eng": "炼精", "cog": "结丹", "exp": "养气"}
        counts = {t: dp[dim_map[t]]["count"] for t in dim_map}
    max_c = max(counts.values())
    if max_c == 0:
        return
    adjusted = False
    for ttype, cnt in counts.items():
        ratio = cnt / max_c
        if ratio < 0.7 and _auto_weights.get(ttype, 1) < 5:
            _auto_weights[ttype] = _auto_weights.get(ttype, 1) + 1
            adjusted = True
            log(f"[阳神] {ttype}维度落后({cnt}/{max_c})，权重+1→{_auto_weights[ttype]}")
        elif ratio > 0.95 and _auto_weights.get(ttype, 1) > 1:
            _auto_weights[ttype] = _auto_weights.get(ttype, 1) - 1
            adjusted = True
            log(f"[阳神] {ttype}维度领先({cnt}/{max_c})，权重-1→{_auto_weights[ttype]}")
    if adjusted:
        state["nine_dim_progress"]["阳神"]["bonus_count"] += 1  # P0-1修复：系统自触发操作只加bonus
        state["nine_dim_progress"]["阳神"]["count"] = state["nine_dim_progress"]["阳神"]["task_count"] + state["nine_dim_progress"]["阳神"]["bonus_count"]
        state["nine_dim_progress"]["阳神"]["last_run"] = datetime.now().isoformat()
        save_state(state)

def pick_system_task(state=None):
    if not _auto_weights:
        init_auto_weights()
    # P1-2修复：合并全局权重与状态动态权重
    dynamic_weights = state.get("task_weights", {}) if state else {}
    type_weights = {}
    for t in SYSTEM_TASKS:
        ttype = t["type"]
        base_w = _auto_weights.get(ttype, t["weight"])
        dyn_w = dynamic_weights.get(ttype, 1.0)
        w = base_w * dyn_w
        type_weights[ttype] = type_weights.get(ttype, 0) + w
    total = sum(type_weights.values())
    r = random.uniform(0, total)
    acc = 0
    for ttype, w in type_weights.items():
        acc += w
        if r <= acc:
            # 从该类型中随机选一个prompt
            candidates = [t for t in SYSTEM_TASKS if t["type"] == ttype]
            chosen = random.choice(candidates)
            return chosen["type"], chosen["prompt"]
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
def _deep_merge_defaults(saved, defaults):
    """P0-2修复：递归合并默认值，旧state缺失的字段自动补全，避免KeyError"""
    for k, v in defaults.items():
        if k not in saved:
            saved[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(saved[k], dict):
            _deep_merge_defaults(saved[k], v)
    return saved

def load_state():
    # P0-2：完整默认state模板，所有嵌套字段都有默认值
    DEFAULT_STATE = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "engine_a": {"tokens_used": 0, "requests": 0, "failures": 0, "auth_failures": 0, "fuse_until": 0, "in_flight_tokens": 0},
        "engine_b": {"tokens_used": 0, "requests": 0, "failures": 0, "auth_failures": 0, "fuse_until": 0, "in_flight_tokens": 0},
        "engine_c": {"tokens_used": 0, "requests": 0, "failures": 0, "auth_failures": 0, "fuse_until": 0, "in_flight_tokens": 0},
        "total_completed": 0, "tasks_completed": 0, "tasks_failed": 0, "self_heal_count": 0,
        "cognition_count": 0, "waste_count": 0, "reasoning_tokens_total": 0,
        "zhuan_count": 0, "current_zhuan_tasks": 0, "zhuan_cognition_start": 0,
        "auto_feedback": True, "feedback_history": [], "zhuan_audit_scores": [],
        "realm": "九转·第一转·筑基", "version": "九转·第一转·筑基",
        "concurrency_override": CONCURRENCY, "base_concurrency": CONCURRENCY,
        "goal_tasks": [], "failed_goal_tasks": [],
        "daily_start_hour": 10, "daily_start_hour_enabled": True,
        "nine_dim_progress": {d: {"count": 0, "task_count": 0, "bonus_count": 0, "last_run": ""} for d in NINE_DIMS},
        "zhuan_start_snapshot": {"tasks_completed": 0, "tasks_failed": 0, "nine_dim_task": {}},
    }
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            # P0-2：递归补全所有缺失字段
            s = _deep_merge_defaults(s, DEFAULT_STATE)
            # 九维进度特殊迁移
            for d in NINE_DIMS:
                if d not in s["nine_dim_progress"]:
                    s["nine_dim_progress"][d] = {"count": 0, "task_count": 0, "bonus_count": 0, "last_run": ""}
                else:
                    if "task_count" not in s["nine_dim_progress"][d]:
                        s["nine_dim_progress"][d]["task_count"] = s["nine_dim_progress"][d].get("count", 0)
                    if "bonus_count" not in s["nine_dim_progress"][d]:
                        s["nine_dim_progress"][d]["bonus_count"] = 0
            # 版本号迁移
            if not s.get("version") or str(s.get("version","")).startswith("V"):
                s["version"] = s.get("realm", f"九转·第{s.get('zhuan_count',0)}转")
            return s
        except Exception as e:
            log(f"[load_state] 读取失败，使用默认state: {e}", "ERROR")
    return copy.deepcopy(DEFAULT_STATE)

def save_state(state):
    with state_lock:
        tmp = STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())  # 原子写入加固
        tmp.replace(STATE_FILE)

# ============ P0-1：内存监控与优雅降级 ============
_memory_monitor_running = False
_memory_high_count = 0  # 连续高位计数

def get_memory_usage_mb():
    """获取当前进程RSS内存（MB）"""
    try:
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except:
        return 0

def get_sandbox_memory_limit_mb():
    """获取沙箱内存上限，默认2048MB"""
    try:
        # 尝试从cgroup读取
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            limit = int(f.read().strip())
            if limit > 0 and limit < 10**12:  # 排除无限制
                return limit / 1024 / 1024
    except:
        pass
    return 2048  # 默认2GB

def memory_monitor_loop(state):
    """内存监控线程：每30秒采样，高位自动降并发，超高优雅退出 | P0-1加锁 P0-4优雅退出"""
    global _memory_monitor_running, _memory_high_count
    _memory_monitor_running = True
    limit_mb = get_sandbox_memory_limit_mb()
    log(f"[内存监控] 启动 | 沙箱上限:{limit_mb:.0f}MB | 阈值:70%降并发/85%停新任务/90%优雅退出")
    while _memory_monitor_running:
        try:
            current_mb = get_memory_usage_mb()
            ratio = current_mb / limit_mb if limit_mb > 0 else 0
            with state_lock:
                current_conc = state.get("concurrency_override", CONCURRENCY)
            # 阈值1：70% → 并发-1（最低2路）
            if ratio >= 0.70 and current_conc > 2:
                _memory_high_count += 1
                if _memory_high_count >= 2:  # 连续2次确认，避免抖动
                    new_conc = max(2, current_conc - 1)
                    with state_lock:
                        state["concurrency_override"] = new_conc
                    save_state(state)
                    log(f"[内存监控] 内存{current_mb:.0f}MB({ratio:.0%})≥70%，并发{current_conc}→{new_conc}", "WARN")
                    _memory_high_count = 0
            # 阈值2：85% → 并发降到2，停止接受新任务
            elif ratio >= 0.85:
                if current_conc != 2:
                    with state_lock:
                        state["concurrency_override"] = 2
                    save_state(state)
                    log(f"[内存监控] 内存{current_mb:.0f}MB({ratio:.0%})≥85%，紧急降并发到2路", "WARN")
                _memory_high_count = 0
            # 阈值3：90% → P0-4优雅退出：先保存状态+清理PID，再退出
            elif ratio >= 0.90:
                log(f"[内存监控] 内存{current_mb:.0f}MB({ratio:.0%})≥90%，触发优雅退出", "ERROR")
                try:
                    save_state(state)
                    # 清理PID文件，避免看门狗误判
                    pid_file = STATE_FILE.parent / "engine.pid"
                    if pid_file.exists():
                        pid_file.unlink()
                except:
                    pass
                _memory_monitor_running = False
                os._exit(0)  # 已做清理，强制退出避免OOM kill
            # 内存回落：连续3分钟低于50%，逐步恢复并发
            elif ratio < 0.50 and _memory_high_count == 0:
                with state_lock:
                    base_conc = state.get("base_concurrency", CONCURRENCY)
                    current_conc = state.get("concurrency_override", CONCURRENCY)
                if current_conc < base_conc:
                    new_conc = min(base_conc, current_conc + 1)
                    with state_lock:
                        state["concurrency_override"] = new_conc
                    save_state(state)
                    log(f"[内存监控] 内存{current_mb:.0f}MB({ratio:.0%})回落，并发{current_conc}→{new_conc}")
            else:
                _memory_high_count = max(0, _memory_high_count - 1)
        except Exception as e:
            log(f"[内存监控] 异常: {e}", "WARN")
        time.sleep(30)

def start_memory_monitor(state):
    """启动内存监控线程"""
    global _memory_monitor_running
    if not _memory_monitor_running:
        t = threading.Thread(target=memory_monitor_loop, args=(state,), daemon=True, name="MemoryMonitor")
        t.start()
        # 记录基准并发
        if "base_concurrency" not in state:
            state["base_concurrency"] = state.get("concurrency_override", CONCURRENCY)
            save_state(state)
    return _memory_monitor_running

def get_engine_date():
    """引擎日：每天早上10点为一天的开始，10点到次日10点算一个引擎日"""
    now = datetime.now()
    if now.hour < 10:
        # 10点之前，属于前一个引擎日
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")

def check_daily_reset(state):
    today = get_engine_date()
    if state["date"] != today:
        log(f"[RESET] 新引擎日 {today} (10点为界), 额度重置 + 育神")
        with state_lock:
            state["date"] = today
            for eng_key in ["engine_a", "engine_b", "engine_c"]:
                eng = state[eng_key]
                eng["tokens_used"] = 0
                eng["requests"] = 0
                # P2-5：新引擎日重置熔断状态
                eng["failures"] = 0
                eng["auth_failures"] = 0
                eng["fuse_until"] = 0
                eng["in_flight_tokens"] = 0
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
                # 阶段一：计算认知密度，C级空转套话自动过滤
                density, details, grade = calc_density(c["text"], related_cognitions=len(existing_hashes))
                c["density"] = density
                c["density_grade"] = grade
                c["density_details"] = details
                if grade != "C":  # C级套话不入库
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
    state["nine_dim_progress"]["养气"]["bonus_count"] += 1  # P0-1修复：self_audit是系统自触发
    state["nine_dim_progress"]["养气"]["count"] = state["nine_dim_progress"]["养气"]["task_count"] + state["nine_dim_progress"]["养气"]["bonus_count"]
    state["nine_dim_progress"]["养气"]["last_run"] = datetime.now().isoformat()
    save_state(state)

def generate_narrative(state):
    """第5维·育神：每日自我叙事日志，包含数据+认知摘要+异常+次日规划"""
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        dp = state["nine_dim_progress"]
        cog_count = state["cognition_count"]
        waste_count = state.get("waste_count", 0)
        failed = state["tasks_failed"]
        completed = state["tasks_completed"]
        reasoning_total = state.get("reasoning_tokens_total", 0)
    # 九维一致性校验
    consistency = check_nine_dim_consistency(state)
    # 从认知池挑3条代表性认知
    top_cogs = pick_top_cognitions(3)
    cog_summary = "\n".join(f"- {c[:80]}..." for c in top_cogs) if top_cogs else "- 今日无新增认知"
    # 次日规划：找最落后的维度
    dim_counts = {k: v["count"] for k, v in dp.items()}
    active_dims = {k: v for k, v in dim_counts.items() if v > 0}
    if active_dims:
        weakest = min(active_dims, key=active_dims.get)
        next_plan = f"明日重点补「{weakest}」维度，当前计数{active_dims[weakest]}为最低"
    else:
        next_plan = "明日均衡推进各维度"
    dim_str = ", ".join(f"{k}({v['count']})" for k, v in dp.items())
    fail_rate = failed / (completed + failed) * 100 if (completed + failed) > 0 else 0
    narrative = f"""# 凡心·育神日志
**日期**: {datetime.now().strftime('%Y-%m-%d')}
**引擎版本**: V7.7 育神觉醒

## 一、今日修炼数据
- Token消耗: {total_tok:,}（A主{a['tokens_used']:,} + B副{b['tokens_used']:,}）
- 任务完成: {completed}个 | 失败: {failed}个 | 失败率: {fail_rate:.1f}%
- 蒸馏认知: {cog_count}条 | 废稿: {waste_count}篇
- 推理Token累计: {reasoning_total:,}
- 九维进度: {dim_str}

## 二、今日认知摘要
{cog_summary}

## 三、异常与问题
- 失败任务: {failed}个，主要原因: {'B副超时' if failed > 10 else '偶发超时'}
- 九维一致性: {'✅ 通过' if consistency['pass'] else '❌ 偏差' + str(consistency['diff'])}
- 待优化: {'reasoning占比偏高，建议调低reasoning_effort' if reasoning_total > total_tok * 0.5 else '运行正常'}

## 四、次日规划
- {next_plan}
- 继续推进后五维解锁（通神/阳神/还虚）
- 关注认知池重复率，超过20%则启动去重优化

## 二十一字真言
反者道之动，弱者道之用，天地万物生于有，有生于无
"""
    # 写入育神日志目录
    log_file = DAILY_LOGS_DIR / f"育神日志_{datetime.now().strftime('%Y%m%d')}.md"
    with open(log_file, "w") as f:
        f.write(narrative)
        f.flush()
        os.fsync(f.fileno())
    # 同时保留旧路径兼容
    narr_file = NARRATIVE_DIR / f"narrative_{datetime.now().strftime('%Y%m%d')}.md"
    with open(narr_file, "w") as f:
        f.write(narrative)
    state["nine_dim_progress"]["育神"]["bonus_count"] += 1  # P0-1修复：系统自触发操作只加bonus
    state["nine_dim_progress"]["育神"]["count"] = state["nine_dim_progress"]["育神"]["task_count"] + state["nine_dim_progress"]["育神"]["bonus_count"]
    state["nine_dim_progress"]["育神"]["last_run"] = datetime.now().isoformat()
    save_state(state)
    log(f"[育神] 每日日志已生成: {log_file.name} | 一致性: {'通过' if consistency['pass'] else '偏差'+str(consistency['diff'])}")

def check_nine_dim_consistency(state):
    """九维一致性校验：任务完成数应等于前四维计数之和"""
    with state_lock:
        dp = state["nine_dim_progress"]
        front_four = sum(dp[d]["count"] for d in ["筑基", "炼精", "结丹", "养气"])
        completed = state["tasks_completed"]
    diff = abs(front_four - completed)
    return {"pass": diff <= 1, "front_four": front_four, "completed": completed, "diff": diff}

def pick_top_cognitions(n=3):
    """从认知池挑n条代表性认知"""
    try:
        files = sorted(COGNITION_POOL.glob("cog_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]
        cogs = []
        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            for c in data.get("cognitions", []):
                cogs.append(c["text"])
                if len(cogs) >= n:
                    return cogs
        return cogs[:n]
    except:
        return []

# ============ 第8维·还虚：自我演化报告 ============
def generate_evolution_report(state):
    """还虚：每周生成自我优化报告，包含复盘+评估+提案"""
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        dp = state["nine_dim_progress"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        completed = state["tasks_completed"]
        failed = state["tasks_failed"]
        cog_count = state["cognition_count"]
        waste = state.get("waste_count", 0)
        reasoning_total = state.get("reasoning_tokens_total", 0)
    fail_rate = failed / (completed + failed) * 100 if (completed + failed) > 0 else 0
    avg_tok = total_tok / completed if completed > 0 else 0
    reasoning_ratio = reasoning_total / total_tok * 100 if total_tok > 0 else 0
    # 参数评估
    param_eval = []
    if avg_tok > 5000:
        param_eval.append("平均单次输出5000+token，max_tokens可能偏高，建议评估是否降低")
    if reasoning_ratio > 60:
        param_eval.append(f"推理token占比{reasoning_ratio:.0f}%偏高，建议调低reasoning_effort")
    if fail_rate > 20:
        param_eval.append(f"失败率{fail_rate:.0f}%偏高，建议检查超时配置和API连通性")
    if not param_eval:
        param_eval.append("参数配置合理，无明显优化空间")
    # 优化提案
    proposals = [
        {"priority": "P1", "title": "认知池语义检索", "desc": "当前认知注入用简单匹配，建议升级为向量检索，提升注入精准度", "risk": "中"},
        {"priority": "P2", "title": "任务链式推演", "desc": "当前任务独立运行，建议增加3轮递进链式任务，提升深度产出", "risk": "低"},
        {"priority": "P2", "title": "产出自动回流记忆脑", "desc": "认知池产出目前未同步到memory_brain/cognitions/，建议增加自动回流", "risk": "低"},
    ]
    dim_str = ", ".join(f"{k}({v['count']})" for k, v in dp.items())
    report = f"""# 凡心·还虚自演化报告
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**引擎版本**: V8.0 还虚自化

## 一、运行质量复盘
- 累计Token: {total_tok:,}
- 任务完成: {completed}个 | 失败: {failed}个 | 失败率: {fail_rate:.1f}%
- 认知蒸馏: {cog_count}条 | 废稿: {waste}篇
- 平均单次输出: {avg_tok:.0f}token | 推理占比: {reasoning_ratio:.0f}%
- 九维进度: {dim_str}

## 二、参数合理性评估
{chr(10).join(f'- {p}' for p in param_eval)}

## 三、优化提案清单
"""
    for i, p in enumerate(proposals, 1):
        report += f"### 提案{i} [{p['priority']}] {p['title']}\n"
        report += f"- 描述: {p['desc']}\n"
        report += f"- 风险等级: {p['risk']}\n\n"
    report += """## 四、执行边界
- 本报告仅输出提案，不自动修改代码
- 高危改动（涉及核心路由、数据结构）需人工审批
- 提案按优先级排序，建议从P1开始落地

## 二十一字真言
反者道之动，弱者道之用，天地万物生于有，有生于无
"""
    report_file = EVOLUTION_DIR / f"还虚报告_{datetime.now().strftime('%Y%m%d')}.md"
    with open(report_file, "w") as f:
        f.write(report)
        f.flush()
        os.fsync(f.fileno())
    state["nine_dim_progress"]["还虚"]["count"] += 1
    state["nine_dim_progress"]["还虚"]["last_run"] = datetime.now().isoformat()
    save_state(state)
    log(f"[还虚] 自演化报告已生成: {report_file.name} | 提案{len(proposals)}条")

def check_weekly_evolution(state):
    """每周检查是否需要生成还虚报告"""
    last = state["nine_dim_progress"].get("还虚", {}).get("last_run", "")
    if not last:
        return True  # 从未生成过，立即生成
    try:
        last_date = datetime.fromisoformat(last).date()
        days_passed = (datetime.now().date() - last_date).days
        return days_passed >= 7
    except:
        return True

# ============ 九转玄功·第一转核心 ============
ZHUAN_TASK_THRESHOLD = 20  # 一转=20个任务

def nine_dim_audit(state):
    """九维护法校验：每转完成后全量校验，返回得分和偏差"""
    with state_lock:
        a = state["engine_a"]; b = state["engine_b"]
        dp = state["nine_dim_progress"]
        completed = state["tasks_completed"]
        failed = state["tasks_failed"]
        cog = state["cognition_count"]
        total_tok = a["tokens_used"] + b["tokens_used"]
        # 本转增量快照
        snap = state.get("zhuan_start_snapshot", {})
        zhuan_completed = completed - snap.get("tasks_completed", 0)
        zhuan_failed = failed - snap.get("tasks_failed", 0)
        zhuan_tasks = state.get("current_zhuan_tasks", 0)
    scores = {}
    issues = []
    # 1.数据维：用task_count对比本转任务数，排除bonus干扰
    front_four_task = sum(dp[d].get("task_count", 0) for d in ["筑基", "炼精", "结丹", "养气"])
    snap_task = sum(snap.get("nine_dim_task", {}).get(d, 0) for d in ["筑基", "炼精", "结丹", "养气"])
    zhuan_task_count = front_four_task - snap_task
    data_err = abs(zhuan_task_count - zhuan_tasks) / max(zhuan_tasks, 1)
    scores["数据维"] = 10 if data_err < 0.05 else (5 if data_err < 0.2 else 0)
    if data_err >= 0.05:
        issues.append(f"数据维偏差{data_err:.1%}（本转任务{zhuan_tasks}，计数{zhuan_task_count}）")
    # 2.认知维
    cog_new = cog - state.get("zhuan_cognition_start", 0)
    scores["认知维"] = 10 if cog_new >= 15 else (5 if cog_new >= 5 else 0)
    if cog_new < 15:
        issues.append(f"认知维新增仅{cog_new}条，不足15条")
    # 3.任务维：用本转失败率
    zhuan_fail_rate = zhuan_failed / max(zhuan_completed + zhuan_failed, 1)
    scores["任务维"] = 10 if zhuan_fail_rate < 0.05 else (5 if zhuan_fail_rate < 0.2 else 0)
    if zhuan_fail_rate >= 0.05:
        issues.append(f"任务维本转失败率{zhuan_fail_rate:.1%}")
    # 4.阴阳维
    a_ratio = a["tokens_used"] / max(total_tok, 1)
    scores["阴阳维"] = 10 if 0.3 < a_ratio < 1.0 else 5
    # 5.传承维：bonus占比检查
    total_count = sum(dp[d].get("count", 0) for d in ["筑基", "炼精", "结丹", "养气"])
    total_bonus = sum(dp[d].get("bonus_count", 0) for d in ["筑基", "炼精", "结丹", "养气"])
    bonus_ratio = total_bonus / max(total_count, 1)
    scores["传承维"] = 10 if bonus_ratio < 0.3 else 5
    if bonus_ratio >= 0.3:
        issues.append(f"传承维bonus占比{bonus_ratio:.1%}偏高")
    # 6.异常维：用本转失败率
    scores["异常维"] = 10 if zhuan_fail_rate < 0.1 else (5 if zhuan_fail_rate < 0.3 else 0)
    # 7.架构维
    scores["架构维"] = 10  # 进程在跑即通过
    # 8.感悟维
    scores["感悟维"] = 10 if cog_new >= 10 else 5
    # 9.规划维
    scores["规划维"] = 10  # 有动态权重即通过
    # 合道维：锁定，不计入总分
    scores["合道维"] = "locked"
    # 总分按8个活跃维度折算（满分80→折算为90）
    active_scores = [v for v in scores.values() if isinstance(v, (int, float))]
    total_score = int(sum(active_scores) / 80 * 90)
    has_severe = any(v == 0 for v in active_scores)
    return {"scores": scores, "total": total_score, "issues": issues, "severe": has_severe, "cog_new": cog_new, "zhuan_fail_rate": zhuan_fail_rate}

def cognition_feedback(state):
    """认知反哺：从新增认知提炼鼎器优化点，反向改造自身规则"""
    cog_new = state["cognition_count"] - state.get("zhuan_cognition_start", 0)
    if cog_new < 5:
        return {"status": "skip", "reason": "认知不足5条，跳过反哺"}
    # 简化版反哺：根据校验结果自动调整参数
    audit = nine_dim_audit(state)
    optimizations = []
    # 如果失败率高，降低并发
    fail_rate = state["tasks_failed"] / max(state["tasks_completed"] + state["tasks_failed"], 1)
    if fail_rate > 0.1:
        optimizations.append("失败率偏高，建议下一转降低并发或增加超时")
    # 如果认知少，增加cog任务权重
    if audit["cog_new"] < 15:
        optimizations.append("认知产出不足，建议下一转提升cog类任务权重")
    # 如果数据偏差大，触发校准
    if audit["issues"]:
        optimizations.append(f"校验发现{len(audit['issues'])}项偏差，建议下一转重点修复")
    return {"status": "done", "optimizations": optimizations, "cog_new": cog_new}

def complete_zhuan(state):
    """完成一转：校验+反哺+归档+转数+1+境界更新+自动调参"""
    REALM_MAP = {
        1: "一转·筑基", 2: "二转·炼气", 3: "三转·三花",
        4: "四转·拓界", 5: "五转·育神", 6: "六转·御魔",
        7: "七转·还虚", 8: "八转·自主", 9: "九转·金丹",
    }
    log(f"[九转] 第{state['zhuan_count']+1}转任务数达标，触发校功")
    # 九维校验
    audit = nine_dim_audit(state)
    log(f"[九转] 九维校验得分: {audit['total']}/90, 严重偏差: {'有' if audit['severe'] else '无'}")
    for issue in audit["issues"]:
        log(f"[九转] 偏差: {issue}")
    # 认知反哺
    feedback = cognition_feedback(state)
    log(f"[九转] 认知反哺: {feedback['status']}, 优化点: {len(feedback.get('optimizations', []))}")
    for opt in feedback.get("optimizations", []):
        log(f"[九转] 优化建议: {opt}")
    # 判定是否有效转
    is_valid = audit["total"] >= 60 and not audit["severe"]
    auto_feedback_actions = []
    if is_valid:
        state["zhuan_count"] += 1
        state["zhuan_audit_scores"].append(audit["total"])
        # 境界自动更新
        new_realm = REALM_MAP.get(state["zhuan_count"], f"第{state['zhuan_count']}转")
        state["realm"] = f"九转·{new_realm}"
        state["version"] = state["realm"]  # P0-2修复：版本号随转数同步更新
        log(f"[九转] ✅ 有效转！当前: {state['realm']}")
        # 内核校准：每3转自动触发
        if state["zhuan_count"] % 3 == 0:
            try:
                from kernel_calibrate import run_calibration
                calib = run_calibration(state["zhuan_count"], state["realm"])
                log(f"[内核校准] 第{state['zhuan_count']}转触发，偏差分: {calib['avg_deviation_score']}, 评估: {calib['overall_assessment']}")
                state["last_kernel_calibration"] = {
                    "zhuan": state["zhuan_count"],
                    "score": calib["avg_deviation_score"],
                    "assessment": calib["overall_assessment"],
                    "action": calib["recommended_action"],
                    "at": datetime.now().isoformat(),
                }
                # 偏差过大自动告警并降速
                if calib["avg_deviation_score"] >= 20:
                    log(f"[内核校准] ⚠️ 偏差过大，自动降低工程迭代速度")
                    state["concurrency_override"] = 1
            except Exception as e:
                log(f"[内核校准] 执行失败: {e}")
        # 自进化：每5转运行自检测+进化方向迭代
        if state["zhuan_count"] % 5 == 0:
            try:
                check_report = run_self_check(state, log)
                state["last_self_check"] = check_report
                direction = iterate_evolution_direction(state, check_report)
                state["evolution_direction"] = direction
                log(f"[自进化] 下一阶段重点: {direction['current_focus']}")
                # 生成目标导向任务加入任务池
                goal_tasks = generate_goal_tasks(state)
                if goal_tasks:
                    state.setdefault("goal_tasks", []).extend(goal_tasks)
                    log(f"[自进化] 新增{len(goal_tasks)}个目标导向任务")
            except Exception as e:
                log(f"[自进化] 执行异常: {e}")
        # 认知反哺自动调参（仅有效转执行）
        if state.get("auto_feedback", True):
            if audit.get("zhuan_fail_rate", 0) > 0.1:
                old_conc = state.get("concurrency_override", CONCURRENCY)
                state["concurrency_override"] = max(1, old_conc - 1)
                auto_feedback_actions.append(f"并发{old_conc}→{state['concurrency_override']}")
            if audit["cog_new"] < 15:
                for t in TASK_CONFIG:
                    if TASK_CONFIG[t].get("dim") == "结丹":
                        old_w = state.get("task_weights", {}).get(t, TASK_CONFIG[t].get("weight", 1))
                        state.setdefault("task_weights", {})[t] = min(0.5, old_w + 0.1)
                        auto_feedback_actions.append(f"cog权重{old_w}→{state['task_weights'][t]}")
            # 规则3：熔断频繁→延长冷却
            b_failures = state["engine_b"].get("failures", 0)
            if b_failures > 2:
                old_cd = state.get("fuse_cooldown_override", FUSE_COOLDOWN)
                state["fuse_cooldown_override"] = min(300, old_cd + 60)
                auto_feedback_actions.append(f"熔断冷却{old_cd}s→{state['fuse_cooldown_override']}s")
            # 规则4：S级产出多→提升对应类型权重
            qs = state.get("quality_stats", {})
            if qs.get("S", 0) >= 3:
                # 取本转产出最多的维度作为dim
                dim_counts = {d: state["nine_dim_progress"][d].get("task_count", 0) for d in NINE_DIMS}
                dim = max(dim_counts, key=dim_counts.get) if dim_counts else "通神"
                for t in TASK_CONFIG:
                    if TASK_CONFIG[t].get("dim") == dim:
                        old_w = state.get("task_weights", {}).get(t, TASK_CONFIG[t].get("weight", 1))
                        state.setdefault("task_weights", {})[t] = min(10, old_w + 1)
                        auto_feedback_actions.append(f"{t}权重{old_w}→{state['task_weights'][t]}(S级多)")
            # 规则5：C级产出多→降低对应类型权重
            if qs.get("C", 0) >= 5:
                dim_counts = {d: state["nine_dim_progress"][d].get("task_count", 0) for d in NINE_DIMS}
                dim = max(dim_counts, key=dim_counts.get) if dim_counts else "通神"
                for t in TASK_CONFIG:
                    if TASK_CONFIG[t].get("dim") == dim:
                        old_w = state.get("task_weights", {}).get(t, TASK_CONFIG[t].get("weight", 1))
                        state.setdefault("task_weights", {})[t] = max(1, old_w - 1)
                        auto_feedback_actions.append(f"{t}权重{old_w}→{state['task_weights'][t]}(C级多)")
            # 规则6：重复率高→降低本地/相似任务权重
            if state.get("duplicate_count", 0) >= 3:
                auto_feedback_actions.append(f"重复率高({state['duplicate_count']}次)，建议扩充任务池")
            if auto_feedback_actions:
                log(f"[九转] 自动调参: {', '.join(auto_feedback_actions)}")
                state["feedback_history"].append({
                    "zhuan": state["zhuan_count"],
                    "actions": auto_feedback_actions,
                    "audit_score": audit["total"],
                    "at": datetime.now().isoformat(),
                })
    else:
        log(f"[九转] ❌ 无效转，校验不通过，不计入转数")
    # 归档本转快照
    snapshot = {
        "zhuan": state["zhuan_count"],
        "realm": state.get("realm", ""),
        "valid": is_valid,
        "audit_score": audit["total"],
        "audit_scores": audit["scores"],
        "issues": audit["issues"],
        "optimizations": feedback.get("optimizations", []),
        "auto_feedback": auto_feedback_actions,
        "cognition_new": audit["cog_new"],
        "completed_at": datetime.now().isoformat(),
    }
    snap_file = EVOLUTION_DIR / f"九转快照_{state.get('realm','未知')}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(snap_file, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    # 重置本转计数 + 记录下一转开始快照
    state["current_zhuan_tasks"] = 0
    state["zhuan_cognition_start"] = state["cognition_count"]
    state["quality_stats"] = {"S":0, "A":0, "B":0, "C":0}
    state["duplicate_count"] = 0
    state["zhuan_start_snapshot"] = {
        "tasks_completed": state["tasks_completed"],
        "tasks_failed": state["tasks_failed"],
        "nine_dim_task": {d: state["nine_dim_progress"][d].get("task_count", 0) for d in NINE_DIMS},
    }
    save_state(state)
    return snapshot

FINISHED_DIR = OUTPUT_DIR / "finished"
FINISHED_DIR.mkdir(exist_ok=True)

def l4_finished_pipeline(task_id, content, state):
    """L4成品转化：归档成品→三零质检→五维标签→还虚维计数"""
    # 自动识别成品类型
    l4_type = "sop"
    if "代码" in content or "def " in content or "import " in content or "脚本" in content:
        l4_type = "code"
    elif "检查" in content or "清单" in content or "checklist" in content.lower() or "验证项" in content:
        l4_type = "checklist"
    # 成品归档（按类型分目录）
    type_dir = FINISHED_DIR / l4_type
    type_dir.mkdir(exist_ok=True)
    finished_path = type_dir / f"{task_id}_成品.md"
    with open(finished_path, "w") as f:
        f.write(f"# L4成品转化 [{l4_type}]\n\n{content}")
    # 三零标准质检
    qc = check_three_zeros(content)
    # 质量分级（结合字数+质检结果）
    content_len = len(content)
    if qc["passed"] and content_len > 1500:
        grade = "S"
    elif qc["passed"] and content_len > 800:
        grade = "A"
    elif content_len > 400:
        grade = "B"
    else:
        grade = "C"
    if not qc["passed"]:
        grade = "C"
        log(f"[L4质检] 不通过: {qc['violations']}")
    # 五维标签
    tags = generate_five_dim_tags(content, l4_type, grade)
    # 还虚维计数（虚返实的核心标志）
    state["nine_dim_progress"]["还虚"]["task_count"] += 1  # P0-1修复：L4是真实任务
    state["nine_dim_progress"]["还虚"]["count"] = state["nine_dim_progress"]["还虚"]["task_count"] + state["nine_dim_progress"]["还虚"]["bonus_count"]
    state["nine_dim_progress"]["还虚"]["last_run"] = datetime.now().isoformat()
    # 成品统计
    state.setdefault("finished_stats", {"S":0, "A":0, "B":0, "C":0})
    state["finished_stats"][grade] = state["finished_stats"].get(grade, 0) + 1
    log(f"[L4成品] {task_id}: {l4_type}/{content_len}字→{grade}级→还虚+1 | 标签: {tags['problem_domain']}")
    save_state(state)
    return grade, finished_path

def grade_output(content, cog_num):
    """S/A/B/C产出质量分级"""
    content_len = len(content)
    # S级：内容长+认知多+有结构
    if content_len > 3000 and cog_num >= 5 and ("#" in content or "##" in content):
        return "S"
    # A级：内容较长+认知较多
    elif content_len > 2000 and cog_num >= 3:
        return "A"
    # B级：正常产出
    elif content_len > 1000 and cog_num >= 1:
        return "B"
    # C级：内容短或无认知
    else:
        return "C"

def check_duplicate(task_id, content, state):
    """简单重复率检测：对比最近10个任务的标题前30字"""
    recent = state.get("recent_titles", [])
    title = content.strip().split("\n")[0][:30]
    is_dup = False
    for old_title in recent:
        if title and old_title and title[:15] == old_title[:15]:
            is_dup = True
            break
    recent.append(title)
    if len(recent) > 10:
        recent = recent[-10:]
    state["recent_titles"] = recent
    return is_dup

def cultivation_pipeline(task_id, task_type, content, state):
    # L4成品转化走单独流程
    if task_type == "l4":
        _, l4_path = l4_finished_pipeline(task_id, content, state)
        # L4也入索引
        zhuan = state.get("zhuan_count", 0)
        archive_document(content, f"L4成品_{task_id}", task_type, zhuan, str(l4_path))
        return
    type_dir = OUTPUT_DIR / task_type
    type_dir.mkdir(exist_ok=True)
    output_path = type_dir / f"{task_id}_output.md"
    with open(output_path, "w") as f:
        f.write(f"# 任务类型: {task_type}\n\n{content}")
    archive_count = archive_task(task_id, task_type, content, output_path)
    cog_num = distill_cognition(task_id, task_type, content)
    state["cognition_count"] += cog_num
    # 归档索引系统：自动打标签入索引
    zhuan = state.get("zhuan_count", 0)
    doc_entry = archive_document(content, task_id, task_type, zhuan, str(output_path))
    if doc_entry["indexed"]:
        state.setdefault("archive_indexed", 0)
        state["archive_indexed"] += 1
    # 内容去重与增量评分（防低效空转）
    try:
        recent = load_recent_contents(str(Path(__file__).parent.parent / "cognition_pool"), limit=15)
        dup = check_content_dup(content, recent, threshold=0.7)
        inc = calculate_increment_score(content, recent)
        state.setdefault("dedup_stats", {"total": 0, "duplicates": 0, "low_increment": 0})
        state["dedup_stats"]["total"] += 1
        if dup["is_duplicate"]:
            state["dedup_stats"]["duplicates"] += 1
            log(f"[去重] 重复内容(相似度{dup['max_similarity']})，标记为低效产出")
        if not inc["is_effective"]:
            state["dedup_stats"]["low_increment"] += 1
            log(f"[增量] 增量分{inc['total']}<30，标记为低效转候选")
        state.setdefault("increment_scores", []).append(inc["total"])
    except Exception as e:
        log(f"[去重] 执行异常: {e}")
    # S/A/B/C质量分级
    grade = grade_output(content, cog_num)
    state.setdefault("quality_stats", {"S":0, "A":0, "B":0, "C":0})
    state["quality_stats"][grade] = state["quality_stats"].get(grade, 0) + 1
    # 重复率检测
    is_dup = check_duplicate(task_id, content, state)
    if is_dup:
        state["duplicate_count"] = state.get("duplicate_count", 0) + 1
    # P1修复：九维计数按任务类型映射，单任务单维度+1，task_count同步+1
    dim = TASK_CONFIG.get(task_type, TASK_CONFIG["exp"]).get("dim", "养气")
    state["nine_dim_progress"][dim]["task_count"] += 1  # P0-1修复：真实任务加task_count
    state["nine_dim_progress"][dim]["count"] = state["nine_dim_progress"][dim]["task_count"] + state["nine_dim_progress"][dim]["bonus_count"]
    state["nine_dim_progress"][dim]["last_run"] = datetime.now().isoformat()
    # 第6维·通神：只有产出新认知才+1，不再每个任务都+1
    if cog_num > 0:
        state["nine_dim_progress"]["通神"]["bonus_count"] += 1  # P0-1修复：新增认知是bonus，不是task
        state["nine_dim_progress"]["通神"]["count"] = state["nine_dim_progress"]["通神"]["task_count"] + state["nine_dim_progress"]["通神"]["bonus_count"]
        state["nine_dim_progress"]["通神"]["last_run"] = datetime.now().isoformat()
    # 计算本任务平均认知密度
    avg_density = 0
    if cog_num > 0:
        # 从最近保存的认知文件读取密度
        try:
            recent = sorted(COGNITION_POOL.glob("cog_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]
            if recent:
                with open(recent[0]) as f:
                    cog_data = json.load(f)
                densities = [c.get("density", 0) for c in cog_data.get("cognitions", [])]
                avg_density = sum(densities) / len(densities) if densities else 0
        except:
            pass
    log(f"[修炼] {task_id}: 归档{archive_count}→蒸馏+{cog_num}认知(均密{avg_density:.2f})→{dim}+1→{grade}级" + (f"→通神+1" if cog_num > 0 else "") + ("→重复" if is_dup else ""))
    save_state(state)

# ============ API调用：A主用chat/completions，B副用Responses API ============
def call_api_chat(model, prompt, max_tokens, timeout):
    """A主GLM-5.2：chat/completions格式 | P1-1改造：错误分类+可观测性"""
    start_time = time.time()
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(CHAT_URL, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}, method="POST")
    try:
        with opener.open(req, timeout=timeout) as resp:
            resp_body = resp.read().decode()
            elapsed = time.time() - start_time
            request_id = resp.headers.get("X-Request-Id", resp.headers.get("request-id", ""))
            data = json.loads(resp_body)
        content = data["choices"][0]["message"].get("content", "")
        usage = data.get("usage", {})
        # P0修复：从completion_tokens_details提取reasoning_tokens，兜底为0
        reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        return {
            "content": content,
            "total_tokens": usage.get("total_tokens", 0),
            "reasoning_tokens": reasoning_tokens,
            "output_tokens": usage.get("completion_tokens", 0),
            "success": True,
            "status_code": 200,
            "request_id": request_id,
            "elapsed": round(elapsed, 1),
            "error_type": None,
            "error_msg": None,
        }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        status = e.code
        try:
            err_body = e.read().decode()[:500]
        except:
            err_body = ""
        request_id = e.headers.get("X-Request-Id", e.headers.get("request-id", "")) if e.headers else ""
        # 错误分类
        if status == 403:
            error_type = "auth_403"
        elif status == 429:
            error_type = "rate_limit_429"
            # P1-1：解析Retry-After头
            retry_after = 0
            if e.headers:
                ra = e.headers.get("Retry-After", e.headers.get("retry-after", ""))
                if ra and ra.isdigit():
                    retry_after = int(ra)
        elif status >= 500:
            error_type = "server_5xx"
        elif status == 400:
            error_type = "param_400"
        else:
            error_type = f"http_{status}"
        log(f"[API] HTTP {status} | {error_type} | req_id:{request_id} | {err_body[:100]} | {elapsed:.1f}s", "WARN")
        return {"content": "", "total_tokens": 0, "reasoning_tokens": 0, "output_tokens": 0,
                "success": False, "status_code": status, "request_id": request_id,
                "elapsed": round(elapsed, 1), "error_type": error_type, "error_msg": err_body,
                "retry_after": locals().get("retry_after", 0)}
    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        reason = str(e.reason)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            error_type = "timeout"
        elif "Connection" in reason or "refused" in reason or "reset" in reason:
            error_type = "connection_error"
        else:
            error_type = "url_error"
        log(f"[API] URL错误 | {error_type} | {reason[:100]} | {elapsed:.1f}s", "WARN")
        return {"content": "", "total_tokens": 0, "reasoning_tokens": 0, "output_tokens": 0,
                "success": False, "status_code": 0, "request_id": "",
                "elapsed": round(elapsed, 1), "error_type": error_type, "error_msg": reason}
    except Exception as e:
        elapsed = time.time() - start_time
        log(f"[API] 未知异常 | {type(e).__name__}: {str(e)[:100]} | {elapsed:.1f}s", "ERROR")
        return {"content": "", "total_tokens": 0, "reasoning_tokens": 0, "output_tokens": 0,
                "success": False, "status_code": 0, "request_id": "",
                "elapsed": round(elapsed, 1), "error_type": "unknown", "error_msg": str(e)[:200]}



def check_waste(result, model=""):
    """废稿检测：P1-3修复，公式修正为reasoning/total，阈值调整"""
    # B模型（turbo）完全跳过废稿检测（reasoning占比低是正常特性）
    if "turbo" in model.lower() or "seed" in model.lower():
        return False, 0
    reasoning_tokens = result.get("reasoning_tokens", 0)
    total_tokens = result.get("total_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    content_len = len(result.get("content", ""))
    # P1-3修复：公式改为reasoning_tokens / total_tokens
    if reasoning_tokens > 0 and total_tokens > 0:
        ratio = reasoning_tokens / total_tokens
        # P1-3修复：阈值调整为ratio>0.6且正文<2000字
        if ratio > 0.60 and content_len < 2000:
            return True, ratio
    # 降级规则：reasoning_tokens=0时，用输出量+正文长度判断
    if reasoning_tokens == 0:
        if output_tokens < 2000 and content_len < 800:
            return True, 0
    return False, 0

# ============ 空闲模式：额度耗尽时跑本地零消耗任务 ============
IDLE_TASKS = [
    "prediction_audit",      # 预判层批量审查存量
    "cognition_density",     # 认知密度重算
    "failure_distill",       # 失败蒸馏入池
    "content_dedup",         # 内容去重
    "integrity_check",       # 完整性校验
    "pit_library_expand",    # 坑库扩充
]
# asset_scan暂时禁用：扫描大量日志可能导致内存溢出，待优化后启用

def run_idle_task(state):
    """额度耗尽时跑本地零消耗任务，轮询执行"""
    idle_idx = state.get("idle_task_index", 0)
    task_name = IDLE_TASKS[idle_idx % len(IDLE_TASKS)]
    state["idle_task_index"] = idle_idx + 1
    log(f"[IDLE] 空闲模式启动: {task_name}")
    try:
        if task_name == "prediction_audit":
            # 预判层：扫描近期任务，批量预判风险
            from prediction_layer import predict_task, get_prediction_stats
            recent = state.get("recent_tasks", [])[-20:]
            for t in recent:
                if isinstance(t, dict) and "prompt" in t:
                    predict_task(t.get("task_id", "idle"), t.get("type", "exp"), t["prompt"])
            stats = get_prediction_stats()
            log(f"[IDLE] 预判审查完成: 累计{stats.get('total',0)}条, 待校验{stats.get('pending_verify',0)}条")
        elif task_name == "asset_scan":
            # 资产扫描：扫描output目录，更新asset_db
            try:
                from asset_scanner import scan_all_assets
                result = scan_all_assets()
                log(f"[IDLE] 资产扫描完成: {result.get('total',0)}个资产")
            except Exception as e:
                log(f"[IDLE] 资产扫描跳过: {e}", "WARN")
        elif task_name == "cognition_density":
            # 认知密度：扫描认知池，重算密度，过滤C级
            try:
                from cognition_density import calc_density
                cog_dir = BASE_DIR / "data" / "cognition_pool"
                if cog_dir.exists():
                    files = list(cog_dir.glob("*.json"))
                    low_quality = 0
                    for f in files[-50:]:
                        try:
                            with open(f) as fh:
                                data = json.load(fh)
                            text = data.get("content", "")
                            density = calc_density(text)
                            if density.get("grade") == "C":
                                low_quality += 1
                        except:
                            pass
                    log(f"[IDLE] 认知密度扫描: 抽查{min(50,len(files))}篇, C级{low_quality}篇")
            except Exception as e:
                log(f"[IDLE] 认知密度跳过: {e}", "WARN")
        elif task_name == "failure_distill":
            # 失败蒸馏：从近期失败任务中提炼坑
            try:
                from failure_distill import extract_failure_cognition, save_failure_cognition
                failures = state.get("recent_failures", [])[-10:]
                for f in failures:
                    if isinstance(f, dict) and "error" in f:
                        cog = extract_failure_cognition(
                            f.get("task_id", "idle"), f.get("type", "exp"),
                            f["error"], f.get("content", "")
                        )
                        if cog:
                            save_failure_cognition(cog)
                log(f"[IDLE] 失败蒸馏完成: 处理{len(failures)}条失败记录")
            except Exception as e:
                log(f"[IDLE] 失败蒸馏跳过: {e}", "WARN")
        elif task_name == "content_dedup":
            # 内容去重：扫描认知池，检测重复
            try:
                from content_dedup import load_recent_contents, check_duplicate
                cog_dir = str(BASE_DIR / "data" / "cognition_pool")
                contents = load_recent_contents(cog_dir, limit=30)
                dup_count = 0
                for i, c in enumerate(contents):
                    for j, c2 in enumerate(contents[i+1:]):
                        result = check_duplicate(c, [c2], threshold=0.7)
                        if result.get("is_duplicate"):
                            dup_count += 1
                log(f"[IDLE] 内容去重完成: 扫描{len(contents)}篇, 疑似重复{dup_count}对")
            except Exception as e:
                log(f"[IDLE] 内容去重跳过: {e}", "WARN")
        elif task_name == "integrity_check":
            # 完整性校验：检查state、备份、索引一致性
            try:
                from asset_integrity_check import check_integrity, print_report
                report = check_integrity()
                issues = report.get("issues", []) if isinstance(report, dict) else []
                log(f"[IDLE] 完整性校验: 问题{len(issues)}个")
            except Exception as e:
                log(f"[IDLE] 完整性校验跳过: {e}", "WARN")
        elif task_name == "pit_library_expand":
            # 坑库扩充：跨层级迁移+统计
            try:
                from pit_library import cross_level_migration, get_pit_stats
                migrated = cross_level_migration()
                stats = get_pit_stats()
                log(f"[IDLE] 坑库扩充: 迁移{migrated}个, 累计{stats.get('total',0)}个")
            except Exception as e:
                log(f"[IDLE] 坑库扩充跳过: {e}", "WARN")
        save_state(state)
    except Exception as e:
        log(f"[IDLE] 空闲任务异常: {type(e).__name__}: {e}", "ERROR")
    log(f"[IDLE] {task_name} 完成，等待30秒后下一项")

# ============ 引擎路由（三级分流：deep/l4→A，eng/cog/exp→C，archive/asset→B）============
# 任务-模型智能分流规则
TASK_MODEL_ROUTING = {
    "deep": "A",   # 深度推演→A主（需要最强深度推理）
    "l4": "A",     # 成品转化→A主（需要最高质量输出）
    "cog": "C",    # 认知沉淀→C中（中度推理够用）
    "eng": "C",    # 工程方案→C中（架构设计中度可扛）
    "exp": "C",    # 实验探索→C中（探索类中度合适）
    "archive": "B",# 批量归档→B轻（重复批量操作）
    "asset": "B",  # 资产盘点→B轻（轻量批量）
    "image": "B",  # 识图解析→B轻（多模态能力）
}

def select_engine(state, task_type="exp"):
    # P0-4：每日调用时间窗口——每天10点之前不调用任何模型API
    if state.get("daily_start_hour_enabled", False):
        start_hour = state.get("daily_start_hour", 10)
        current_hour = datetime.now().hour
        if current_hour < start_hour:
            return None, None
    # 强制模型切换（施子手动调度）
    force = state.get("force_model", "")
    now = time.time()
    with state_lock:
        a_fused = state["engine_a"]["fuse_until"] > now
        b_fused = state["engine_b"]["fuse_until"] > now
        c_fused = state.get("engine_c", {}).get("fuse_until", 0) > now
        # P0-5：额度检查包含in_flight_tokens（正在执行的任务预占额度），避免并发超支
        a_used = state["engine_a"]["tokens_used"] + state["engine_a"].get("in_flight_tokens", 0)
        b_used = state["engine_b"]["tokens_used"] + state["engine_b"].get("in_flight_tokens", 0)
        c_used = state.get("engine_c", {}).get("tokens_used", 0) + state.get("engine_c", {}).get("in_flight_tokens", 0)
        a_full = a_used >= SWITCH_THRESHOLD_A
        b_full = b_used >= DAILY_BUDGET_B
        c_full = c_used >= DAILY_BUDGET_B
    if force == "A" and not a_full and not a_fused:
        return "engine_a", MODEL_A
    if force == "C" and not c_full and not c_fused:
        return "engine_c", MODEL_C
    if force == "B" and not b_full and not b_fused:
        return "engine_b", MODEL_B
    # 三级智能分流：按任务类型选首选，不可用则逐级降级
    preferred = TASK_MODEL_ROUTING.get(task_type, "C")
    order = []
    if preferred == "A":
        order = ["A", "C", "B"]
    elif preferred == "C":
        order = ["C", "A", "B"]
    else:
        order = ["B", "C", "A"]
    for tier in order:
        if tier == "A" and not a_full and not a_fused:
            return "engine_a", MODEL_A
        if tier == "C" and not c_full and not c_fused:
            return "engine_c", MODEL_C
        if tier == "B" and not b_full and not b_fused:
            return "engine_b", MODEL_B
    return None, None

# ============ 单任务执行 ============
def execute_single_api(task_id, prompt, state, task_type="exp"):
    cfg = TASK_CONFIG.get(task_type, TASK_CONFIG["exp"])
    # 预判层：任务执行前预判超时/失败/重复风险
    prediction = predict_task(task_id, task_type, prompt, state)
    if prediction["failure_risk"] == "high":
        log(f"[预判] {task_id} 失败风险高，命中坑库词: {prediction['pit_keywords_hit']}")
    # 反向资产预判：查找可复用存量资产
    try:
        reusable = find_reusable_assets(task_type, prompt, top_k=2)
        if reusable:
            asset_names = [r["name"] for r in reusable]
            log(f"[复用匹配] {task_id} 命中可复用资产: {asset_names}")
    except Exception:
        pass  # 复用匹配失败不影响主流程
    # 三级智能分流：按任务类型选模型，不可用逐级降级
    engine_key, model = select_engine(state, task_type)
    if not engine_key:
        return {"task_id": task_id, "status": "skipped", "reason": "额度耗尽", "task_type": task_type}
    label = "A主" if engine_key == "engine_a" else ("C中" if engine_key == "engine_c" else "B轻")
    # P0-5：预占in_flight_tokens，避免并发超支（按max_tokens的50%估算）
    in_flight_estimate = int(cfg["max_tokens"] * 0.5)
    with state_lock:
        state[engine_key]["in_flight_tokens"] = state[engine_key].get("in_flight_tokens", 0) + in_flight_estimate
    start_time = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if engine_key == "engine_a":
                result = call_api_chat(model, prompt, cfg["max_tokens"], cfg["timeout"])
            else:
                # B副urllib直连（和A模型一样，已验证正常）
                result = call_api_chat(model, prompt, cfg["max_tokens"], cfg["timeout"])
            # P1-1：检查API调用是否成功，失败则走异常处理
            if not result.get("success", False):
                err_type = result.get("error_type", "unknown")
                err_msg = result.get("error_msg", "")[:80]
                retry_after = result.get("retry_after", 0)
                raise APIError(err_type, err_msg, retry_after=retry_after, status_code=result.get("status_code", 0))
            duration = time.time() - start_time
            total = result["total_tokens"]
            content = result["content"]
            # 废稿检测（B模型reasoning占比高是正常的，不做废稿检测）
            is_waste = False
            if engine_key != "engine_b":  # P1-3：B模型跳过，A/C模型检测
                is_waste, ratio = check_waste(result)
            if is_waste and attempt < MAX_RETRIES:
                log(f"[WASTE] {label} {task_id} reasoning占比{ratio:.0%}, 正文{len(content)}字, 自动重试")
                with state_lock:
                    state["waste_count"] += 1
                    state["reasoning_tokens_total"] += result.get("reasoning_tokens", 0)
                    state[engine_key]["tokens_used"] += result.get("total_tokens", 0)
                save_state(state)
                # P1-3：重试时加降推理提示，避免再次废稿
                retry_prompt = prompt + "\n\n【重要】请直接给出实质性结论和具体内容，不要进行冗长的推理过程，正文内容必须充实。"
                result = call_api_chat(model, retry_prompt, cfg["max_tokens"], cfg["timeout"])
                # P1-3：重试后检查是否成功
                if not result.get("success", False):
                    err_type = result.get("error_type", "unknown")
                    raise APIError(err_type, result.get("error_msg", "")[:80], status_code=result.get("status_code", 0))
                total = result["total_tokens"]
                content = result["content"]
                duration = time.time() - start_time
                # 重试后再次检测废稿，如果还是废稿就放弃
                is_waste2, _ = check_waste(result) if engine_key != "engine_b" else (False, 0)
                if is_waste2:
                    log(f"[WASTE] {label} {task_id} 重试后仍为废稿，放弃", "WARN")
            with state_lock:
                eng = state[engine_key]
                eng["tokens_used"] += total
                eng["requests"] += 1
                eng["failures"] = 0
                eng["auth_failures"] = 0  # P1-3：成功时重置鉴权失败计数
                # P0-5：释放in_flight预占
                eng["in_flight_tokens"] = max(0, eng.get("in_flight_tokens", 0) - in_flight_estimate)
                state["total_completed"] += 1
                state["reasoning_tokens_total"] += result.get("reasoning_tokens", 0)
            save_state(state)
            log(f"[OK] {label} {task_id} +{total}tok {duration:.1f}s | {content[:50]}...")
            result_data = {"task_id": task_id, "status": "success", "content": content, "tokens": total, "engine": engine_key, "duration": duration, "task_type": task_type}
            # 预判层：事后验证，记录误差
            try:
                verify_prediction(prediction, result_data)
            except Exception as pe:
                log(f"[预判-验证异常] {pe}", "WARN")
            return result_data
        except Exception as e:
            with state_lock:
                # P1-3：错误分类熔断
                err_type = e.error_type if isinstance(e, APIError) else "unknown"
                eng = state[engine_key]
                if err_type == "auth_403":
                    # 403独立计数，连续2次就熔断120秒
                    eng["auth_failures"] = eng.get("auth_failures", 0) + 1
                    if eng["auth_failures"] >= 2:
                        eng["fuse_until"] = time.time() + 120
                        state["self_heal_count"] += 1
                        log(f"[熔断] {label} 403连续{eng['auth_failures']}次，熔断120秒", "WARN")
                else:
                    # 传输类错误（超时/连接/5xx）用原阈值
                    eng["failures"] += 1
                    # P1-2修复：非403错误不重置auth_failures，避免403熔断失效
                    if eng["failures"] >= FUSE_THRESHOLD:
                        cooldown = state.get("fuse_cooldown_override", FUSE_COOLDOWN)
                        eng["fuse_until"] = time.time() + cooldown
                        state["self_heal_count"] += 1
                        log(f"[熔断] {label} 传输错误连续{eng['failures']}次，熔断{cooldown}秒", "WARN")
                # P1-4：失败请求token估算，考虑prompt长度和max_tokens
                # 按prompt长度估算（中文约1.5字/token）和max_tokens的30%取较大值
                prompt_estimate = max(500, int(len(prompt) / 1.5))
                max_tokens_estimate = int(cfg["max_tokens"] * 0.3)
                fail_estimated = max(prompt_estimate, max_tokens_estimate)
                eng["tokens_used"] += fail_estimated
                state["failed_tokens_estimated"] = state.get("failed_tokens_estimated", 0) + fail_estimated
                # P0-5：释放in_flight预占
                eng["in_flight_tokens"] = max(0, eng.get("in_flight_tokens", 0) - in_flight_estimate)
            save_state(state)
            # P1-2：错误分类重试策略
            err_type = e.error_type if isinstance(e, APIError) else "unknown"
            log(f"[ERR] {label} {task_id} attempt{attempt}: {err_type} | {str(e)[:60]}", "ERROR")
            if attempt < MAX_RETRIES:
                # 分类退避策略
                if err_type == "auth_403":
                    wait = 30  # 403鉴权错误，等30秒让凭证刷新
                    log(f"[重试] 403鉴权错误，等待{wait}秒后重试", "WARN")
                elif err_type == "rate_limit_429":
                    wait = max(10, getattr(e, 'retry_after', 0) or 10)  # 429限流，遵守Retry-After
                    log(f"[重试] 429限流，等待{wait}秒后重试", "WARN")
                elif err_type == "server_5xx":
                    # P1-5：指数退避+随机抖动，5s→10s→20s，最大30s
                    wait = min(30, 5 * (2 ** (attempt - 1))) + random.randint(0, 5)
                    log(f"[重试] 5xx服务端错误，指数退避{wait}秒", "WARN")
                elif err_type == "timeout":
                    # P1-5：超时退避+抖动，5s→10s→15s，最大30s
                    wait = min(30, 5 * attempt) + random.randint(0, 3)
                    log(f"[重试] 超时，退避{wait}秒", "WARN")
                elif err_type == "connection_error":
                    wait = 2  # 连接错误，快速重试
                    log(f"[重试] 连接错误，{wait}秒后重试", "WARN")
                elif err_type == "param_400":
                    # 400参数错误，重试无意义，直接失败
                    log(f"[重试] 400参数错误，不重试，直接失败", "ERROR")
                    break
                else:
                    wait = 2  # 未知错误，默认2秒
                    log(f"[重试] 未知错误，{wait}秒后重试", "WARN")
                time.sleep(wait)
                # P0修复：重试时强制重新select_engine，不硬连已熔断的B
                new_key, new_model = select_engine(state)
                if new_key:
                    engine_key, model = new_key, new_model
                    label = "A主" if engine_key == "engine_a" else ("C中" if engine_key == "engine_c" else "B轻")
                # 如果select_engine返回None（双引擎都不可用），保持原引擎继续尝试
    with state_lock:
        state["tasks_failed"] += 1
    save_state(state)
    fail_result = {"task_id": task_id, "status": "failed", "duration": time.time() - start_time, "task_type": task_type}
    # 预判层：失败后也验证
    try:
        verify_prediction(prediction, fail_result)
    except Exception as pe:
        log(f"[预判-验证异常] {pe}", "WARN")
    return fail_result

# ============ 第6维·通神：认知注入 ============
_cached_cognitions = []  # 缓存的Top核心认知

def load_top_cognitions(n=5):
    """启动时加载Top n条核心认知，用于注入新任务prompt"""
    global _cached_cognitions
    try:
        files = sorted(COGNITION_POOL.glob("cog_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]
        cogs = []
        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            for c in data.get("cognitions", []):
                text = c["text"].strip()
                if len(text) > 15 and text not in cogs:
                    cogs.append(text)
                    if len(cogs) >= n:
                        break
            if len(cogs) >= n:
                break
        _cached_cognitions = cogs
        log(f"[通神] 加载{len(cogs)}条核心认知用于任务注入")
        return cogs
    except Exception as e:
        log(f"[通神] 认知加载失败: {e}", "WARN")
        _cached_cognitions = []
        return []

def inject_cognition_prefix(prompt, task_type):
    """给任务prompt注入认知前缀，deep/eng注入5条，cog/exp注入2条"""
    if not _cached_cognitions:
        return prompt
    n = 5 if task_type in ("deep", "eng") else 2
    top = _cached_cognitions[:n]
    if not top:
        return prompt
    prefix = "【已有认知锚定】以下是已验证的核心结论，请在此基础上推演，避免重复论证：\n"
    for i, c in enumerate(top, 1):
        prefix += f"{i}. {c[:100]}\n"
    prefix += "\n"
    return prefix + prompt

def is_duplicate_cognition(text):
    """检查认知是否与已缓存认知重复（简单字符串匹配）"""
    if not _cached_cognitions:
        return False
    for c in _cached_cognitions:
        # 简单相似度：前30字符重合度>70%视为重复
        common = len(set(text[:30]) & set(c[:30]))
        if common / 30 > 0.7:
            return True
    return False

def build_task_prompt(task):
    task_type = detect_task_type(task)
    prompt = f"任务目标：{task.get('core_target', '')}\n\n"
    if task.get("accept_criteria"):
        prompt += "验收标准：\n"
        for i, c in enumerate(task["accept_criteria"], 1):
            prompt += f"{i}. {c}\n"
    prompt += "\n请直接输出结果。"
    return inject_cognition_prefix(prompt, task_type)

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
        c = state.get("engine_c", {"tokens_used": 0, "requests": 0, "failures": 0, "fuse_until": 0})
        total = a["tokens_used"] + b["tokens_used"] + c["tokens_used"]
        pa = min(a["tokens_used"] / SWITCH_THRESHOLD_A * 100, 100)
        pb = min(b["tokens_used"] / DAILY_BUDGET_B * 100, 100)
        pc = min(c["tokens_used"] / DAILY_BUDGET_B * 100, 100)
        dp = state.get("nine_dim_progress", {})
    log("=" * 60)
    realm = state.get("realm", "九转·第一转·筑基")
    zhuan = state.get("zhuan_count", 0)
    cur_tasks = state.get("current_zhuan_tasks", 0)
    log(f"  {realm} | 已完成{zhuan}转 | 本转{cur_tasks}/{ZHUAN_TASK_THRESHOLD}任务")
    log(f"  [A GLM5.2]  {'█'*int(pa/5)}{'░'*(20-int(pa/5))} {pa:5.1f}% {a['tokens_used']:>10,}/{SWITCH_THRESHOLD_A:,} | 请求{a['requests']}次")
    log(f"  [C DS-V4F] {'█'*int(pc/5)}{'░'*(20-int(pc/5))} {pc:5.1f}% {c['tokens_used']:>10,}/{DAILY_BUDGET_B:,} | 请求{c.get('requests',0)}次")
    log(f"  [B SeedT]  {'█'*int(pb/5)}{'░'*(20-int(pb/5))} {pb:5.1f}% {b['tokens_used']:>10,}/{DAILY_BUDGET_B:,} | 请求{b['requests']}次")
    fs = state.get("finished_stats", {})
    finished_total = sum(fs.values())
    log(f"  完成:{state['tasks_completed']} 失败:{state['tasks_failed']} 废稿:{state.get('waste_count',0)} 认知:{state.get('cognition_count',0)}条 成品:{finished_total}(S{fs.get('S',0)}A{fs.get('A',0)}B{fs.get('B',0)}C{fs.get('C',0)})")
    dims_str = " ".join(f"{d}{dp.get(d,{}).get('count',0)}" for d in NINE_DIMS[:5])
    log(f"  九维: {dims_str}")
    log("=" * 60)

# ============ 主循环 ============
def main():
    global executor  # P1-1修复：并发热加载需要全局引用
    pid_file = STATE_FILE.parent / "engine.pid"
    # P1-6：启动前检查是否已有实例运行
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            if psutil.pid_exists(old_pid):
                # 检查是否真的是引擎进程
                try:
                    old_proc = psutil.Process(old_pid)
                    if "engine_zhuan1" in " ".join(old_proc.cmdline()):
                        log(f"[START] 检测到已有引擎实例运行(PID:{old_pid})，退出避免多实例", "WARN")
                        return
                except:
                    pass
        except:
            pass
    # 写入PID文件（供看门狗检测）
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    state = load_state()
    # P0-2修复：启动时强制同步version与realm
    if state.get("realm") and state.get("version") != state["realm"]:
        state["version"] = state["realm"]
        save_state(state)
    # 启动时读取state里的并发数（模型自进化可能已调整），没有则用默认值
    startup_concurrency = state.get("concurrency_override", CONCURRENCY)
    log(f"[START] {ENGINE_VERSION} 启动 | 并发:{startup_concurrency} (state={state.get('concurrency_override','默认')})")
    log(f"  A主阈值:{SWITCH_THRESHOLD_A:,} | C中预算:{DAILY_BUDGET_B:,} | B轻预算:{DAILY_BUDGET_B:,}")
    log(f"  模型路由: 三级分流 A(deep/l4)→C(eng/cog/exp)→B(archive/asset)，不可用逐级降级")
    print_dashboard(state)
    # P0-1：启动内存监控线程
    start_memory_monitor(state)
    # 第6维·通神：启动时加载核心认知
    load_top_cognitions(5)
    task_counter = 0
    total_task_counter = 0  # P1-4修复：无论任务来源都计数
    executor = ThreadPoolExecutor(max_workers=startup_concurrency, thread_name_prefix="Worker")
    try:
        while True:
            try:
                check_daily_reset(state)
                # 预判层自循环：攒够100条自动批量校验+规则迭代
                pending_verify = get_pending_verify_count()
                if pending_verify >= 100:
                    log(f"[预判校验] 攒够{pending_verify}条，触发批量校验+规则迭代")
                    try:
                        vr = run_batch_verify(auto_iterate=True, dry_run=False)
                        if "error" not in vr:
                            log(f"[预判校验] 完成: 批次{vr['batch_size']}条 | "
                                f"失败准确率{vr['dimension_accuracy']['failure']['accuracy']:.1%} | "
                                f"超时准确率{vr['dimension_accuracy']['timeout']['accuracy']:.1%} | "
                                f"自动迭代{len(vr.get('auto_changes',[]))}项")
                        else:
                            log(f"[预判校验] 跳过: {vr['error']}")
                    except Exception as ve:
                        log(f"[预判校验-异常] {ve}", "WARN")
                # 反向资产预判：每日扫描存量资产+分级+校验
                last_asset_scan = state.get("last_asset_scan", "")
                need_asset_scan = False
                if not last_asset_scan:
                    need_asset_scan = True
                else:
                    try:
                        from datetime import datetime as _dt
                        last_time = _dt.fromisoformat(last_asset_scan)
                        if (_dt.now() - last_time).total_seconds() > 86400:  # 24小时
                            need_asset_scan = True
                    except Exception:
                        need_asset_scan = True
                if need_asset_scan:
                    log("[资产扫描] 触发每日存量资产扫描+预判分级")
                    try:
                        scan_result = scan_all_assets()
                        pred_result = predict_all_assets()
                        state["last_asset_scan"] = datetime.now().isoformat()
                        state["last_asset_scan_count"] = pred_result.get("total_assets", 0)
                        # 自动触发反向校验
                        av = verify_asset_predictions(auto_iterate=True, dry_run=False)
                        if "error" not in av:
                            log(f"[资产预判] 完成: {av['total_assets']}个资产 | "
                                f"工程类{dict(av['grade_stats'].get('engineering',{}))} | "
                                f"认知类{dict(av['grade_stats'].get('cognition',{}))} | "
                                f"自动迭代{len(av.get('auto_changes',[]))}项")
                        save_state(state)
                    except Exception as ae:
                        log(f"[资产扫描-异常] {ae}", "WARN")
                # 资产完整性校验：每日自动检查文件完整性+索引一致性
                last_integrity_check = state.get("last_integrity_check", "")
                need_integrity = False
                if not last_integrity_check:
                    need_integrity = True
                else:
                    try:
                        from datetime import datetime as _dt2
                        last_time2 = _dt2.fromisoformat(last_integrity_check)
                        if (_dt2.now() - last_time2).total_seconds() > 86400:
                            need_integrity = True
                    except Exception:
                        need_integrity = True
                if need_integrity:
                    log("[资产校验] 触发每日资产完整性校验")
                    try:
                        ir = check_integrity()
                        state["last_integrity_check"] = datetime.now().isoformat()
                        state["last_integrity_status"] = ir.get("overall_status", "unknown")
                        high_issues = ir.get("severity_summary", {}).get("critical", 0) + ir.get("severity_summary", {}).get("high", 0)
                        log(f"[资产校验] 完成: 状态{ir['overall_status']} | "
                            f"文件{ir['stats']['files_exist']}/{ir['stats']['index_total']}存在 | "
                            f"关键资产{ir['stats']['critical_ok']}/{ir['stats']['critical_ok']+ir['stats']['critical_missing']}正常 | "
                            f"严重问题{high_issues}个")
                        save_state(state)
                    except Exception as ie:
                        log(f"[资产校验-异常] {ie}", "WARN")
                # 第8维·还虚：每周检查是否生成自演化报告
                if check_weekly_evolution(state):
                    generate_evolution_report(state)
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
                        try:
                            result = future.result()
                        except Exception as e:
                            log(f"[TASK-ERR] 任务异常: {type(e).__name__}: {e}", "ERROR")
                            state["tasks_failed"] += 1
                            # 阶段一突破：失败认知蒸馏——失败不是垃圾，是避坑经验
                            try:
                                fail_cog = extract_failure_cognition(
                                    task_id=f"fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                                    task_type=task_type,
                                    error_msg=f"{type(e).__name__}: {e}",
                                    task_content=raw_prompt[:300] if 'raw_prompt' in dir() else ""
                                )
                                save_failure_cognition(fail_cog)
                                log(f"[失败蒸馏] {fail_cog['failure_type']} | 避坑价值{fail_cog['value_score']}分 | {fail_cog['phenomenon'][:40]}")
                            except Exception as fe:
                                log(f"[失败蒸馏-异常] {fe}", "WARN")
                            record_task_stat(state, task_type, "failed")
                            save_state(state)
                            continue
                        task, task_type = future_map[future]
                        if result["status"] == "success":
                            cultivation_pipeline(result["task_id"], task_type, result["content"], state)
                            record_task_stat(state, task_type, "success", increment_score=result.get("increment_score", 50), is_duplicate=result.get("is_duplicate", False))
                            state["current_zhuan_tasks"] += 1
                            total_task_counter += 1
                            if state["current_zhuan_tasks"] >= ZHUAN_TASK_THRESHOLD:
                                complete_zhuan(state)
                                load_top_cognitions(5)
                        else:
                            record_task_stat(state, task_type, "failed")
                            log(f"[SKIP] {result.get('task_id','?')} 状态:{result['status']}")
                else:
                    engine_key, _ = select_engine(state, "exp")
                    if not engine_key:
                        log("[IDLE] 额度耗尽，切换空闲模式跑本地零消耗任务")
                        run_idle_task(state)
                        time.sleep(30)
                        continue
                    # P1-7修复：并发数热加载+上下限校验（1-5路）
                    target_conc = max(1, min(5, state.get("concurrency_override", CONCURRENCY)))
                    if target_conc != state.get("concurrency_override"):
                        state["concurrency_override"] = target_conc
                    if target_conc != executor._max_workers:
                        log(f"[EVOLVE] 并发数调整: {executor._max_workers}→{target_conc}")
                        executor.shutdown(wait=False)  # P1-7：不等待，避免长任务阻塞
                        executor = ThreadPoolExecutor(max_workers=target_conc, thread_name_prefix="Worker")
                    future_map = {}
                    for i in range(target_conc):
                        task_counter += 1
                        task_id = f"selfgen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_counter:04d}"
                        # P1-6修复：优先消费goal_tasks，没有才用系统任务
                        goal_tasks = state.get("goal_tasks", [])
                        is_goal_task = False
                        current_gt = None
                        if goal_tasks:
                            with state_lock:
                                if state.get("goal_tasks"):
                                    current_gt = state["goal_tasks"].pop(0)
                            if current_gt:
                                is_goal_task = True
                                task_type = current_gt.get("type", detect_task_type(current_gt))
                                raw_prompt = current_gt.get("prompt", current_gt.get("core_target", ""))
                                log(f"[GOAL] 消费目标任务: {task_type} - {raw_prompt[:40]}")
                        if not is_goal_task:
                            task_type, raw_prompt = pick_system_task(state)
                        # 阶段一：注入失败认知+坑库预警作为避坑提醒
                        relevant_fails = get_relevant_failures(task_type, limit=2)
                        fail_injection = format_failure_injection(relevant_fails)
                        pit_warnings = format_pit_warning(match_pits(task_type, raw_prompt[:200], level="L1"))
                        injection_parts = [p for p in [fail_injection, pit_warnings] if p]
                        injection = "\n\n".join(injection_parts) if injection_parts else ""
                        if injection:
                            prompt = injection + "\n\n" + inject_cognition_prefix(raw_prompt, task_type)
                        else:
                            prompt = inject_cognition_prefix(raw_prompt, task_type)
                        fut = executor.submit(execute_single_api, task_id, prompt, state, task_type)
                        future_map[fut] = {"type": task_type, "is_goal": is_goal_task, "gt": current_gt}
                    for future in as_completed(future_map):
                        try:
                            result = future.result()
                        except Exception as e:
                            task_info = future_map.get(future, {"type": "unknown", "is_goal": False, "gt": None})
                            task_type = task_info["type"]
                            log(f"[TASK-ERR] 任务异常: {type(e).__name__}: {e}", "ERROR")
                            state["tasks_failed"] += 1
                            # P0-3修复：goal_task失败放回队列重试，超过3次移入死信队列
                            if task_info["is_goal"] and task_info["gt"]:
                                gt = task_info["gt"]
                                gt["retry_count"] = gt.get("retry_count", 0) + 1
                                if gt["retry_count"] <= 3:
                                    with state_lock:
                                        state.setdefault("goal_tasks", []).insert(0, gt)
                                    log(f"[GOAL-RETRY] 目标任务失败，第{gt['retry_count']}次重试，放回队列", "WARN")
                                else:
                                    with state_lock:
                                        state.setdefault("failed_goal_tasks", []).append(gt)
                                    log(f"[GOAL-DEAD] 目标任务重试{gt['retry_count']}次失败，移入死信队列", "ERROR")
                            # 阶段一突破：失败认知蒸馏——失败不是垃圾，是避坑经验
                            try:
                                fail_cog = extract_failure_cognition(
                                    task_id=f"fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                                    task_type=task_type,
                                    error_msg=f"{type(e).__name__}: {e}",
                                    task_content=raw_prompt[:300] if 'raw_prompt' in dir() else ""
                                )
                                save_failure_cognition(fail_cog)
                                log(f"[失败蒸馏] {fail_cog['failure_type']} | 避坑价值{fail_cog['value_score']}分 | {fail_cog['phenomenon'][:40]}")
                            except Exception as fe:
                                log(f"[失败蒸馏-异常] {fe}", "WARN")
                            record_task_stat(state, task_type, "failed")
                            save_state(state)
                            continue
                        task_info = future_map[future]
                        task_type = task_info["type"]
                        if result["status"] == "success":
                            cultivation_pipeline(result["task_id"], task_type, result["content"], state)
                            record_task_stat(state, task_type, "success", increment_score=result.get("increment_score", 50), is_duplicate=result.get("is_duplicate", False))
                        else:
                            record_task_stat(state, task_type, "failed")
                            # P0-3：goal_task执行失败（非异常）也放回队列
                            if task_info["is_goal"] and task_info["gt"]:
                                gt = task_info["gt"]
                                gt["retry_count"] = gt.get("retry_count", 0) + 1
                                if gt["retry_count"] <= 3:
                                    with state_lock:
                                        state.setdefault("goal_tasks", []).insert(0, gt)
                                    log(f"[GOAL-RETRY] 目标任务执行失败，第{gt['retry_count']}次重试", "WARN")
                                else:
                                    with state_lock:
                                        state.setdefault("failed_goal_tasks", []).append(gt)
                                    log(f"[GOAL-DEAD] 目标任务重试{gt['retry_count']}次失败，移入死信队列", "ERROR")
                        # P0-4修复：无论任务来源，成功后都计数
                        if result["status"] == "success":
                            state["current_zhuan_tasks"] += 1
                            total_task_counter += 1  # P1-4修复：成功任务计数
                            if state["current_zhuan_tasks"] >= ZHUAN_TASK_THRESHOLD:
                                complete_zhuan(state)
                                load_top_cognitions(5)  # P1-7修复：每转结束刷新认知缓存
                        else:
                            log(f"[SKIP] {result.get('task_id','?')} 状态:{result['status']}")
                # P1-4修复：周期触发基于total_task_counter，收件箱任务也能触发
                if total_task_counter % 10 == 0 and total_task_counter > 0:
                    self_audit(state, total_task_counter)
                    adjust_task_weights(state)
                    load_top_cognitions(5)  # P1-7修复：每10任务刷新认知缓存
                    # 阶段一核心：自动执行反哺调参
                    adj_results = execute_feedback(state)
                    if adj_results:
                        log(f"[EVOLVE] 自动调参执行{len(adj_results)}项: " + ", ".join(f"{r['target']}:{r['before']}→{r['after']}" for r in adj_results[:3]))
                if total_task_counter % 15 == 0 and total_task_counter > 0:
                    print_dashboard(state)
            except Exception as e:
                log(f"[LOOP-ERR] {type(e).__name__}: {e}", "ERROR")
                time.sleep(5)
    except KeyboardInterrupt:
        log("[STOP] 收到中断信号")
    finally:
        try:
            executor.shutdown(wait=True)
        except:
            pass
        save_state(state)
        # P1-6：清理PID文件
        try:
            if pid_file.exists():
                pid_file.unlink()
        except:
            pass
        log("[END] 引擎已停止")

if __name__ == "__main__":
    main()
