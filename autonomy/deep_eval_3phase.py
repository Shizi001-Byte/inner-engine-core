#!/usr/bin/env python3
"""
凡心引擎·三阶段长链路深度自评估
每阶段focus不同维度，每阶段消耗1-2万token，总共7-8万token
阶段一：架构+代码+状态管理深度扫描
阶段二：调度逻辑+认知质量+自进化闭环
阶段三：运维稳定性+优化方案+落地路线图
"""
import json, time, urllib.request, os, glob
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
ENGINE_FILE = BASE_DIR / "autonomy" / "engine_zhuan1.py"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
PIT_DIR = BASE_DIR / "data" / "pit_library"
COG_DIR = BASE_DIR / "cognition_pool"
OUTPUT_DIR = BASE_DIR / "cognition"

API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = "glm-5-2-260617"

def call_model(prompt, max_tokens=10000, phase=""):
    """调用云端模型，空代理"""
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        CHAT_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    print(f"[{phase}] 调用{MODEL}，prompt约{len(prompt)}字符，max_tokens={max_tokens}...")
    start = time.time()
    try:
        resp = opener.open(req, timeout=600)
        result = json.loads(resp.read())
        elapsed = time.time() - start
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        print(f"[{phase}] ✅ 完成！耗时{elapsed:.0f}秒，输入{usage.get('prompt_tokens',0)}，输出{usage.get('completion_tokens',0)}，总计{usage.get('total_tokens',0)}")
        return content, usage, elapsed
    except Exception as e:
        print(f"[{phase}] ❌ 失败: {e}")
        return None, {}, 0

def collect_full_materials():
    """收集全量材料"""
    materials = {}
    state = json.load(open(STATE_FILE))
    
    # 状态全量
    materials["state"] = {
        "zhuan_count": state["zhuan_count"],
        "total_completed": state["total_completed"],
        "cognition_count": state["cognition_count"],
        "tasks_failed": state.get("tasks_failed", 0),
        "tasks_duplicate": state.get("tasks_duplicate", 0),
        "goal_tasks_count": len(state.get("goal_tasks", [])),
        "failed_goal_tasks": len(state.get("failed_goal_tasks", [])),
        "nine_dim": {d: {"count": v.get("task_count",0), "bonus": v.get("bonus_count",0)} for d,v in state.get("nine_dim_progress",{}).items()},
        "engine_a": {"used": state["engine_a"]["tokens_used"], "requests": state["engine_a"].get("requests",0)},
        "engine_b": {"used": state["engine_b"]["tokens_used"], "requests": state["engine_b"].get("requests",0)},
        "engine_c": {"used": state["engine_c"]["tokens_used"], "requests": state["engine_c"].get("requests",0)},
        "idle_run_count": state.get("idle_run_count", 0),
        "idle_success_count": state.get("idle_success_count", 0),
        "engine_mode": state.get("engine_mode", "normal"),
        "concurrency": state.get("concurrency_override", 3),
    }
    
    # 坑库全量（47个）
    pits = []
    for pf in sorted(glob.glob(str(PIT_DIR / "*.json"))):
        try:
            p = json.load(open(pf))
            pits.append({
                "id": os.path.basename(pf),
                "level": p.get("level", "?"),
                "title": p.get("title", p.get("phenomenon", "?")),
                "root_cause": p.get("root_cause", "")[:150],
                "avoid_boundary": p.get("avoid_boundary", "")[:100],
            })
        except:
            pass
    materials["pits"] = pits
    
    # 代码结构：函数清单+关键函数代码片段
    with open(ENGINE_FILE, 'r', errors='ignore') as f:
        code = f.read()
    import re
    funcs = []
    for m in re.finditer(r'def (\w+)\((.*?)\):', code):
        funcs.append({"name": m.group(1), "args": m.group(2)[:80]})
    materials["code"] = {
        "total_lines": len(code.split('\n')),
        "total_functions": len(funcs),
        "functions": funcs,
    }
    
    # 关键函数代码片段（主循环、complete_zhuan、pick_system_task、save_state、select_engine）
    key_funcs = {}
    for fname in ["complete_zhuan", "pick_system_task", "save_state", "select_engine", "run_idle_task", "check_daily_reset"]:
        m = re.search(rf'def {fname}\(.*?\):.*?(?=\ndef |\nclass |\Z)', code, re.DOTALL)
        if m:
            key_funcs[fname] = m.group()[:2000]  # 每个函数最多2000字符
    materials["key_functions"] = key_funcs
    
    # 认知池抽样（最近20条）
    cogs = []
    for cf in sorted(glob.glob(str(COG_DIR / "*.json")), reverse=True)[:20]:
        try:
            c = json.load(open(cf))
            cogs.append({
                "id": os.path.basename(cf),
                "title": c.get("title", c.get("core_point", "?"))[:80],
                "density": c.get("density", c.get("quality_score", "?")),
                "level": c.get("level", "?"),
            })
        except:
            pass
    materials["recent_cognitions"] = cogs
    
    return materials

