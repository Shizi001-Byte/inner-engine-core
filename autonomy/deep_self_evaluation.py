#!/usr/bin/env python3
"""
凡心引擎·长链路深度自评估
学着星卷的方式：收集材料→构造prompt→调用云端模型→四段式输出
四段式：问题清单→根因分析→优化方向→优先级排序
"""
import json, time, urllib.request, os, glob
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
ENGINE_FILE = BASE_DIR / "autonomy" / "engine_zhuan1.py"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
PIT_DIR = BASE_DIR / "data" / "pit_library"
OUTPUT_DIR = BASE_DIR / "cognition"

API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = "glm-5-2-260617"  # A主，编码能力最强

def collect_materials():
    """收集核心材料"""
    materials = {}
    
    # 1. 引擎状态
    state = json.load(open(STATE_FILE))
    materials["state"] = {
        "zhuan_count": state["zhuan_count"],
        "total_completed": state["total_completed"],
        "cognition_count": state["cognition_count"],
        "tasks_failed": state.get("tasks_failed", 0),
        "goal_tasks": len(state.get("goal_tasks", [])),
        "nine_dim": {d: v.get("task_count",0) for d,v in state.get("nine_dim_progress",{}).items()},
        "engine_a_used": state["engine_a"]["tokens_used"],
        "engine_b_used": state["engine_b"]["tokens_used"],
        "engine_c_used": state["engine_c"]["tokens_used"],
        "idle_run_count": state.get("idle_run_count", 0),
    }
    
    # 2. 坑库摘要（只取标题和根因）
    pits = []
    for pf in glob.glob(str(PIT_DIR / "*.json"))[:20]:
        try:
            p = json.load(open(pf))
            pits.append({
                "id": p.get("id", os.path.basename(pf)),
                "level": p.get("level", "?"),
                "title": p.get("title", p.get("phenomenon", "?")),
                "root_cause": p.get("root_cause", "")[:100],
            })
        except:
            pass
    materials["pits"] = pits
    
    # 3. 主引擎代码关键部分（函数清单+行数）
    with open(ENGINE_FILE, 'r', errors='ignore') as f:
        code = f.read()
    import re
    funcs = re.findall(r'def (\w+)\(', code)
    materials["code_structure"] = {
        "total_lines": len(code.split('\n')),
        "total_functions": len(funcs),
        "functions": funcs[:50],  # 前50个函数名
    }
    
    # 4. 已知问题（从代码注释和近期修改提取）
    materials["known_issues"] = [
        "engine_zhuan1.py 2926行，多次修改，接近维护极限",
        "状态分散在多个JSON，state_lock未覆盖全部写操作",
        "C模型超支后硬熔断fuse_until会被save_state竞态覆盖",
        "任务池41模板random.choice随机选，重复率高",
        "goal_tasks跑完就全去随机探索，没有保底主线",
        "认知池3959条但密度量化后大量C级低密认知",
        "飞书通知只有转完成才发，引擎挂了不会告警",
        "空闲模式9任务但只在额度耗尽后才跑",
        "九维严重不均衡：育神1、阳神2、合道0",
        "Supabase同步依赖state_sync.py，未接主循环（已修）",
    ]
    
    return materials

def build_prompt(materials):
    """构造四段式深度评估prompt"""
    prompt = f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」进行长链路深度自评估。
这是一个在云端沙箱中24小时运行的自进化AI引擎，核心目标：修补记忆链路 + 自我迭代进化。

## 一、引擎当前状态
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 二、坑库摘要（已踩过的坑，共{len(materials['pits'])}个）
{json.dumps(materials['pits'], ensure_ascii=False, indent=2)}

## 三、代码结构
{json.dumps(materials['code_structure'], ensure_ascii=False, indent=2)}

## 四、已知问题清单
{chr(10).join(f'{i+1}. {x}' for i,x in enumerate(materials['known_issues']))}

## 五、评估要求（四段式）

请严格按以下四段式输出，每段都要深入、具体、可执行：

### 第一段：问题清单（P0致命/P1严重/P2一般/P3建议）
从代码结构、状态管理、调度逻辑、认知质量、运维稳定性五个维度，全面扫描问题。
每个问题要写：现象、影响范围、严重程度。

