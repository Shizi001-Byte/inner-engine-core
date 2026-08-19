"""
认知密度量化模块
对标星卷视觉名词密度规律，建立认知质量的可计算指标
"""
import re
from datetime import datetime

# 核心概念词库（用于计算信息密度）
CORE_CONCEPTS = {
    "engine": ["引擎", "调度", "并发", "路由", "熔断", "调参", "权重", "热加载", "闭环", "反哺", "线程", "队列", "锁", "竞态", "守护进程"],
    "cognition": ["认知", "蒸馏", "沉淀", "记忆", "链路", "整合", "注入", "锚点", "密度", "分层", "归档", "索引", "检索", "溯源"],
    "philosophy": ["反者道之动", "弱者道之用", "有生于无", "九转", "阴阳", "虚实", "鼎器", "丹核", "护法", "筑基", "炼精", "结丹", "育神"],
    "engineering": ["架构", "模块", "接口", "配置", "状态", "持久化", "原子", "幂等", "降级", "兜底", "SQL", "schema", "字段", "列名", "索引", "事务", "迁移", "备份", "灾备"],
    "evolution": ["进化", "迭代", "自优化", "自检测", "目标导向", "增量", "校准", "淬炼", "圆满", "突破", "跃迁", "重构"],
    "tech_general": ["脚本", "代码", "函数", "API", "密钥", "超时", "重试", "缓存", "同步", "异步", "序列化", "编码", "格式", "校验", "检查清单", "SOP", "补丁", "回滚"],
}

# 可执行动作词（用于计算可执行密度）
ACTION_WORDS = ["修改", "创建", "删除", "调整", "设置", "接入", "修复", "优化", "扩展", "替换", "重构", "封装", "调用", "触发", "编写", "部署", "测试", "验证", "排查", "归档", "同步", "备份", "恢复", "升级", "降级", "监控", "告警", "限流", "熔断"]

# 空转套话词（命中则扣分）
EMPTY_WORDS = ["赋能", "抓手", "闭环思维", "底层逻辑", "顶层设计", "组合拳", "打法", "矩阵", "生态", "范式"]


def count_core_concepts(text):
    """统计文本中的核心概念数"""
    count = 0
    found = []
    for category, words in CORE_CONCEPTS.items():
        for w in words:
            if w in text:
                count += 1
                found.append(w)
    return count, found


def count_action_points(text):
    """统计可执行动作点数"""
    count = 0
    for w in ACTION_WORDS:
        count += len(re.findall(w, text))
    return count


def count_empty_words(text):
    """统计空转套话词数"""
    count = 0
    for w in EMPTY_WORDS:
        count += text.count(w)
    return count


def calc_density(text, related_cognitions=0):
    """
    计算认知综合密度
    返回：(综合密度, 各维度分, 等级)
    """
    if not text or len(text.strip()) < 10:
        return 0.0, {"info": 0, "action": 0, "relation": 0, "empty_penalty": 0}, "C"

    text_len = len(text)
    core_count, _ = count_core_concepts(text)
    action_count = count_action_points(text)
    empty_count = count_empty_words(text)

    # 信息密度：核心概念数 / 百字
    info_density = min(1.0, core_count / max(1, text_len / 100))
    # 可执行密度：动作点数 / 总观点数（估算为句子数）
    sentences = [s for s in re.split(r'[。！？\n]', text) if len(s.strip()) > 5]
    action_density = min(1.0, action_count / max(1, len(sentences)))
    # 关联密度：与已有认知的关联数（外部传入）
    relation_density = min(1.0, related_cognitions / 5.0)
    # 套话惩罚：每命中一个扣0.1
    empty_penalty = min(0.5, empty_count * 0.1)

    # 综合密度：信息40% + 可执行35% + 关联25% - 套话惩罚
    composite = info_density * 0.4 + action_density * 0.35 + relation_density * 0.25 - empty_penalty
    composite = max(0.0, min(1.0, composite))

    # 分级
    if composite >= 0.7:
        grade = "S"
    elif composite >= 0.5:
        grade = "A"
    elif composite >= 0.3:
        grade = "B"
    else:
        grade = "C"

    details = {
        "info": round(info_density, 3),
        "action": round(action_density, 3),
        "relation": round(relation_density, 3),
        "empty_penalty": round(empty_penalty, 3),
        "core_concepts": core_count,
        "action_points": action_count,
        "empty_words": empty_count,
    }
    return round(composite, 3), details, grade


def format_density_report(text, related_cognitions=0):
    """生成密度报告字符串"""
    composite, details, grade = calc_density(text, related_cognitions)
    return f"""认知密度分析:
  综合密度: {composite} ({grade}级)
  信息密度: {details['info']} (核心概念{details['core_concepts']}个)
  可执行密度: {details['action']} (动作点{details['action_points']}个)
  关联密度: {details['relation']} (关联认知{related_cognitions}条)
  套话惩罚: -{details['empty_penalty']} (命中{details['empty_words']}个套话词)
"""