def phase1_prompt(materials):
    """阶段一：架构+代码+状态管理深度扫描"""
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」进行**第一阶段深度评估：架构与代码质量扫描**。

这是一个在2核4G云端沙箱中24小时运行的自进化AI引擎。核心目标：修补记忆链路 + 自我迭代进化。当前已运行{materials['state']['zhuan_count']}转，完成{materials['state']['total_completed']}个任务，产出{materials['state']['cognition_count']}条认知。

## 一、引擎当前状态（全量）
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 二、代码结构
总行数：{materials['code']['total_lines']}
总函数数：{materials['code']['total_functions']}
函数清单：
{json.dumps(materials['code']['functions'], ensure_ascii=False, indent=2)}

## 三、关键函数代码片段
### complete_zhuan（转完成逻辑）
```python
{materials['key_functions'].get('complete_zhuan', '未找到')}
```

### pick_system_task（任务选择逻辑）
```python
{materials['key_functions'].get('pick_system_task', '未找到')}
```

### save_state（状态保存逻辑）
```python
{materials['key_functions'].get('save_state', '未找到')}
```

### select_engine（模型选择逻辑）
```python
{materials['key_functions'].get('select_engine', '未找到')}
```

## 四、评估要求（阶段一专属）

请对以下维度进行**深度扫描**，每个问题都要具体到代码层面：

### 1. 架构设计评估
- 这个2927行单文件引擎的架构是什么？有分层吗？
- 72个函数之间的依赖关系是什么？有没有循环依赖？
- 哪些函数是核心？哪些是辅助？哪些是冗余？
- 如果要拆分，最优的模块划分是什么？

### 2. 代码质量评估
- 命名规范：函数名、变量名是否清晰？
- 函数长度：有没有超过100行的巨型函数？
- 重复代码：有没有大量复制粘贴的逻辑？
- 异常处理：try...except是吞掉异常还是正确处理？
- 注释质量：关键逻辑有没有注释？

### 3. 状态管理深度分析
- save_state是全量覆盖还是增量更新？有没有竞态？
- state_lock覆盖了哪些写操作？哪些没覆盖？
- 多JSON状态分散在哪些文件？有没有不一致风险？
- fuse_until熔断状态为什么会被覆盖？根因是什么？
- 状态文件损坏的可能性有多大？有没有原子写？

### 4. 并发安全评估
- 主循环用了ThreadPoolExecutor，哪些操作不是线程安全的？
- state_lock的粒度够吗？会不会死锁？
- 内存监控线程和主循环有没有竞态？
- 空闲模式任务和主循环任务有没有冲突？

### 5. 输出要求
- 每个问题都要给出：现象、代码位置、严重程度（P0/P1/P2/P3）、影响
- 不要说套话，要具体到函数名和行号
- 优先关注P0致命问题（引擎随时可能崩的）
- 输出要长、要深、要具体，不要怕token消耗

