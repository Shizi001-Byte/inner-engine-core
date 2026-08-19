"""引擎提升自动记录 - 每转完成后对比指标，有提升自动写入认知池"""
import json, os, glob
from datetime import datetime

ENGINE_DIR = "/sandboxdata/workspace/file/engine_v7_2"
COG_DIR = f"{ENGINE_DIR}/cognition_pool"
PROGRESS_FILE = f"{ENGINE_DIR}/data/progress_history.json"

def get_current_metrics(state):
    """提取当前关键指标"""
    return {
        "zhuan": state.get("zhuan_count", 0),
        "total_completed": state.get("total_completed", 0),
        "cognition_count": state.get("cognition_count", 0),
        "pit_count": len(glob.glob(f"{ENGINE_DIR}/data/pit_library/*.json")),
        "snapshot_count": len(glob.glob(f"{ENGINE_DIR}/data/snapshots/*.tar.gz")),
        "task_usage_count": len(state.get("task_usage", {})),
        "failure_fingerprints": len(state.get("failure_fingerprints", {})),
        "nine_dim_total": sum(v.get("task_count",0) for v in state.get("nine_dim_progress",{}).values()),
        "timestamp": datetime.now().isoformat()
    }

def record_progress(state):
    """记录本转指标，与上一转对比，有提升写入认知池"""
    current = get_current_metrics(state)
    # 读取历史
    history = []
    if os.path.exists(PROGRESS_FILE):
        try:
            history = json.load(open(PROGRESS_FILE))
        except:
            history = []
    
    if not history:
        history.append(current)
        json.dump(history, open(PROGRESS_FILE,'w'), indent=2, ensure_ascii=False)
        return
    
    last = history[-1]
    improvements = []
    for key in ["total_completed","cognition_count","pit_count","snapshot_count","task_usage_count","nine_dim_total"]:
        diff = current.get(key,0) - last.get(key,0)
        if diff > 0:
            improvements.append(f"{key}+{diff}")
    
    if improvements:
        cog = {
            "task_id": f"progress_zhuan{current['zhuan']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "task_type": "cog",
            "cognitions": [{
                "text": f"第{current['zhuan']}转提升记录：{', '.join(improvements)}。累计完成{current['total_completed']}任务，认知{current['cognition_count']}条，坑库{current['pit_count']}个，快照{current['snapshot_count']}个。引擎自进化指标持续增长。",
                "density": 0.7,
                "quality": "B",
                "source": "progress_tracker自动记录",
                "metrics": current
            }],
            "generated_at": datetime.now().isoformat(),
            "engine_zhuan": current["zhuan"]
        }
        cog_path = f"{COG_DIR}/cog_{datetime.now().strftime('%Y%m%d_%H%M%S')}_progress_zhuan{current['zhuan']}.json"
        json.dump(cog, open(cog_path,'w'), indent=2, ensure_ascii=False)
    
    history.append(current)
    # 只保留最近100转
    if len(history) > 100:
        history = history[-100:]
    json.dump(history, open(PROGRESS_FILE,'w'), indent=2, ensure_ascii=False)
