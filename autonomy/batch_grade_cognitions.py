#!/usr/bin/env python3
"""
批量给旧无级认知补充分级。
在空闲模式里运行，不影响主循环。
每次处理50条，避免内存溢出。
"""
import json, glob, os, sys
from pathlib import Path

COGNITION_POOL = Path(__file__).parent.parent / "cognition_pool"

def calc_density_simple(text):
    """简化版密度计算：信息密度+可执行密度+关联密度"""
    if not text or len(text) < 10:
        return 0.0, "C"
    # 信息密度：核心概念数（按标点分句，有效句子数）
    sentences = [s.strip() for s in text.replace('。', '\n').replace('！', '\n').replace('？', '\n').split('\n') if len(s.strip()) > 5]
    info_density = min(1.0, len(sentences) / 5.0)
    # 可执行密度：是否包含动作词/数字/具体方案
    action_words = ['应该', '需要', '可以', '必须', '建议', '实现', '设计', '优化', '修复', '构建', '建立', '配置', '部署']
    has_action = any(w in text for w in action_words)
    has_number = any(c.isdigit() for c in text)
    exec_density = 0.5 + (0.25 if has_action else 0) + (0.25 if has_number else 0)
    # 关联密度：是否引用了体系内概念
    sys_concepts = ['反者道之动', '阴阳', '九转', '九维', '引擎', '认知', '坑库', '自进化', '筑基', '炼精', '结丹', '养气', '育神', '通神', '还虚', '阳神', '合道']
    ref_count = sum(1 for c in sys_concepts if c in text)
    ref_density = min(1.0, ref_count / 3.0)
    # 综合密度
    density = (info_density * 0.4 + exec_density * 0.3 + ref_density * 0.3)
    # 套话惩罚
    cliche_words = ['赋能', '抓手', '闭环思维', '底层逻辑', '顶层设计', '生态闭环', '价值赋能']
    for w in cliche_words:
        if w in text:
            density -= 0.1
    density = max(0.0, min(1.0, density))
    # 分级
    if density >= 0.7:
        grade = "S"
    elif density >= 0.5:
        grade = "A"
    elif density >= 0.3:
        grade = "B"
    else:
        grade = "C"
    return round(density, 2), grade

def main():
    files = sorted(glob.glob(str(COGNITION_POOL / "cog_*.json")), key=lambda x: os.path.getmtime(x))
    total = len(files)
    print(f"认知池共{total}个文件")
    
    processed = 0
    graded = 0
    skipped = 0
    c_count = 0
    
    for f in files:
        try:
            data = json.load(open(f))
            cogs = data.get("cognitions", [])
            needs_update = False
            for c in cogs:
                if not c.get("density_grade") or c.get("density") is None:
                    density, grade = calc_density_simple(c.get("text", ""))
                    c["density"] = density
                    c["density_grade"] = grade
                    needs_update = True
                    graded += 1
                    if grade == "C":
                        c_count += 1
                else:
                    skipped += 1
            if needs_update:
                with open(f, "w") as wf:
                    json.dump(data, wf, indent=2, ensure_ascii=False)
            processed += 1
            if processed % 100 == 0:
                print(f"  已处理{processed}/{total}，补分级{graded}条，跳过{skipped}条，C级{c_count}条")
        except Exception as e:
            print(f"  处理{os.path.basename(f)}失败: {e}")
    
    print(f"\n完成！共处理{processed}个文件，补分级{graded}条，跳过{skipped}条，C级{c_count}条")

if __name__ == "__main__":
    main()