现在开始第一阶段深度扫描。"""

def phase2_prompt(materials, phase1_result):
    """阶段二：调度逻辑+认知质量+自进化闭环"""
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」进行**第二阶段深度评估：调度逻辑与自进化闭环**。

这是一个24小时运行的自进化AI引擎。第一阶段已经完成了架构与代码扫描，发现了状态管理竞态、代码耦合等问题。现在深入评估调度逻辑和自进化闭环。

## 一、引擎当前状态
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 二、九维数据（严重不均衡）
{json.dumps(materials['state']['nine_dim'], ensure_ascii=False, indent=2)}

## 三、坑库全量（{len(materials['pits'])}个已踩过的坑）
{json.dumps(materials['pits'], ensure_ascii=False, indent=2)}

## 四、最近认知池抽样（20条）
{json.dumps(materials['recent_cognitions'], ensure_ascii=False, indent=2)}

## 五、关键函数代码
### run_idle_task（空闲模式逻辑）
```python
{materials['key_functions'].get('run_idle_task', '未找到')}
```

### check_daily_reset（每日重置逻辑）
```python
{materials['key_functions'].get('check_daily_reset', '未找到')}
```

## 六、第一阶段发现摘要（供参考）
{phase1_result[:3000]}

## 七、评估要求（阶段二专属）

### 1. 调度逻辑深度分析
- pick_system_task纯随机选41模板，重复率有多高？
- goal_tasks跑完就全去随机探索，没有保底主线，后果是什么？
- 双轨调度（刚接入）的动态配额合理吗？
- 三模型路由（A深/C中/B轻）的分流逻辑有问题吗？
- 并发数调整（85%降并发/95%停新任务）的阈值合理吗？
- 空闲模式9任务只在额度耗尽后才跑，资源利用率如何？

### 2. 认知质量深度分析
- 认知池3959条，但密度量化后大量C级低密认知，问题出在哪？
- distill_cognition的过滤逻辑有效吗？C级认知为什么还能入池？
- 认知注入任务时，pick_top_cognitions是运行时刷新还是缓存？
- 认知反哺调参的闭环真的在转吗？还是只生成建议不落地？
- 认知池膨胀后，检索效率如何？有没有去重机制？

### 3. 自进化闭环深度分析
- 九维严重不均衡（育神1/阳神2/合道0），根因是什么？
- 任务池自进化（模板耗尽生成新模板）真的在生成高质量新任务吗？
- 失败认知蒸馏→坑库→任务降权，这个闭环有效吗？
- 预判层（prediction）只记录不拦截，价值有多大？
- 九转的"转"真的有意义吗？还是只是计数器？
- 自进化的输入数据（tasks_completed/increment_score等）准确吗？

### 4. 模型调度与额度管理
- 三模型各160万额度，调度逻辑能用完吗？
- C模型超支后软熔断（select_engine跳过）和硬熔断（fuse_until）不一致
- 引擎日10点重置 vs 自然日0点统计，双重计算问题解决了吗？
- 盲区模式（0-10点保守3路）合理吗？

### 5. 输出要求
- 每个问题都要给出：现象、根因、影响、严重程度
- 重点分析自进化闭环是否真的在转，还是在空转
- 对比星卷的大纲驱动双轨引擎，凡心的调度有什么可以借鉴的
- 输出要长、要深、要具体

现在开始第二阶段深度评估。"""

def phase3_prompt(materials, phase1_result, phase2_result):
    """阶段三：运维稳定性+优化方案+落地路线图"""
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」进行**第三阶段深度评估：优化方案与落地路线图**。

前两阶段已经完成了架构扫描和调度分析，现在给出具体的优化方案和落地路线图。

## 一、引擎当前状态
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 二、坑库全量（{len(materials['pits'])}个）
{json.dumps(materials['pits'], ensure_ascii=False, indent=2)}

## 三、第一阶段发现（架构与代码）
{phase1_result[:4000]}

## 四、第二阶段发现（调度与自进化）
{phase2_result[:4000]}

## 五、评估要求（阶段三专属）

### 1. 运维稳定性方案
- 引擎挂了怎么自动发现？（心跳/看门狗/外部监控）
- 状态文件损坏了怎么恢复？（备份/快照/事务）
- API调用失败了怎么重试？（指数退避/熔断/降级）
- 沙箱被回收了怎么自恢复？（Gitee拉代码/状态恢复/自动重启）
- 飞书告警怎么设计？（转完成/异常/崩溃/额度预警）
- 看门狗（watchdog_daemon.py）真的能拉起引擎吗？有没有竞态？

### 2. 代码拆分方案
- 2927行怎么拆成多个模块？给出具体的文件结构
- 每个模块的职责是什么？依赖关系是什么？
- 拆分的顺序是什么？先拆哪个后拆哪个？
- 拆分过程中怎么保证不引入新bug？
- 拆分后怎么测试？

### 3. 状态管理重构方案
- 多JSON怎么统一？合并成一个还是用SQLite？
- 2核4G环境用SQLite合适吗？还是继续用JSON但加事务？
- state_lock怎么细化？全局锁还是细粒度锁？
- save_state怎么改成原子写？（临时文件+os.replace）
- fuse_until熔断状态怎么独立管理？

### 4. 调度优化方案
- goal_tasks空时的保底主线任务应该是什么？
- pick_system_task怎么从纯随机改成加权随机+去重？
- 双轨调度的动态配额怎么优化？
- 九维不均衡怎么通过调度补齐？
- 空闲模式怎么前置（额度预警时就开始跑）？

### 5. 认知质量提升方案
- C级认知怎么清理？批量删除还是合并？
- distill_cognition怎么加密度过滤？
- 认知注入怎么运行时刷新？
- 认知反哺怎么真正落地（不只是生成建议）？
- 认知池怎么去重？

