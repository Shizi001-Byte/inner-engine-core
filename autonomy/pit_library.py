"""
三级全域坑库体系
L1工程级 + L2方法级 + L3规律级
核心认知：坑不是意外，是单向运动走到临界点的必然反噬
锚定：反者道之动，弱者道之用，天地万物生于有，有生于无
"""
import json
import hashlib
from datetime import datetime
from pathlib import Path

PIT_LIB_DIR = Path(__file__).parent.parent / "data" / "pit_library"
PIT_LIB_DIR.mkdir(parents=True, exist_ok=True)

LEVELS = {
    "L1": "工程级",  # 代码bug、配置错误、API踩坑
    "L2": "方法级",  # 做事误区、认知偏差、路径依赖
    "L3": "规律级",  # 社会规律、周期反噬、系统反转
}


def pit_filepath(level, pit_id):
    return PIT_LIB_DIR / f"{level}_{pit_id}.json"


def add_pit(level, name, phenomenon, root_cause, critical_point, backlash_path, safe_boundary, tags=None):
    """
    添加一个坑到坑库
    五要素：现象、根因、临界点、反噬路径、避坑边界
    """
    if level not in LEVELS:
        raise ValueError(f"无效层级: {level}")

    pit_id = hashlib.md5((name + phenomenon[:50]).encode()).hexdigest()[:10]
    pit = {
        "id": pit_id,
        "level": level,
        "level_name": LEVELS[level],
        "name": name,
        "phenomenon": phenomenon,
        "root_cause": root_cause,
        "critical_point": critical_point,
        "backlash_path": backlash_path,
        "safe_boundary": safe_boundary,
        "tags": tags or [],
        "created_at": datetime.now().isoformat(),
        "hit_count": 0,
        "last_hit": None,
    }

    fpath = pit_filepath(level, pit_id)
    with open(fpath, "w") as f:
        json.dump(pit, f, indent=2, ensure_ascii=False)
    return pit_id


def get_pits(level=None, tags=None):
    """获取坑库中的坑"""
    pits = []
    for f in PIT_LIB_DIR.glob("*.json"):
        try:
            with open(f) as fh:
                pit = json.load(fh)
            if level and pit.get("level") != level:
                continue
            if tags:
                if not any(t in pit.get("tags", []) for t in tags):
                    continue
            pits.append(pit)
        except:
            pass
    return pits


def match_pits(task_type, content="", level="L1"):
    """匹配与当前任务相关的坑，用于前置校验"""
    pits = get_pits(level=level)
    matched = []
    text = (task_type + " " + content).lower()
    for pit in pits:
        # 简单关键词匹配
        keywords = pit.get("tags", []) + [pit["name"]]
        for kw in keywords:
            if kw.lower() in text:
                matched.append(pit)
                break
    return matched[:3]


def format_pit_warning(pits):
    """格式化坑预警为任务注入文本"""
    if not pits:
        return ""
    lines = ["【坑库预警】以下是同类任务的历史踩坑经验："]
    for i, p in enumerate(pits, 1):
        lines.append(f"{i}. [{p['level_name']}] {p['name']}")
        lines.append(f"   现象：{p['phenomenon'][:60]}")
        lines.append(f"   避坑：{p['safe_boundary'][:60]}")
    return "\n".join(lines)


def record_hit(pit_id, level="L1"):
    """记录坑被命中（实际踩坑了）"""
    fpath = pit_filepath(level, pit_id)
    if fpath.exists():
        with open(fpath) as f:
            pit = json.load(f)
        pit["hit_count"] += 1
        pit["last_hit"] = datetime.now().isoformat()
        with open(fpath, "w") as f:
            json.dump(pit, f, indent=2, ensure_ascii=False)


def get_pit_stats():
    """获取坑库统计"""
    stats = {"total": 0, "by_level": {}, "total_hits": 0}
    for level, name in LEVELS.items():
        pits = get_pits(level=level)
        stats["by_level"][level] = {"name": name, "count": len(pits)}
        stats["total"] += len(pits)
        stats["total_hits"] += sum(p.get("hit_count", 0) for p in pits)
    return stats


def cross_level_migration():
    """
    跨域迁移机制：自下而上提炼
    从L1工程坑提炼L2方法规律，从L2方法坑验证L3规律逻辑
    """
    # 这个函数用于人工触发的跨层级关联分析
    # 自动关联：相同tags的坑建立关联
    associations = {}
    all_pits = get_pits()
    for pit in all_pits:
        for tag in pit.get("tags", []):
            associations.setdefault(tag, []).append(f"{pit['level']}:{pit['name']}")
    return {k: v for k, v in associations.items() if len(v) > 1}
