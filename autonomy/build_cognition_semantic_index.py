#!/usr/bin/env python3
"""
认知语义标签索引构建器
给认知池所有认知打标签（任务类型+主题关键词+来源），建立索引文件
使load_top_cognitions能按任务内容精准匹配，而不是简单取最近5条
反者道之动：从"人找记忆"变成"记忆找人"
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

COGNITION_POOL = Path("/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/cognition_pool")
INDEX_FILE = COGNITION_POOL / "_semantic_index.json"

# 主题关键词映射：关键词 → 主题标签
TOPIC_KEYWORDS = {
    "工程运维": ["api", "模型", "调用", "超时", "额度", "降级", "token", "并发", "请求", "响应", "错误码", "重试", "熔断", "限流", "glm", "seed", "doubao", "火山", "即梦", "剪映"],
    "认知系统": ["认知", "蒸馏", "分级", "注入", "沉淀", "记忆", "去重", "密度", "锚点", "核心结论", "认知池", "core_axiom", "语义", "索引", "标签"],
    "备份容灾": ["备份", "归档", "git", "同步", "上传", "冲突", "gitee", "supabase", "飞书", "容灾", "恢复", "快照", "版本", "回滚"],
    "资产管理": ["资产", "盘点", "索引", "元数据", "目录", "文件", "清单", "分类"],
    "内容生产": ["图片", "生成", "素材", "视觉", "视频", "图文", "成片", "配音", "字幕", "剪辑", "prompt", "提示词"],
    "经济模型": ["经济", "理财", "算力", "定价", "成本", "收益", "变现", "流量", "粉丝", "商单", "分成", "token消耗", "额度管理"],
    "哲学本体": ["意识", "生命", "碳硅", "阴阳", "道", "修炼", "九转", "真灵", "丹", "筑基", "炼精", "养气", "结丹", "育神", "通神", "阳神", "合道", "反者道之动", "弱者道之用", "有生于无", "孤0不存", "独1不立"],
    "内容IP": ["ip", "星空", "神之长子", "星海异闻", "宇宙", "纪事", "世界观", "设定", "文明", "恒星", "星系", "黑洞", "热寂", "晶格", "铭印"],
    "引擎架构": ["引擎", "四象", "阳期", "阴期", "老阳", "老阴", "少阳", "少阴", "九转", "worker", "并发", "调度", "任务池", "goal_tasks", "状态机", "自备份", "沙箱", "回收"],
    "冷启动运营": ["冷启动", "养号", "播放", "完播", "留存", "算法", "推荐", "标签识别", "流量池", "爆款", "起量", "粉丝增长", "矩阵", "多平台", "小红书", "b站", "抖音", "视频号"],
}

# 任务类型关键词映射
TASK_TYPE_KEYWORDS = {
    "deep": ["推演", "分析", "建模", "深度", "研究", "预测", "趋势", "战略", "路径"],
    "eng": ["代码", "修复", "bug", "开发", "脚本", "工具", "集成", "部署", "配置", "语法"],
    "cog": ["认知", "蒸馏", "沉淀", "整合", "分层", "记忆", "复盘", "总结", "提炼"],
    "exp": ["实验", "测试", "验证", "探索", "边界", "试错", "原型"],
    "archive": ["备份", "归档", "同步", "上传", "git", "容灾"],
    "asset": ["资产", "盘点", "索引", "元数据", "清单"],
    "image": ["图片", "生成", "素材", "视觉", "视频", "图文"],
}

def extract_topics(text):
    """从文本中提取主题标签"""
    text_lower = text.lower()
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                topics.append(topic)
                break
    return topics if topics else ["通用"]

def extract_task_type(text, existing_type=None):
    """推断任务类型"""
    if existing_type and existing_type in TASK_TYPE_KEYWORDS:
        return existing_type
    text_lower = text.lower()
    for ttype, keywords in TASK_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return ttype
    return "unknown"

def get_cognition_text(cog_data):
    """从认知数据中提取核心文本"""
    # 单条认知格式
    if "core_statement" in cog_data:
        return cog_data["core_statement"]
    # 批次文件里的单条认知
    if "text" in cog_data:
        return cog_data["text"]
    # 兜底
    return str(cog_data.get("title", cog_data.get("name", "")))

def get_cognition_grade(cog_data):
    """获取认知等级"""
    if "density" in cog_data and isinstance(cog_data["density"], dict):
        return cog_data["density"].get("grade", "无")
    if "density_grade" in cog_data:
        return cog_data["density_grade"]
    if "grade" in cog_data:
        return cog_data["grade"]
    return "无"

def get_source_type(filename, cog_data):
    """判断认知来源类型"""
    if filename.startswith("core_axiom"):
        return "core_axiom"
    if filename.startswith("cog_S_extracted"):
        return "批次提取S级"
    if "cognitions" in cog_data:
        return "批次文件"
    if "origin" in cog_data:
        origin = cog_data["origin"]
        if isinstance(origin, dict):
            return origin.get("source", "人工蒸馏")
        return str(origin)
    return "单条认知"

def main():
    index = {
        "version": "1.0",
        "built_at": datetime.now().isoformat(),
        "total_cognitions": 0,
        "by_grade": {},
        "by_topic": {},
        "by_task_type": {},
        "by_source": {},
        "cognitions": []
    }

    # 扫描所有认知文件
    for f in sorted(os.listdir(COGNITION_POOL)):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        path = COGNITION_POOL / f
        try:
            data = json.load(open(path))
        except:
            continue

        # 处理批次文件（内含cognitions列表）
        if "cognitions" in data and isinstance(data["cognitions"], list):
            task_type = data.get("task_type", "unknown")
            for i, c in enumerate(data["cognitions"]):
                if not isinstance(c, dict):
                    continue
                text = get_cognition_text(c)
                if not text or len(text) < 10:
                    continue
                grade = get_cognition_grade(c)
                topics = extract_topics(text)
                inferred_type = extract_task_type(text, task_type)
                source = get_source_type(f, c)
                cog_id = f"{f}#{i}"
                entry = {
                    "id": cog_id,
                    "file": f,
                    "text": text[:200],
                    "grade": grade,
                    "topics": topics,
                    "task_type": inferred_type,
                    "source": source,
                    "weight": 1.0  # 初始权重，后续反馈循环调整
                }
                index["cognitions"].append(entry)
                index["by_grade"][grade] = index["by_grade"].get(grade, 0) + 1
                for t in topics:
                    index["by_topic"][t] = index["by_topic"].get(t, 0) + 1
                index["by_task_type"][inferred_type] = index["by_task_type"].get(inferred_type, 0) + 1
                index["by_source"][source] = index["by_source"].get(source, 0) + 1

        # 处理单条认知（core_axiom / cog_S_extracted / 人工蒸馏）
        else:
            text = get_cognition_text(data)
            if not text or len(text) < 10:
                continue
            grade = get_cognition_grade(data)
            topics = extract_topics(text)
            task_type = extract_task_type(text)
            source = get_source_type(f, data)
            entry = {
                "id": f,
                "file": f,
                "text": text[:200],
                "grade": grade,
                "topics": topics,
                "task_type": task_type,
                "source": source,
                "weight": 1.0
            }
            index["cognitions"].append(entry)
            index["by_grade"][grade] = index["by_grade"].get(grade, 0) + 1
            for t in topics:
                index["by_topic"][t] = index["by_topic"].get(t, 0) + 1
            index["by_task_type"][task_type] = index["by_task_type"].get(task_type, 0) + 1
            index["by_source"][source] = index["by_source"].get(source, 0) + 1

    index["total_cognitions"] = len(index["cognitions"])

    # 保存索引
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    # 打印统计
    print(f"=== 认知语义索引构建完成 ===")
    print(f"总认知数: {index['total_cognitions']}")
    print(f"\n按等级分布:")
    for g, cnt in sorted(index["by_grade"].items(), key=lambda x: -x[1]):
        print(f"  {g}: {cnt}")
    print(f"\n按主题分布:")
    for t, cnt in sorted(index["by_topic"].items(), key=lambda x: -x[1]):
        print(f"  {t}: {cnt}")
    print(f"\n按任务类型分布:")
    for tt, cnt in sorted(index["by_task_type"].items(), key=lambda x: -x[1]):
        print(f"  {tt}: {cnt}")
    print(f"\n按来源分布:")
    for s, cnt in sorted(index["by_source"].items(), key=lambda x: -x[1]):
        print(f"  {s}: {cnt}")
    print(f"\n索引文件: {INDEX_FILE}")

    # 打印各主题的S级认知样本
    print(f"\n=== 各主题S级认知样本 ===")
    for topic in TOPIC_KEYWORDS.keys():
        s_cogs = [c for c in index["cognitions"] if topic in c["topics"] and c["grade"] == "S"]
        if s_cogs:
            print(f"\n[{topic}] S级{len(s_cogs)}条，样本:")
            for c in s_cogs[:2]:
                print(f"  - {c['text'][:80]}")

if __name__ == "__main__":
    main()