### 第二段：根因分析
对P0和P1问题，深入分析根因。不要停留在表面，要挖到设计层面的问题。
重点分析：为什么会出现这个问题？是架构缺陷还是实现bug？有没有系统性的根因？

### 第三段：优化方向
针对每个P0/P1问题，给出具体的优化方案。
要求：可执行、有优先级、考虑工程成本（这个引擎在2核4G沙箱里跑）。
重点关注：
- 代码拆分方案（2926行怎么拆）
- 状态管理方案（多JSON怎么统一）
- 调度逻辑优化（双轨调度怎么完善）
- 认知质量提升（C级认知怎么处理）
- 运维稳定性（怎么保证引擎不挂、挂了能自动恢复）

### 第四段：优先级排序与落地路线图
按P0→P1→P2→P3排序，给出短期（1-3天）、中期（1-2周）、长期（1个月）的落地路线图。
每个阶段要写：做什么、为什么、预期效果。

## 六、特别要求
1. 不要说套话，每个问题都要有具体的代码层面的分析
2. 优先关注P0致命问题，这些是引擎随时可能崩的隐患
3. 考虑这个引擎的特殊环境：2核4G沙箱、24小时运行、网络不稳定、可能被回收
4. 这个引擎的核心价值是"自进化"，评估时要关注自进化链路是否真的在转
5. 输出要长、要深、要具体，不要怕token消耗

现在开始四段式深度评估。"""
    return prompt

def call_model(prompt):
    """调用云端模型"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16000,
        "temperature": 0.3,
    }
    # 空代理设置（引擎里一直这么用，避免代理兼容性问题）
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(
        CHAT_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    print(f"[评估] 调用{MODEL}，prompt约{len(prompt)}字符，等待响应...")
    start = time.time()
    try:
        resp = opener.open(req, timeout=300)
        result = json.loads(resp.read())
        elapsed = time.time() - start
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        print(f"[评估] 完成！耗时{elapsed:.0f}秒，输入{usage.get('prompt_tokens',0)}token，输出{usage.get('completion_tokens',0)}token")
        return content, usage, elapsed
    except Exception as e:
        print(f"[评估] 调用失败: {e}")
        return None, {}, 0

def main():
    print("="*60)
    print("凡心引擎·长链路深度自评估")
    print(f"时间: {datetime.now().isoformat()}")
    print("="*60)
    
    print("\n[1/3] 收集核心材料...")
    materials = collect_materials()
    print(f"  状态: 第{materials['state']['zhuan_count']}转，{materials['state']['total_completed']}任务，{materials['state']['cognition_count']}认知")
    print(f"  坑库: {len(materials['pits'])}个")
    print(f"  代码: {materials['code_structure']['total_lines']}行，{materials['code_structure']['total_functions']}函数")
    
    print("\n[2/3] 构造评估prompt...")
    prompt = build_prompt(materials)
    print(f"  prompt长度: {len(prompt)}字符")
    
    print("\n[3/3] 调用云端模型跑四段式深度评估...")
    content, usage, elapsed = call_model(prompt)
    
    if content:
        OUTPUT_DIR.mkdir(exist_ok=True)
        outfile = OUTPUT_DIR / f"深度自评估报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(outfile, 'w') as f:
            f.write(f"# 凡心引擎·长链路深度自评估报告\n\n")
            f.write(f"**时间**: {datetime.now().isoformat()}\n")
            f.write(f"**模型**: {MODEL}\n")
            f.write(f"**耗时**: {elapsed:.0f}秒\n")
            f.write(f"**Token消耗**: 输入{usage.get('prompt_tokens',0)} + 输出{usage.get('completion_tokens',0)} = {usage.get('total_tokens',0)}\n\n")
            f.write("---\n\n")
            f.write(content)
        print(f"\n✅ 报告已保存: {outfile}")
        print(f"   报告长度: {len(content)}字符")
        return str(outfile)
    else:
        print("\n❌ 评估失败")
        return None

if __name__ == "__main__":
    main()
