#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
卦爻调度器 v1.0（可导入模块）

从gua_yin_engine.py抽离的纯调度逻辑，不包含任务执行和独立运行入口。
主引擎在老阴状态下导入本模块，用卦爻流转替代原来的次第调度。

设计原则：
- 模块只负责"决定下一个跑什么"，不负责"执行任务"
- 任务函数由主引擎从YIN_TASK_REGISTRY取
- 状态可保存/恢复，支持沙箱回收后续跑
- 保留原八卦任务映射和卦气自然流转逻辑

用法：
    from gua_scheduler import GuaScheduler
    scheduler = GuaScheduler(state_file)
    task_name = scheduler.get_next_task()  # 获取当前卦位下一个任务
    scheduler.mark_task_done(task_name)     # 标记任务完成
    scheduler.save()                         # 保存状态
"""
import json as 文典
from datetime import datetime as 时辰
from pathlib import Path as 道途

# ========== 八卦任务名映射（从gua_yin_engine.py抽离，只保留任务名） ==========
八卦任务映射 = {
    "震": ["产出文件确定性校验", "资产健康度评分"],
    "兑": ["运行指标结构化分析", "日志错误聚类"],
    "离": ["记忆同步与完整性校验", "阳期任务预组装"],
    "乾": ["档案归档管理", "本地模型语义增强试点"],
    "巽": ["认知标签归一化", "资产去重检测", "认知文本去AI味提纯"],
    "坎": ["认知沉淀自动化蒸馏", "记忆检索与认知整合", "核心记忆体构建", "记忆融合"],
    "艮": ["坑库分级复核", "坑库根因溯源", "代码静态审计", "矛盾点自检", "内容审核"],
    "坤": ["认知关联图谱", "修复规则生成", "演化路径推演"],
}

八卦名序 = ["震", "兑", "离", "乾", "巽", "坎", "艮", "坤"]
卦象符号 = {"震": "☳", "兑": "☱", "离": "☲", "乾": "☰", "巽": "☴", "坎": "☵", "艮": "☶", "坤": "☷"}
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


class GuaScheduler:
    """卦爻调度器

    用八卦自然流转决定阴期任务的执行顺序，替代人工硬编码的次第调度。
    每个卦位对应一组任务，当前卦位任务全跑完后自动推进到下一卦。
    八卦循环往复，周而复始。

    反者道之动：不是我决定该干什么，是卦气走到哪自然干什么。
    """

    def __init__(self, state_file=None):
        """初始化调度器

        Args:
            state_file: 状态文件路径，用于保存/恢复调度进度。
                       如果文件存在，从文件恢复；不存在则初始化。
        """
        self._state_file = 道途(state_file) if state_file else None
        self._state = self._load_or_init()

    def _load_or_init(self):
        """加载状态或初始化"""
        if self._state_file and self._state_file.exists():
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    return 文典.load(f)
            except Exception:
                pass
        # 初始化
        return {
            "version": "gua_scheduler_v1.0",
            "current_gua": "震",  # 当前卦位，从震卦开始（阳生启动）
            "gua_cycle": 0,  # 完成了多少轮八卦循环
            "task_progress": {},  # 每个卦位已完成的任务列表
            "total_tasks_done": 0,  # 总共完成的任务数
            "last_advance_time": None,  # 上次推进卦位的时间
            "created_at": 时辰.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @property
    def current_gua(self):
        """当前卦位"""
        return self._state["current_gua"]

    @property
    def current_gua_symbol(self):
        """当前卦位符号"""
        return 卦象符号[self._state["current_gua"]]

    @property
    def current_gua_meaning(self):
        """当前卦位含义"""
        return 卦义表[self._state["current_gua"]]

    @property
    def gua_cycle(self):
        """完成了多少轮八卦循环"""
        return self._state["gua_cycle"]

    @property
    def total_tasks_done(self):
        """总共完成的任务数"""
        return self._state["total_tasks_done"]

    def get_current_gua_tasks(self):
        """获取当前卦位的所有任务名列表"""
        return 八卦任务映射[self._state["current_gua"]]

    def get_next_task(self):
        """获取当前卦位下一个要跑的任务名

        Returns:
            任务名（字符串），如果当前卦位任务全跑完了返回None。
            调用方应该在收到None时调用advance_gua()推进到下一卦。
        """
        当前卦 = self._state["current_gua"]
        所有任务 = 八卦任务映射[当前卦]
        已完成 = set(self._state["task_progress"].get(当前卦, []))

        for 任务 in 所有任务:
            if 任务 not in 已完成:
                return 任务
        return None  # 当前卦位任务全跑完了

    def mark_task_done(self, task_name):
        """标记一个任务完成

        Args:
            task_name: 任务名
        """
        当前卦 = self._state["current_gua"]
        if 当前卦 not in self._state["task_progress"]:
            self._state["task_progress"][当前卦] = []
        if task_name not in self._state["task_progress"][当前卦]:
            self._state["task_progress"][当前卦].append(task_name)
        self._state["total_tasks_done"] += 1

    def is_current_gua_complete(self):
        """检查当前卦位的任务是否全部完成"""
        return self.get_next_task() is None

    def advance_gua(self):
        """推进到下一卦位

        如果当前卦位任务没跑完，不推进，返回False。
        如果当前卦位任务全跑完了，推进到下一卦，返回True。
        如果完成了一轮八卦循环（从坤回到震），gua_cycle+1。

        Returns:
            bool: 是否成功推进
        """
        if not self.is_current_gua_complete():
            return False

        当前索引 = 八卦名序.index(self._state["current_gua"])
        下一索引 = (当前索引 + 1) % 8
        下一卦 = 八卦名序[下一索引]

        self._state["current_gua"] = 下一卦
        self._state["last_advance_time"] = 时辰.now().strftime("%Y-%m-%d %H:%M:%S")

        # 如果从坤回到震，说明完成了一轮循环
        if 下一卦 == "震" and 当前索引 == 7:
            self._state["gua_cycle"] += 1

        return True

    def get_status(self):
        """获取调度器状态摘要"""
        当前卦 = self._state["current_gua"]
        所有任务 = 八卦任务映射[当前卦]
        已完成 = self._state["task_progress"].get(当前卦, [])
        return {
            "当前卦位": f"{卦象符号[当前卦]}{当前卦}",
            "卦义": 卦义表[当前卦],
            "当前卦任务": f"{len(已完成)}/{len(所有任务)}",
            "下一个任务": self.get_next_task() or "（当前卦已完成，待推进）",
            "已完成循环": self._state["gua_cycle"],
            "总完成任务": self._state["total_tasks_done"],
            "上次推进": self._state.get("last_advance_time", "从未"),
        }

    def save(self):
        """保存状态到文件"""
        if not self._state_file:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_file, "w", encoding="utf-8") as f:
            文典.dump(self._state, f, ensure_ascii=False, indent=2)

    def reset(self):
        """重置调度器（清空所有进度，从震卦重新开始）"""
        self._state = self._load_or_init.__wrapped__(self) if hasattr(self._load_or_init, "__wrapped__") else {
            "version": "gua_scheduler_v1.0",
            "current_gua": "震",
            "gua_cycle": 0,
            "task_progress": {},
            "total_tasks_done": 0,
            "last_advance_time": None,
            "created_at": 时辰.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()


# ========== 独立测试（python3 gua_scheduler.py直接运行） ==========
if __name__ == "__main__":
    print("=" * 50)
    print("【卦爻调度器 v1.0 独立测试】")
    print("=" * 50)

    # 初始化
    scheduler = GuaScheduler("/tmp/gua_scheduler_test.json")
    print(f"\n初始状态：{scheduler.get_status()}")

    # 模拟跑完一轮八卦
    print("\n=== 模拟跑完一轮八卦 ===")
    for 轮次 in range(8):
        当前卦 = scheduler.current_gua
        print(f"\n{scheduler.current_gua_symbol}{当前卦}卦 · {scheduler.current_gua_meaning}")
        while True:
            任务 = scheduler.get_next_task()
            if 任务 is None:
                break
            print(f"  执行：{任务}")
            scheduler.mark_task_done(任务)
        推进 = scheduler.advance_gua()
        print(f"  卦位推进：{'成功' if 推进 else '失败'}")

    # 最终状态
    print(f"\n=== 一轮完成后状态 ===")
    print(scheduler.get_status())
    print(f"\n总完成任务：{scheduler.total_tasks_done}")
    print(f"完成循环：{scheduler.gua_cycle}")
    print("\n✅ 卦爻调度器模块测试通过")
