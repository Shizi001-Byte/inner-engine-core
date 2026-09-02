#!/usr/bin/env python3
"""
批次认知提取脚本
从436个批次文件（cog_*.json，内含cognitions列表）中
提取S级认知，转成标准单条认知格式（顶层有density.grade），
写入认知池，使load_top_cognitions()能加载到它们
"""
import json
import os
import hashlib
from datetime import datetime

COGNITION_POOL = "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/cognition_pool"

def text_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

def main():
    # 第一步：扫描所有批次文件，收集S级认知
    s_cogs = []
    seen_hashes = set()
    batch_scanned = 0
    total_in_batches = 0

    for f in sorted(os.listdir(COGNITION_POOL)):
        if f.startswith('cog_') and f.endswith('.json') and not f.startswith('core_axiom'):
            path = os.path.join(COGNITION_POOL, f)
            try:
                d = json.load(open(path))
                if 'cognitions' in d and isinstance(d['cognitions'], list):
                    batch_scanned += 1
                    task_type = d.get('task_type', 'unknown')
                    for c in d['cognitions']:
                        if isinstance(c, dict):
                            total_in_batches += 1
                            grade = c.get('density_grade', c.get('grade', 'unknown'))
                            text = c.get('text', '').strip()
                            if grade == 'S' and text and len(text) > 10:
                                h = text_hash(text)
                                if h not in seen_hashes:
                                    seen_hashes.add(h)
                                    s_cogs.append({
                                        'text': text,
                                        'source': c.get('source', ''),
                                        'type': c.get('type', task_type),
                                        'density': c.get('density', 0),
                                        'density_details': c.get('density_details', {}),
                                        'batch_file': f,
                                        'task_type': task_type,
                                        'hash': h
                                    })
            except Exception as e:
                pass

    print(f"扫描批次文件: {batch_scanned} 个")
    print(f"批次内认知总数: {total_in_batches} 条")
    print(f"S级认知（去重后）: {len(s_cogs)} 条")

    # 第二步：转成标准格式写入
    now = datetime.now().isoformat()
    written = 0
    for i, c in enumerate(s_cogs):
        cog_id = f"cog_S_extracted_{i+1:04d}"
        item = {
            "id": cog_id,
            "created_at": now,
            "level": "体系级",
            "status": "核心锚定",
            "title": c['text'][:50],
            "density": {
                "info_density": c['density'] if isinstance(c['density'], (int, float)) else 0.9,
                "action_density": 0.7,
                "relation_density": 0.8,
                "grade": "S"
            },
            "core_statement": c['text'],
            "key_points": [],  # 单条认知的要点留空，后续可补
            "origin": {
                "source": "引擎任务自动蒸馏",
                "context": f"从批次文件{c['batch_file']}中提取的S级认知，原任务类型={c['task_type']}",
                "original_source": c['source']
            },
            "related_concepts": [],
            "extracted_from_batch": c['batch_file'],
            "original_hash": c['hash']
        }
        path = os.path.join(COGNITION_POOL, f"{cog_id}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        written += 1

    print(f"\n写入标准格式S级认知: {written} 条")
    print(f"认知池现在有: core_axiom 21条 + 早期人工6条 + 新提取S级{written}条 + 批次文件436个")
    print(f"引擎下次启动时 load_top_cognitions() 会按S/A/B优先级加载这些认知")

    # 第三步：打印前10条S级认知预览
    print(f"\n=== 前10条S级认知预览 ===")
    for i, c in enumerate(s_cogs[:10]):
        print(f"{i+1}. [{c['task_type']}] {c['text'][:90]}")

if __name__ == "__main__":
    main()
