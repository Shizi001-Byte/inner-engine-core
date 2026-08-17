"""
失败认知蒸馏模块
核心突破：失败任务不是垃圾，是最有价值的避坑经验
弱者道之用：失败是弱端，但弱端有大用——避坑价值高于成功经验
"""
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path

FAILURE_POOL = Path(__file__).parent.parent / "data" / "failure_cognitions"
FAILURE_POOL.mkdir(parents=True, exist_ok=True)

# 失败模式分类
FAILURE_PATTERNS = {
    "timeout": ["超时", "timeout", "卡住", "无响应", "超过", "timed out"],
    "format_error": ["格式错误", "format", "解析失败", "json", "decode", "编码"],
    "api_error": ["api", "400", "401", "403", "429", "500", "502", "503", "请求失败"],
    "duplicate": ["重复", "duplicate", "同质化", "套话", "空转"],
    "logic_error": ["逻辑", "bug", "异常", "exception", "error", "报错"],
    "config_error": ["配置", "config", "参数", "参数错误", "不生效"],
}

# 失败认知的核心提取维度
FAILURE_DIMENSIONS = [
    "失败现象",      # 发生了什么
    "根因分析",      # 为什么会失败
    "边界条件",      # 在什么情况下会触发
    "修复方法",      # 怎么解决
    "预防措施",      # 以后怎么避免
]


def classify_failure(error_msg, task_content=""):
    """分类失败类型"""
    text = (error_msg + task_content).lower()
    for ftype, keywords in FAILURE_PATTERNS.items():
        for kw in keywords:
            if kw.lower() in text:
                return ftype
    return "unknown"


def extract_failure_cognition(task_id, task_type, error_msg, task_content="", context=""):
    """
    从失败任务中蒸馏认知
    返回：失败认知字典
    """
    ftype = classify_failure(error_msg, task_content)

    # 构建失败认知
    cognition = {
        "task_id": task_id,
        "task_type": task_type,
        "failure_type": ftype,
        "error_msg": error_msg[:500],
        "extracted_at": datetime.now().isoformat(),
        "phenomenon": "",
        "root_cause": "",
        "boundary": "",
        "fix_method": "",
        "prevention": "",
        "value_score": 0,  # 避坑价值分
    }

    # 简单规则提取（后续可升级为API蒸馏）
    text = error_msg + " " + task_content

    # 现象提取
    if "超时" in text or "timeout" in text.lower():
        cognition["phenomenon"] = "API调用超时，任务未在规定时间内返回"
        cognition["root_cause"] = "模型推理时间过长或网络延迟，timeout配置不足"
        cognition["boundary"] = "max_tokens较大或模型推理慢时触发"
        cognition["fix_method"] = "增大timeout或降低max_tokens，切换到更快的模型"
        cognition["prevention"] = "根据任务类型预设合理timeout，B模型turbo用300秒，A模型用600秒"
        cognition["value_score"] = 8
    elif "格式" in text or "json" in text.lower() or "解析" in text:
        cognition["phenomenon"] = "返回内容格式不符合预期，解析失败"
        cognition["root_cause"] = "模型输出格式不稳定，或prompt未明确要求格式"
        cognition["boundary"] = "要求结构化输出但模型自由发挥时触发"
        cognition["fix_method"] = "prompt中加格式示例，或增加容错解析逻辑"
        cognition["prevention"] = "结构化任务必须给格式示例，解析层加try-except兜底"
        cognition["value_score"] = 7
    elif "重复" in text or "套话" in text or "同质化" in text:
        cognition["phenomenon"] = "产出内容与已有内容高度重复，无增量"
        cognition["root_cause"] = "任务池过小或权重倾斜，模型反复生成同类内容"
        cognition["boundary"] = "某类任务权重过高或任务池<30个时触发"
        cognition["fix_method"] = "扩充任务池，降低高权重类型，增加随机任务槽位"
        cognition["prevention"] = "每5转检查任务多样性，重复率>30%自动降权"
        cognition["value_score"] = 9
    elif "配置" in text or "不生效" in text or "参数" in text:
        cognition["phenomenon"] = "配置修改后未生效，行为无变化"
        cognition["root_cause"] = "执行逻辑读取全局常量而非状态配置，或热加载断点"
        cognition["boundary"] = "新增可配置参数但未接入执行逻辑时触发"
        cognition["fix_method"] = "检查执行逻辑是否读取state，全局常量是否覆盖了配置"
        cognition["prevention"] = "新增配置必须同步修改读取点，修改后立即验证生效"
        cognition["value_score"] = 10
    else:
        cognition["phenomenon"] = error_msg[:200]
        cognition["root_cause"] = "待分析"
        cognition["boundary"] = "待确认"
        cognition["fix_method"] = "待排查"
        cognition["prevention"] = "待总结"
        cognition["value_score"] = 5

    return cognition


def save_failure_cognition(cognition):
    """保存失败认知到文件"""
    h = hashlib.md5((cognition["task_id"] + cognition["error_msg"][:100]).encode()).hexdigest()[:12]
    fname = f"fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{h}.json"
    fpath = FAILURE_POOL / fname
    with open(fpath, "w") as f:
        json.dump(cognition, f, indent=2, ensure_ascii=False)
    return fpath


def get_relevant_failures(task_type, limit=3):
    """获取与当前任务相关的失败认知，用于注入避坑提示"""
    failures = []
    try:
        files = sorted(FAILURE_POOL.glob("fail_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in files[:20]:
            with open(f) as fh:
                cog = json.load(fh)
            if cog.get("task_type") == task_type or cog.get("failure_type") in ["timeout", "format_error"]:
                failures.append(cog)
                if len(failures) >= limit:
                    break
    except:
        pass
    return failures


def format_failure_injection(failures):
    """格式化失败认知为任务注入文本"""
    if not failures:
        return ""
    lines = ["【避坑提醒】以下是同类任务的历史失败经验："]
    for i, f in enumerate(failures, 1):
        lines.append(f"{i}. 现象：{f.get('phenomenon','')}")
        lines.append(f"   预防：{f.get('prevention','')}")
    return "\n".join(lines)


def get_failure_stats():
    """获取失败认知统计"""
    try:
        files = list(FAILURE_POOL.glob("fail_*.json"))
        types = {}
        total_value = 0
        for f in files:
            with open(f) as fh:
                cog = json.load(fh)
            ft = cog.get("failure_type", "unknown")
            types[ft] = types.get(ft, 0) + 1
            total_value += cog.get("value_score", 0)
        return {
            "total": len(files),
            "by_type": types,
            "total_value_score": total_value,
            "avg_value": round(total_value / len(files), 1) if files else 0,
        }
    except:
        return {"total": 0, "by_type": {}, "total_value_score": 0, "avg_value": 0}