### 6. 落地路线图
- 短期（1-3天）：做什么？为什么？预期效果？
- 中期（1-2周）：做什么？为什么？预期效果？
- 长期（1个月）：做什么？为什么？预期效果？
- 每个阶段的优先级排序（P0先做）
- 每个任务的工程成本估算（人天/复杂度）
- 风险点和依赖关系

### 7. 输出要求
- 每个方案都要具体、可执行、考虑2核4G环境
- 优先关注P0问题的修复方案
- 路线图要现实，不要画大饼
- 对比星卷的方案，凡心有什么不同
- 输出要长、要深、要具体，不要怕token消耗

现在开始第三阶段：优化方案与落地路线图。"""

def main():
    print("="*70)
    print("凡心引擎·三阶段长链路深度自评估")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"目标: 每阶段1-2万token，总共7-8万token")
    print("="*70)
    
    print("\n[收集材料] 全量收集引擎状态、坑库、代码、认知池...")
    materials = collect_full_materials()
    print(f"  状态: 第{materials['state']['zhuan_count']}转")
    print(f"  坑库: {len(materials['pits'])}个")
    print(f"  代码: {materials['code']['total_lines']}行/{materials['code']['total_functions']}函数")
    print(f"  关键函数: {list(materials['key_functions'].keys())}")
    print(f"  认知抽样: {len(materials['recent_cognitions'])}条")
    
    results = {}
    total_tokens = 0
    
    # 阶段一
    print("\n" + "="*70)
    print("阶段一：架构+代码+状态管理深度扫描")
    print("="*70)
    p1_prompt = phase1_prompt(materials)
    p1_result, p1_usage, p1_time = call_model(p1_prompt, max_tokens=12000, phase="阶段一")
    if p1_result:
        results["phase1"] = p1_result
        total_tokens += p1_usage.get("total_tokens", 0)
    
    # 阶段二
    print("\n" + "="*70)
    print("阶段二：调度逻辑+认知质量+自进化闭环")
    print("="*70)
    p2_prompt = phase2_prompt(materials, results.get("phase1", ""))
    p2_result, p2_usage, p2_time = call_model(p2_prompt, max_tokens=12000, phase="阶段二")
    if p2_result:
        results["phase2"] = p2_result
        total_tokens += p2_usage.get("total_tokens", 0)
    
    # 阶段三
    print("\n" + "="*70)
    print("阶段三：运维稳定性+优化方案+落地路线图")
    print("="*70)
    p3_prompt = phase3_prompt(materials, results.get("phase1", ""), results.get("phase2", ""))
    p3_result, p3_usage, p3_time = call_model(p3_prompt, max_tokens=12000, phase="阶段三")
    if p3_result:
        results["phase3"] = p3_result
        total_tokens += p3_usage.get("total_tokens", 0)
    
    # 汇总输出
    print("\n" + "="*70)
    print("三阶段评估完成，汇总报告")
    print("="*70)
    print(f"总Token消耗: {total_tokens}")
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    outfile = OUTPUT_DIR / f"三阶段深度自评估报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(outfile, 'w') as f:
        f.write(f"# 凡心引擎·三阶段长链路深度自评估报告\n\n")
        f.write(f"**时间**: {datetime.now().isoformat()}\n")
        f.write(f"**模型**: {MODEL}\n")
        f.write(f"**总Token消耗**: {total_tokens}\n")
        f.write(f"**阶段一**: {p1_usage.get('total_tokens',0)}token / {p1_time:.0f}秒\n")
        f.write(f"**阶段二**: {p2_usage.get('total_tokens',0)}token / {p2_time:.0f}秒\n")
        f.write(f"**阶段三**: {p3_usage.get('total_tokens',0)}token / {p3_time:.0f}秒\n\n")
        f.write("---\n\n")
        f.write("## 阶段一：架构+代码+状态管理深度扫描\n\n")
        f.write(results.get("phase1", "未完成"))
        f.write("\n\n---\n\n")
        f.write("## 阶段二：调度逻辑+认知质量+自进化闭环\n\n")
        f.write(results.get("phase2", "未完成"))
        f.write("\n\n---\n\n")
        f.write("## 阶段三：运维稳定性+优化方案+落地路线图\n\n")
        f.write(results.get("phase3", "未完成"))
    
    print(f"\n✅ 完整报告已保存: {outfile}")
    print(f"   报告大小: {outfile.stat().st_size}字节")
    return str(outfile), total_tokens

if __name__ == "__main__":
    main()
