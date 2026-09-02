#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能旁路调度器（Skill Bypass Dispatcher）
=========================================
位置：最外层独立脚本，与超级守护进程同级
原则：自循环绝对不动，只做外层连通，0.5B本地干，零API消耗

功能：
1. 意图识别（0.5B或规则匹配）→ 匹配预设流水线
2. 按固定顺序调用 skill_porting 模块
3. 汇总结果，输出报告

三条预设线：
- 认知沉淀线：输入文本 → 蒸馏 → 提纯 → 归档 → 记忆融合
- 资产盘点线：自动扫描 → 指标分析 → 完整性校验 → 内容审核 → 产出校验
- 内容生产线：输入主题 → 深度阅读 → 参考审核 → 可视化结构 → 框架输出

安全：
- 不碰四象主循环、不碰核心配置、不写engine_state核心字段
- 所有调用包try-except，失败不影响其他
- 文件锁防与引擎冲突
"""

import os
import sys
import json
import time
import fcntl
import traceback
from datetime import datetime
from pathlib import Path

# 路径配置
BASE_DIR = Path(__file__).parent.parent
SKILL_PORTING_DIR = BASE_DIR / "autonomy" / "skill_porting"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
LOG_DIR = BASE_DIR / "logs"
BYPASS_LOG = LOG_DIR / "skill_bypass.log"
LOCK_FILE = BASE_DIR / "data" / "skill_bypass.lock"

# 确保目录存在
LOG_DIR.mkdir(exist_ok=True)


def log(msg, level="INFO"):
    """写日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(BYPASS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


def acquire_lock():
    """获取文件锁，防止与引擎冲突"""
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd
    except:
        return None


def release_lock(lock_fd):
    """释放文件锁"""
    try:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
    except:
        pass


def load_engine_state():
    """只读引擎状态，不修改"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def get_skill_module(name):
    """动态导入 skill_porting 模块"""
    try:
        sys.path.insert(0, str(SKILL_PORTING_DIR))
        module = __import__(name)
        return module
    except Exception as e:
        log(f"导入模块失败 {name}: {e}", "ERROR")
        return None


def call_skill(name, **kwargs):
    """调用单个 skill_porting 模块，统一异常处理"""
    log(f"调用技能模块: {name}")
    try:
        module = get_skill_module(name)
        if module is None:
            return {"ok": False, "name": name, "error": "模块导入失败"}
        if not hasattr(module, "run"):
            return {"ok": False, "name": name, "error": "无run函数"}
        state = load_engine_state()
        result = module.run(state=state, **kwargs)
        if result:
            log(f"  {name} 完成: ok={result.get('ok', '?')}, {result.get('evidence', '')[:60]}")
        return result
    except Exception as e:
        err = traceback.format_exc()
        log(f"  {name} 异常: {e}", "ERROR")
        return {"ok": False, "name": name, "error": str(e), "traceback": err}


# ============================================================
# 意图识别：0.5B 或 规则匹配
# ============================================================

def intent_recognize(user_input):
    """
    意图识别：判断用户需求匹配哪条预设线
    返回: {"pipeline": "cognition"|"asset"|"content", "params": {...}, "confidence": float}
    策略：规则匹配优先（稳定可靠），0.5B只做辅助验证
    """
    # 先用规则匹配（稳定可靠）
    rule_result = _intent_by_rules(user_input)
    rule_confidence = rule_result.get("confidence", 0)

    # 规则匹配置信度高，直接用
    if rule_confidence >= 0.4 and rule_result.get("pipeline") != "other":
        log(f"规则意图识别(高置信): {rule_result['pipeline']} (置信度={rule_confidence:.2f})")
        return rule_result

    # 规则匹配置信度低，尝试0.5B辅助
    result_05b = _intent_by_05b(user_input)
    if result_05b and result_05b.get("pipeline") and result_05b["pipeline"] != "other":
        log(f"0.5B辅助意图识别: {result_05b['pipeline']} (规则置信度={rule_confidence:.2f})")
        return result_05b

    # 都不行，返回规则结果（可能是other）
    log(f"规则意图识别(低置信): {rule_result['pipeline']} (置信度={rule_confidence:.2f})")
    return rule_result


def _intent_by_05b(user_input):
    """用0.5B做意图识别"""
    try:
        sys.path.insert(0, str(BASE_DIR / "autonomy"))
        from local_model_bridge import get_bridge
        b = get_bridge()
        if not b or not b._check_service():
            return None

        categories = ["认知沉淀", "资产盘点", "内容生产", "其他"]
        category = b.classify(user_input, categories, max_tokens=20)
        if category:
            category = category.strip().replace("\n", "").replace(" ", "")

        log(f"0.5B分类原始结果: '{category}'", "DEBUG")

        pipeline_map = {
            "认知沉淀": "cognition",
            "资产盘点": "asset",
            "内容生产": "content",
        }
        # 精确匹配优先，模糊匹配兜底
        pipeline = pipeline_map.get(category, "other")
        if pipeline == "other":
            for key, val in pipeline_map.items():
                if key in (category or "") or (category or "") in key:
                    pipeline = val
                    break

        # 提取参数（简单提取）
        params = {}
        if pipeline == "cognition":
            params["text"] = user_input
        elif pipeline == "content":
            params["topic"] = user_input

        return {"pipeline": pipeline, "params": params, "confidence": 0.7}
    except Exception as e:
        log(f"0.5B意图识别失败: {e}", "WARN")
        return None


def _intent_by_rules(user_input):
    """关键词规则匹配"""
    text = user_input.lower()

    # 认知沉淀关键词
    cognition_kw = ["沉淀", "认知", "蒸馏", "归档", "记忆", "感悟", "思考", "对话", "整理这段", "把这段"]
    # 资产盘点关键词
    asset_kw = ["盘点", "检查", "扫描", "状态", "健康", "统计", "报告", "看看有多少", "资产"]
    # 内容生产关键词
    content_kw = ["写", "创作", "生成", "主题", "篇目", "大纲", "视频", "文案", "内容"]

    cognition_score = sum(1 for kw in cognition_kw if kw in text)
    asset_score = sum(1 for kw in asset_kw if kw in text)
    content_score = sum(1 for kw in content_kw if kw in text)

    scores = {"cognition": cognition_score, "asset": asset_score, "content": content_score}
    best = max(scores, key=scores.get)

    if scores[best] == 0:
        return {"pipeline": "other", "params": {"text": user_input}, "confidence": 0.0}

    total = sum(scores.values())
    confidence = scores[best] / total if total > 0 else 0

    params = {}
    if best == "cognition":
        params["text"] = user_input
    elif best == "content":
        params["topic"] = user_input

    return {"pipeline": best, "params": params, "confidence": confidence}


# ============================================================
# 三条预设流水线
# ============================================================

def pipeline_cognition(text=""):
    """
    认知沉淀线
    输入：一段对话/思考文本
    流程：认知蒸馏 → 去AI味提纯 → 归档管理 → 记忆融合
    """
    log("=" * 50)
    log("启动【认知沉淀线】")
    log("=" * 50)

    results = []

    # 1. 认知蒸馏
    r = call_skill("cognitive_sediment", text=text)
    results.append(r)

    # 2. 去AI味提纯
    r = call_skill("cognition_polish", text=text)
    results.append(r)

    # 3. 归档管理
    r = call_skill("archive_manager")
    results.append(r)

    # 4. 记忆融合
    r = call_skill("memory_fusion")
    results.append(r)

    return _summarize_pipeline("认知沉淀线", results)


def pipeline_asset():
    """
    资产盘点线
    输入：无（自动扫描）
    流程：指标分析 → 记忆同步校验 → 内容审核 → 产出校验 → 核心记忆体构建
    """
    log("=" * 50)
    log("启动【资产盘点线】")
    log("=" * 50)

    results = []

    # 1. 运行指标分析
    r = call_skill("metrics_analyzer")
    results.append(r)

    # 2. 记忆同步与完整性校验
    r = call_skill("memory_sync")
    results.append(r)

    # 3. 内容审核
    r = call_skill("content_audit")
    results.append(r)

    # 4. 产出校验
    r = call_skill("verifier_bridge")
    results.append(r)

    # 5. 核心记忆体构建
    r = call_skill("core_memory_build")
    results.append(r)

    return _summarize_pipeline("资产盘点线", results)


def pipeline_content(topic=""):
    """
    内容生产线（阴期框架版，不调用API）
    输入：主题/篇目名
    流程：深度阅读 → 参考审核 → 可视化结构 → 内容审核
    输出：内容框架+提示词草稿
    """
    log("=" * 50)
    log("启动【内容生产线·阴期框架版】")
    log(f"主题: {topic}")
    log("=" * 50)

    results = []

    # 1. 深度阅读（如果有参考文本）
    r = call_skill("critical_reading", topic=topic)
    results.append(r)

    # 2. 参考文献审核
    r = call_skill("reference_audit", topic=topic)
    results.append(r)

    # 3. 可视化结构
    r = call_skill("visualization", topic=topic)
    results.append(r)

    # 4. 内容审核
    r = call_skill("content_audit", topic=topic)
    results.append(r)

    return _summarize_pipeline("内容生产线", results)


def _summarize_pipeline(name, results):
    """汇总流水线结果"""
    ok_count = sum(1 for r in results if r and r.get("ok"))
    fail_count = len(results) - ok_count

    summary = {
        "pipeline": name,
        "total": len(results),
        "ok": ok_count,
        "failed": fail_count,
        "timestamp": datetime.now().isoformat(),
        "details": results,
    }

    log("-" * 50)
    log(f"【{name}】完成: 成功{ok_count}/{len(results)}, 失败{fail_count}")
    log("-" * 50)

    # 保存报告
    report_path = BASE_DIR / "data" / f"bypass_report_{name}_{int(time.time())}.json"
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log(f"报告已保存: {report_path}")
    except:
        pass

    return summary


# ============================================================
# 主入口
# ============================================================

def run_pipeline(pipeline_name, **kwargs):
    """
    运行指定流水线
    pipeline_name: cognition / asset / content
    """
    lock_fd = acquire_lock()
    if lock_fd is None:
        log("获取锁失败，引擎可能正在运行，稍后重试", "WARN")
        return {"ok": False, "error": "锁冲突，引擎运行中"}

    try:
        if pipeline_name == "cognition":
            return pipeline_cognition(**kwargs)
        elif pipeline_name == "asset":
            return pipeline_asset()
        elif pipeline_name == "content":
            return pipeline_content(**kwargs)
        else:
            log(f"未知流水线: {pipeline_name}", "ERROR")
            return {"ok": False, "error": f"未知流水线: {pipeline_name}"}
    finally:
        release_lock(lock_fd)


def dispatch(user_input):
    """
    主调度：意图识别 → 匹配流水线 → 执行
    """
    log("=" * 60)
    log(f"旁路调度器启动，输入: {user_input[:80]}...")
    log("=" * 60)

    # 意图识别
    intent = intent_recognize(user_input)
    pipeline = intent.get("pipeline", "other")
    params = intent.get("params", {})

    if pipeline == "other":
        log("无法匹配预设流水线，返回可用选项")
        return {
            "ok": False,
            "matched": False,
            "message": "无法识别需求，可用流水线：认知沉淀/资产盘点/内容生产",
            "available": ["认知沉淀", "资产盘点", "内容生产"],
        }

    # 执行流水线
    result = run_pipeline(pipeline, **params)
    result["intent"] = intent
    return result


def list_pipelines():
    """列出所有可用流水线"""
    return {
        "pipelines": [
            {
                "name": "cognition",
                "desc": "认知沉淀线",
                "input": "一段对话/思考文本",
                "steps": ["认知蒸馏", "去AI味提纯", "归档管理", "记忆融合"],
            },
            {
                "name": "asset",
                "desc": "资产盘点线",
                "input": "无（自动扫描）",
                "steps": ["指标分析", "记忆同步校验", "内容审核", "产出校验", "核心记忆体构建"],
            },
            {
                "name": "content",
                "desc": "内容生产线（阴期框架版）",
                "input": "主题/篇目名",
                "steps": ["深度阅读", "参考审核", "可视化结构", "内容审核"],
            },
        ]
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="技能旁路调度器")
    parser.add_argument("--pipeline", "-p", choices=["cognition", "asset", "content"],
                        help="直接指定流水线")
    parser.add_argument("--input", "-i", type=str, help="输入文本（认知沉淀/内容生产用）")
    parser.add_argument("--dispatch", "-d", type=str, help="自然语言调度（自动意图识别）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有流水线")

    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_pipelines(), ensure_ascii=False, indent=2))
    elif args.dispatch:
        result = dispatch(args.dispatch)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.pipeline:
        kwargs = {}
        if args.input:
            if args.pipeline == "cognition":
                kwargs["text"] = args.input
            elif args.pipeline == "content":
                kwargs["topic"] = args.input
        result = run_pipeline(args.pipeline, **kwargs)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        parser.print_help()
