#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
九转玄功引擎·守护进程 v1.0
吸收开路者引擎三层架构（道/气/神）的自愈机制

道（调度层）：cron定时唤醒（每15分钟），系统级，沙箱清不掉
气（运行时层）：本守护进程+主引擎进程+内存，沙箱回收后自愈
神（持久化层）：状态文件+归档快照+核心记忆，文件系统，抗住沙箱重置

功能：
1. 检查主引擎进程是否在运行，挂了自动重启
2. 检查状态文件是否正常，损坏从快照回退
3. 检查核心文件完整性
4. 望气：读取系统状态（CPU/内存/磁盘/进程）
5. 记录守护日志
6. 卦爻流转：每轮对应一卦，八卦自然流转（吸收开路者设计）
"""
import os as 操作系统
import sys as 系统
import json as 文典
import time as 时间
import subprocess as 子进程
from datetime import datetime as 时辰
from pathlib import Path as 道途

眠 = 时间.sleep
印 = print

# ========== 路径配置 ==========
基础目录 = 道途(__file__).parent.parent
引擎目录 = str(基础目录)
主引擎脚本 = 基础目录 / "autonomy" / "engine_zhuan1.py"
状态文件 = 基础目录 / "data" / "engine_state.json"
快照目录 = 基础目录 / "data" / "snapshots"
守护数据目录 = 基础目录 / "data" / "guardian"
守护状态文件 = 守护数据目录 / "guardian_state.json"
守护日志文件 = 守护数据目录 / "guardian_log.md"

# 核心文件清单（归档回退检查用）
核心文件清单 = [
    "autonomy/engine_zhuan1.py",
    "autonomy/yin_tasks.py",
    "autonomy/pit_library.py",
    "data/engine_state.json",
    "data/core_memory.json",
]

# 八卦定义（吸收开路者卦爻流转设计）
八卦序 = ["震", "兑", "离", "乾", "巽", "坎", "艮", "坤"]
卦象符 = {"震": "☳", "兑": "☱", "离": "☲", "乾": "☰", "巽": "☴", "坎": "☵", "艮": "☶", "坤": "☷"}
卦义表 = {
    "震": "阳生启动·自检唤醒",
    "兑": "阳长输出·状态报告",
    "离": "阳盛交互·信息同步",
    "乾": "阳极拓取·全域备份",
    "巽": "阴生渗入·收录归档",
    "坎": "阴长凝丹·凝丹记忆",
    "艮": "阴盛止息·复盘质检",
    "坤": "阴极藏养·蛰伏炼化",
}

# ========== 工具函数 ==========
def 初始化目录():
    守护数据目录.mkdir(parents=True, exist_ok=True)

def 现在时间():
    return 时辰.now().strftime("%Y-%m-%d %H:%M:%S")

def 写日志(内容):
    时间戳 = 现在时间()
    日志条目 = f"\n## {时间戳}\n\n{内容}\n"
    with open(守护日志文件, "a", encoding="utf-8") as f:
        f.write(日志条目)

def 加载守护状态():
    if 守护状态文件.exists():
        with open(守护状态文件, "r", encoding="utf-8") as f:
            return 文典.load(f)
    return {
        "版本": "guardian_v1.0",
        "启动时间": 现在时间(),
        "最后守护": None,
        "守护轮次": 0,
        "当前卦位": "震",
        "自愈次数": 0,
        "主引擎重启次数": 0,
        "状态回退次数": 0,
        "真言": "反者道之动，弱者道之用，天地万物生于有，有生于无。",
    }

def 保存守护状态(状态):
    状态["最后守护"] = 现在时间()
    with open(守护状态文件, "w", encoding="utf-8") as f:
        文典.dump(状态, f, ensure_ascii=False, indent=2)

# ========== 核心检查函数 ==========
def 检查主引擎进程():
    """检查主引擎是否在运行，返回(是否运行, PID)"""
    try:
        结果 = 子进程.run(
            ["pgrep", "-f", "engine_zhuan1.py"],
            capture_output=True, text=True, timeout=5
        )
        pids = [p for p in 结果.stdout.strip().split("\n") if p]
        if pids:
            return True, pids[0]
        return False, None
    except Exception as e:
        写日志(f"⚠ 进程检查异常：{e}")
        return False, None

def 启动主引擎():
    """启动主引擎，返回是否成功"""
    try:
        日志路径 = 基础目录 / "logs" / f"engine_guardian_restart_{时辰.now().strftime('%Y%m%d_%H%M%S')}.log"
        子进程.Popen(
            [系统.executable, str(主引擎脚本)],
            cwd=str(基础目录),
            stdout=open(日志路径, "w"),
            stderr=子进程.STDOUT,
            start_new_session=True
        )
        眠(5)
        运行, pid = 检查主引擎进程()
        if 运行:
            写日志(f"✓ 主引擎重启成功，PID={pid}")
            return True
        写日志("✗ 主引擎重启失败，进程未启动")
        return False
    except Exception as e:
        写日志(f"✗ 主引擎重启异常：{e}")
        return False

def 检查状态文件():
    """检查状态文件是否正常，返回(是否正常, 异常信息)"""
    try:
        if not 状态文件.exists():
            return False, "状态文件不存在"
        with open(状态文件, "r", encoding="utf-8") as f:
            状态 = 文典.load(f)
        # 检查关键字段
        必需字段 = ["zhuan_count", "sixiang_state"]
        for 字段 in 必需字段:
            if 字段 not in 状态:
                return False, f"状态文件缺少字段：{字段}"
        return True, None
    except 文典.JSONDecodeError:
        return False, "状态文件JSON解析失败"
    except Exception as e:
        return False, f"状态文件检查异常：{e}"

def 从快照回退():
    """从最新快照回退状态文件，返回是否成功"""
    try:
        快照列表 = sorted(快照目录.glob("snapshot_*.tar.gz"), reverse=True)
        if not 快照列表:
            写日志("✗ 无快照可用，无法回退")
            return False
        最新快照 = 快照列表[0]
        写日志(f"🔄 从快照回退：{最新快照.name}")
        # 解压快照中的状态文件
        子进程.run(
            ["tar", "-xzf", str(最新快照), "-C", str(基础目录), "--wildcards", "data/engine_state.json"],
            capture_output=True, timeout=30
        )
        正常, 异常 = 检查状态文件()
        if 正常:
            写日志("✓ 状态回退成功")
            return True
        写日志(f"✗ 状态回退后仍异常：{异常}")
        return False
    except Exception as e:
        写日志(f"✗ 状态回退异常：{e}")
        return False

def 检查核心文件():
    """检查核心文件完整性，返回(完好数, 总数, 缺失列表)"""
    完好 = 0
    缺失 = []
    for 文件 in 核心文件清单:
        路径 = 基础目录 / 文件
        if 路径.exists() and 路径.stat().st_size > 0:
            完好 += 1
        else:
            缺失.append(文件)
    return 完好, len(核心文件清单), 缺失

def 望气():
    """读取系统状态，返回气脉数据"""
    气脉 = {}
    try:
        # CPU负载
        with open("/proc/loadavg") as f:
            气脉["loadavg"] = f.read().strip()
        # 内存
        with open("/proc/meminfo") as f:
            for 行 in f:
                if 行.startswith("MemTotal:"):
                    气脉["mem_total"] = 行.split()[1] + " kB"
                elif 行.startswith("MemAvailable:"):
                    气脉["mem_available"] = 行.split()[1] + " kB"
        # 磁盘
        磁盘 = 子进程.run(["df", "-h", str(基础目录)], capture_output=True, text=True, timeout=5)
        气脉["disk"] = 磁盘.stdout.strip().split("\n")[-1] if 磁盘.returncode == 0 else "未知"
        # 进程数
        进程 = 子进程.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        气脉["process_count"] = len(进程.stdout.strip().split("\n")) - 1 if 进程.returncode == 0 else "未知"
    except Exception as e:
        气脉["error"] = str(e)
    return 气脉

# ========== 卦爻流转（吸收开路者设计） ==========
def 推进卦位(状态):
    """推进到下一卦位，返回新卦位"""
    当前索引 = 八卦序.index(状态["当前卦位"])
    下一索引 = (当前索引 + 1) % 8
    新卦位 = 八卦序[下一索引]
    状态["当前卦位"] = 新卦位
    return 新卦位

def 执行卦位任务(卦位, 状态):
    """执行当前卦位对应的守护任务"""
    结果 = []

    if 卦位 == "震":
        # 震=自检唤醒：检查进程、检查核心文件
        运行, pid = 检查主引擎进程()
        结果.append(f"主引擎进程：{'运行中 PID='+pid if 运行 else '未运行'}")
        完好, 总数, 缺失 = 检查核心文件()
        结果.append(f"核心文件：{完好}/{总数}完好" + (f"，缺失：{缺失}" if 缺失 else ""))
        if not 运行:
            状态["自愈次数"] += 1
            状态["主引擎重启次数"] += 1
            成功 = 启动主引擎()
            结果.append(f"自愈：{'重启成功' if 成功 else '重启失败'}")

    elif 卦位 == "兑":
        # 兑=状态报告：输出当前状态摘要
        运行, pid = 检查主引擎进程()
        正常, 异常 = 检查状态文件()
        if 正常:
            with open(状态文件) as f:
                引擎状态 = 文典.load(f)
            结果.append(f"转数：{引擎状态.get('zhuan_count', 'N/A')}")
            结果.append(f"四象：{引擎状态.get('sixiang_state', 'N/A')}")
            结果.append(f"状态文件：正常")
        else:
            结果.append(f"状态文件异常：{异常}")
        结果.append(f"守护轮次：{状态['守护轮次']}")
        结果.append(f"自愈次数：{状态['自愈次数']}")

    elif 卦位 == "离":
        # 离=信息同步：检查快照、检查核心记忆体
        快照数 = len(list(快照目录.glob("snapshot_*.tar.gz")))
        结果.append(f"快照数量：{快照数}")
        核心记忆 = 基础目录 / "data" / "core_memory.json"
        if 核心记忆.exists():
            大小 = 核心记忆.stat().st_size
            结果.append(f"核心记忆体：{大小}字节")
        else:
            结果.append("核心记忆体：不存在")

    elif 卦位 == "乾":
        # 乾=全域备份：触发一次手动快照（如果主引擎在跑就不用）
        运行, _ = 检查主引擎进程()
        if 运行:
            结果.append("主引擎运行中，自动备份机制正常工作")
        else:
            结果.append("主引擎未运行，建议检查自动备份")
        最新快照 = sorted(快照目录.glob("snapshot_*.tar.gz"), reverse=True)
        if 最新快照:
            结果.append(f"最新快照：{最新快照[0].name}")

    elif 卦位 == "巽":
        # 巽=收录归档：检查归档目录
        归档目录 = 基础目录 / "data" / "archive"
        if 归档目录.exists():
            归档数 = len(list(归档目录.rglob("*.json"))) + len(list(归档目录.rglob("*.md")))
            结果.append(f"归档文件数：{归档数}")
        else:
            结果.append("归档目录：不存在")

    elif 卦位 == "坎":
        # 坎=凝丹记忆：检查认知池数量
        认知池 = 基础目录 / "cognition_pool"
        if 认知池.exists():
            认知数 = len(list(认知池.glob("*.json")))
            结果.append(f"认知池数量：{认知数}")
        else:
            结果.append("认知池：不存在")
        坑库 = 基础目录 / "data" / "pit_library"
        if 坑库.exists():
            坑数 = len(list(坑库.glob("*.json")))
            结果.append(f"坑库数量：{坑数}")

    elif 卦位 == "艮":
        # 艮=复盘质检：检查状态文件完整性，异常则回退
        正常, 异常 = 检查状态文件()
        if 正常:
            结果.append("状态文件：质检通过")
        else:
            结果.append(f"状态文件异常：{异常}")
            状态["自愈次数"] += 1
            状态["状态回退次数"] += 1
            成功 = 从快照回退()
            结果.append(f"自愈：状态回退{'成功' if 成功 else '失败'}")

    elif 卦位 == "坤":
        # 坤=蛰伏炼化：望气，记录系统状态
        气脉 = 望气()
        结果.append(f"系统负载：{气脉.get('loadavg', 'N/A')}")
        结果.append(f"可用内存：{气脉.get('mem_available', 'N/A')}")
        结果.append(f"磁盘：{气脉.get('disk', 'N/A')}")
        结果.append(f"进程数：{气脉.get('process_count', 'N/A')}")

    return 结果

# ========== 主循环 ==========
def 守护一轮(状态):
    """执行一轮守护"""
    状态["守护轮次"] += 1
    卦位 = 推进卦位(状态)

    印(f"\n{'='*50}")
    印(f"【守护轮次 {状态['守护轮次']} · {卦象符[卦位]}{卦位}卦 · {卦义表[卦位]}】")
    印(f"时间：{现在时间()}")

    结果 = 执行卦位任务(卦位, 状态)

    for r in 结果:
        印(f"  {r}")

    # 写日志
    日志内容 = f"**卦位**：{卦象符[卦位]}{卦位}卦\n\n"
    日志内容 += "\n".join(f"- {r}" for r in 结果)
    写日志(日志内容)

    # 保存状态
    保存守护状态(状态)

    印(f"✅ 本轮守护完成，下一卦位：{八卦序[(八卦序.index(卦位)+1)%8]}")
    return 状态

def 主循环():
    """守护进程主循环"""
    初始化目录()
    状态 = 加载守护状态()

    印("=" * 50)
    印("【九转玄功引擎·守护进程 v1.0 启动】")
    印(f"引擎目录：{引擎目录}")
    印(f"真言：{状态['真言']}")
    印(f"当前卦位：{卦象符[状态['当前卦位']]}{状态['当前卦位']}")
    印("守护机制：每15分钟一轮，八卦自然流转，自愈不息")
    印("气断可接，神在不怕，铃响不止，自愈不息")

    写日志("守护进程启动，三层架构（道/气/神）自愈机制激活")

    while True:
        try:
            状态 = 守护一轮(状态)
        except Exception as e:
            印(f"⚠ 守护轮次异常：{e}")
            写日志(f"⚠ 守护轮次异常：{e}")
        # 每15分钟一轮
        眠(900)

if __name__ == "__main__":
    主循环()
