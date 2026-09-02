#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent输出统一包装器 V1.0
功能：为阴期任务产出提供标准化元数据包装，确保格式统一、可追溯、可过滤
原则：零API调用，纯本地处理，不改变原始数据内容，仅添加元数据层
"""
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Agent角色定义表
AGENT_ROLES = {
    "yin_tag_normalize": {"role": "分类学家", "fact_level_default": "事实"},
    "yin_pit_review": {"role": "产品经理", "fact_level_default": "事实"},
    "yin_asset_dedup": {"role": "质检员", "fact_level_default": "事实"},
    "yin_log_cluster": {"role": "系统集成师", "fact_level_default": "事实"},
    "yin_cognition_graph": {"role": "系统集成师", "fact_level_default": "推断"},
    "yin_pit_rootcause": {"role": "产品经理", "fact_level_default": "推断"},
    "yin_code_audit": {"role": "质检员", "fact_level_default": "事实"},
    "yin_task_preassemble": {"role": "系统集成师", "fact_level_default": "推断"},
    "yin_conflict_check": {"role": "质检员", "fact_level_default": "事实"},
    "yin_rule_gen": {"role": "分类学家", "fact_level_default": "推断"},
    "yin_evolution_path": {"role": "产品经理", "fact_level_default": "假设"},
    "yin_asset_health": {"role": "质检员", "fact_level_default": "事实"},
    "yin_local_semantic_pilot": {"role": "文案编辑", "fact_level_default": "推断"},
    "yin_verifier_audit": {"role": "质检员", "fact_level_default": "事实"},
    "yin_metrics_analyzer": {"role": "系统集成师", "fact_level_default": "事实"},
    "yin_cognition_polish": {"role": "文案编辑", "fact_level_default": "推断"},
    "yin_cognitive_sediment": {"role": "文案编辑", "fact_level_default": "推断"},
    "yin_archive_manager": {"role": "档案管理员", "fact_level_default": "事实"},
    "yin_memory_sync": {"role": "档案管理员", "fact_level_default": "事实"},
    "yin_memory_integration": {"role": "系统集成师", "fact_level_default": "推断"},
    "yin_content_audit": {"role": "质检员", "fact_level_default": "事实"},
    "yin_core_memory_build": {"role": "系统集成师", "fact_level_default": "事实"},
    "yin_memory_fusion": {"role": "系统集成师", "fact_level_default": "推断"},
    # 考据归档类（未来扩展）
    "yin_research_archive": {"role": "档案管理员", "fact_level_default": "事实"},
    # 金句提取类（未来扩展）
    "yin_quote_extract": {"role": "文案编辑", "fact_level_default": "事实"},
}

VERSION = "1.0.0"


def _generate_task_id(task_name: str) -> str:
    """生成唯一任务ID"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{task_name}_{ts}"


def _assess_confidence(
    task_name: str,
    data: Any,
    error_count: int = 0,
    total_count: int = 0,
    manual_override: Optional[str] = None,
) -> str:
    """
    置信度评估
    规则：
    - 手动覆盖优先
    - 错误率>30% → 低
    - 错误率10-30% → 中
    - 错误率<10% 且 有数据 → 高
    - 无数据 → 低
    """
    if manual_override in ("高", "中", "低"):
        return manual_override

    if total_count == 0 or data is None or (isinstance(data, (list, dict)) and len(data) == 0):
        return "低"

    error_rate = error_count / total_count if total_count > 0 else 1.0
    if error_rate > 0.3:
        return "低"
    elif error_rate > 0.1:
        return "中"
    else:
        return "高"


def wrap_agent_output(
    task_name: str,
    data: Any,
    source_trace: str = "",
    fact_level: Optional[str] = None,
    confidence: Optional[str] = None,
    error_count: int = 0,
    total_count: int = 0,
) -> Dict[str, Any]:
    """
    统一包装Agent产出

    参数：
        task_name: 任务名称（用于匹配Agent角色）
        data: 实际产出数据
        source_trace: 来源追溯（文件路径/目录等）
        fact_level: 事实层级覆盖（事实/推断/假设）
        confidence: 置信度覆盖（高/中/低）
        error_count: 处理中的错误数（用于置信度评估）
        total_count: 处理总数（用于置信度评估）

    返回：
        带_agent_meta元数据层的标准输出字典
    """
    role_info = AGENT_ROLES.get(task_name, {"role": "未定义Agent", "fact_level_default": "推断"})

    final_fact_level = fact_level or role_info["fact_level_default"]
    final_confidence = _assess_confidence(
        task_name, data, error_count, total_count, confidence
    )

    task_id = _generate_task_id(task_name)
    generated_at = datetime.now().isoformat(timespec="seconds")

    # 计算数据指纹（用于去重和版本对比）
    try:
        data_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
        data_fingerprint = hashlib.md5(data_str.encode("utf-8")).hexdigest()[:12]
    except Exception:
        data_fingerprint = "unknown"

    return {
        "_agent_meta": {
            "agent_role": role_info["role"],
            "task_name": task_name,
            "task_id": task_id,
            "fact_level": final_fact_level,
            "confidence": final_confidence,
            "source_trace": source_trace,
            "version": VERSION,
            "generated_at": generated_at,
            "data_fingerprint": data_fingerprint,
            "stats": {
                "total_count": total_count,
                "error_count": error_count,
                "error_rate": round(error_count / total_count, 4) if total_count > 0 else 0,
            },
        },
        "data": data,
    }


def is_low_confidence(wrapped_output: Dict[str, Any]) -> bool:
    """判断产出是否为低置信度（需人工复核）"""
    meta = wrapped_output.get("_agent_meta", {})
    return meta.get("confidence") == "低"


def extract_data(wrapped_output: Dict[str, Any]) -> Any:
    """从包装输出中提取原始数据"""
    return wrapped_output.get("data")


def get_meta(wrapped_output: Dict[str, Any]) -> Dict[str, Any]:
    """提取元数据"""
    return wrapped_output.get("_agent_meta", {})


def format_summary(wrapped_output: Dict[str, Any]) -> str:
    """生成人类可读的摘要字符串（用于引擎日志）"""
    meta = wrapped_output.get("_agent_meta", {})
    data = wrapped_output.get("data")

    role = meta.get("agent_role", "?")
    task = meta.get("task_name", "?")
    conf = meta.get("confidence", "?")
    fact = meta.get("fact_level", "?")
    stats = meta.get("stats", {})
    total = stats.get("total_count", 0)
    errors = stats.get("error_count", 0)

    # 估算数据量
    if isinstance(data, dict):
        data_size = f"{len(data)}项"
    elif isinstance(data, list):
        data_size = f"{len(data)}条"
    else:
        data_size = "已生成"

    conf_mark = "🟢" if conf == "高" else ("🟡" if conf == "中" else "🔴")

    return f"[{role}] {task}: {data_size}, 置信度{conf_mark}{conf}, {fact}, 处理{total}项(错误{errors})"


# 自检
if __name__ == "__main__":
    # 测试包装
    test_data = {"标签A": ["同义1", "同义2"], "标签B": ["同义3"]}
    wrapped = wrap_agent_output(
        "yin_tag_normalize",
        test_data,
        source_trace="cognition_pool/*.json",
        total_count=100,
        error_count=2,
    )
    print(json.dumps(wrapped, ensure_ascii=False, indent=2))
    print("\n--- 摘要 ---")
    print(format_summary(wrapped))
    print(f"\n低置信度? {is_low_confidence(wrapped)}")
