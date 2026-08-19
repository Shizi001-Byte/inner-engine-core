#!/usr/bin/env python3
"""
凡心引擎·五阶段深度复审（整改后）
目标：总消耗8-10万token
阶段一：P0修复验证（3个P0问题的修复代码深度审查）
阶段二：P1修复验证（6个P1问题的修复代码深度审查）
阶段三：P2修复验证（6个P2问题的修复代码深度审查）
阶段四：整体架构评估（整改后的整体架构、并发安全、状态管理）
阶段五：剩余问题与演进路线图
"""
import json, time, urllib.request, os, glob
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
ENGINE_FILE = BASE_DIR / "autonomy" / "engine_zhuan1.py"
STATE_FILE = BASE_DIR / "data" / "engine_state.json"
PIT_DIR = BASE_DIR / "data" / "pit_library"
COGNITION_POOL = BASE_DIR / "cognition_pool"
OUTPUT_DIR = BASE_DIR / "cognition"

API_KEY = "ark-6c0c1704-78c4-42a0-be0d-0011fab46ca6-2688e"
CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = "glm-5-2-260617"

def call_model(prompt, max_tokens=18000, phase=""):
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
    for retry in range(3):
        try:
            resp = opener.open(req, timeout=900)
            result = json.loads(resp.read())
            elapsed = time.time() - start
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            print(f"[{phase}] ✅ 完成！耗时{elapsed:.0f}秒，输入{usage.get('prompt_tokens',0)}，输出{usage.get('completion_tokens',0)}，总计{usage.get('total_tokens',0)}")
            return content, usage, elapsed
        except Exception as e:
            print(f"[{phase}] ⚠️ 第{retry+1}次尝试失败: {e}")
            if retry < 2:
                print(f"[{phase}] 30秒后重试...")
                time.sleep(30)
    print(f"[{phase}] ❌ 3次重试全部失败")
    return None, {}, 0

def collect_materials():
    materials = {}
    state = json.load(open(STATE_FILE))
    
    # 状态全量
    materials["state"] = {
        "zhuan_count": state["zhuan_count"],
        "total_completed": state["total_completed"],
        "cognition_count": state["cognition_count"],
        "tasks_failed": state.get("tasks_failed", 0),
        "engine_health_score": state.get("engine_health_score", "未计算"),
        "health_history_count": len(state.get("health_history", [])),
        "uptime_history_count": len(state.get("uptime_history", [])),
        "nine_dim": {d: {"count": v.get("task_count",0), "bonus": v.get("bonus_count",0)} for d,v in state.get("nine_dim_progress",{}).items()},
        "engine_a": {"used": state["engine_a"]["tokens_used"], "requests": state["engine_a"].get("requests",0)},
        "engine_b": {"used": state["engine_b"]["tokens_used"], "requests": state["engine_b"].get("requests",0)},
        "engine_c": {"used": state["engine_c"]["tokens_used"], "requests": state["engine_c"].get("requests",0)},
        "goal_tasks": len(state.get("goal_tasks", [])),
        "idle_run_count": state.get("idle_run_count", 0),
        "engine_mode": state.get("engine_mode", "normal"),
    }
    
    # 坑库全量
    pits = []
    for pf in sorted(glob.glob(str(PIT_DIR / "*.json"))):
        try:
            p = json.load(open(pf))
            pits.append({
                "id": os.path.basename(pf),
                "level": p.get("level", "?"),
                "title": p.get("title", p.get("phenomenon", "?"))[:100],
                "root_cause": p.get("root_cause", "")[:100],
            })
        except:
            pass
    materials["pits"] = pits
    
    # 代码：读取关键函数的完整代码
    with open(ENGINE_FILE, 'r', errors='ignore') as f:
        code = f.read()
    import re
    key_funcs = {}
    for fname in ["pick_system_task", "select_engine", "save_state", "check_duplicate", 
                  "complete_zhuan", "load_top_cognitions", "distill_cognition",
                  "run_idle_task", "_pick_next_idle_task", "memory_monitor_loop",
                  "check_daily_reset", "execute_single_api", "cultivation_pipeline"]:
        m = re.search(rf'def {fname}\(.*?\):.*?(?=\ndef |\nclass |\Z)', code, re.DOTALL)
        if m:
            key_funcs[fname] = m.group()[:3000]  # 每个函数最多3000字符
    materials["key_functions"] = key_funcs
    materials["code_total_lines"] = len(code.split('\n'))
    
    # 已修复问题清单
    materials["fixed_issues"] = {
        "P0": [
            "pick_system_task无锁操作state → 加state_lock，权重计算和任务选择全程在锁内",
            "fuse_until熔断状态丢失 → 修改时加state_lock并立即save_state",
            "check_duplicate并发穿透 → 读取判断写入全程原子化在state_lock内",
        ],
        "P1": [
            "goal_tasks空时无保底主线 → 自动生成系统自检/认知清理/任务池审计保底任务",
            "任务池纯随机重复率高 → 短期去重，排除最近3次已选模板",
            "唤醒包失败只记日志不降级 → 设置降级标志+连续失败3次告警",
            "引擎崩溃无告警 → 外层通用异常捕获+飞书崩溃告警",
            "九维不均衡 → 偏弱维度权重x2，促进均衡发展",
            "C级认知污染注入上下文 → load_top_cognitions优先S/A/B级，跳过C级",
        ],
        "P2": [
            "select_engine重复代码 → 字典+循环代替a/b/c复制粘贴",
            "无运行时长统计 → 启动时间记录+uptime_history保留最近50次",
            "无健康度监控 → 综合额度/成功率/认知质量/九维均衡的0-100健康度评分",
            "飞书通知信息不足 → 加入健康度评分+颜色图标(🟢🟡🔴)",
            "认知无定期去重 → 每转完成检查最近50条，标记重复不删除",
            "C级认知堆积 → 超过24小时的C级文件移到archive_c_level目录，不删除",
        ],
    }
    
    return materials

def phase1_prompt(materials):
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」整改后的代码进行**第一阶段深度复审：P0修复验证**。

这是一个在2核4G云端沙箱中24小时运行的自进化AI引擎。之前的评估发现了3个P0致命问题，现在已经修复。你需要深度审查修复代码，验证修复是否真正解决了问题，有没有引入新的bug。

## 一、当前引擎状态
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 二、P0问题及修复方案
{json.dumps(materials['fixed_issues']['P0'], ensure_ascii=False, indent=2)}

## 三、关键函数代码（修复后的）

### pick_system_task（P0-1修复对象）
```python
{materials['key_functions'].get('pick_system_task', '未找到')}
```

### select_engine（P0-2修复对象）
```python
{materials['key_functions'].get('select_engine', '未找到')}
```

### check_duplicate（P0-3修复对象）
```python
{materials['key_functions'].get('check_duplicate', '未找到')}
```

### save_state（状态保存，与P0-2相关）
```python
{materials['key_functions'].get('save_state', '未找到')}
```

## 四、复审要求

对每个P0问题，深度审查以下维度：

### P0-1：pick_system_task加锁
1. state_lock是否覆盖了所有读写state的操作？有没有遗漏？
2. generate_new_tasks在锁外调用，会不会导致状态不一致？
3. 锁的粒度会不会太大导致性能问题？
4. 有没有死锁风险？（state_lock嵌套？）
5. 修复后有没有引入新的bug？

### P0-2：fuse_until熔断状态丢失
1. 修改fuse_until时是否真的在state_lock内？
2. 修改后是否立即调用了save_state？save_state会不会被其他线程覆盖？
3. 熔断状态读取时（select_engine）是否也在锁内？
4. 有没有熔断状态泄漏的情况？（比如API成功后没有重置fuse_until）
5. 修复后熔断机制是否真的能生效？

### P0-3：check_duplicate并发穿透
1. 读取recent_titles、判断重复、写入是否全程在锁内？
2. 锁的粒度是否合理？会不会影响并发性能？
3. 有没有其他地方也在修改recent_titles但没加锁？
4. 重复判断逻辑是否准确？（title[:15]比较会不会误判？）
5. 修复后并发场景下是否真的不会穿透？

### 综合评估
1. 三个P0修复是否都真正解决了问题？
2. 修复代码的质量如何？有没有技术债？
3. 有没有遗漏的并发安全问题？（其他函数有没有类似的无锁操作？）
4. 给出每个P0的修复评分（0-100）和具体改进建议
5. 如果发现修复有问题，给出具体的修复方案

输出要长、要深、要具体，每个问题都要给出代码层面的分析。不要说套话。"""

def phase2_prompt(materials, phase1_result):
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」整改后的代码进行**第二阶段深度复审：P1修复验证**。

之前的评估发现了6个P1严重问题，现在已经修复。你需要深度审查修复代码。

## 一、P1问题及修复方案
{json.dumps(materials['fixed_issues']['P1'], ensure_ascii=False, indent=2)}

## 二、关键函数代码

### complete_zhuan（转完成逻辑，多个P1修复都在这里）
```python
{materials['key_functions'].get('complete_zhuan', '未找到')}
```

### load_top_cognitions（P1-6修复对象）
```python
{materials['key_functions'].get('load_top_cognitions', '未找到')}
```

### distill_cognition（P1-6相关，认知蒸馏）
```python
{materials['key_functions'].get('distill_cognition', '未找到')}
```

### _pick_next_idle_task（空闲模式调度）
```python
{materials['key_functions'].get('_pick_next_idle_task', '未找到')}
```

## 三、第一阶段复审结论（供参考）
{phase1_result[:2000]}

## 四、复审要求

对每个P1问题，深度审查：

### P1-1：goal_tasks空时保底主线
1. 保底任务生成逻辑是否合理？会不会生成低质量任务？
2. 保底任务的优先级排序是否正确？（P0>P1>P2）
3. 保底任务和正常goal_tasks会不会冲突？
4. 10分钟冷却时间是否合理？
5. 保底任务执行失败后会不会重试？

### P1-2：任务池短期去重
1. 排除最近3次已选模板的逻辑是否正确？
2. recent_template_ids记录是否准确？有没有遗漏？
3. 如果所有模板都在最近3次内，会不会导致无任务可选？
4. 去重会不会导致某些模板永远选不到？
5. 3次的窗口大小是否合理？

### P1-3：唤醒包失败降级
1. 降级标志wake_packet_ok是否正确设置？
2. 连续失败计数会不会溢出？
3. 失败3次告警后，后续成功会不会重置计数？
4. 唤醒包失败对引擎运行有什么实际影响？
5. 有没有其他地方依赖唤醒包但没检查降级标志？

### P1-4：引擎崩溃告警
1. 外层try...except是否能捕获所有异常？
2. 飞书告警发送失败会不会导致二次崩溃？
3. 告警信息是否足够定位问题？
4. KeyboardInterrupt会不会被误判为崩溃？
5. 崩溃后状态是否正确保存？

### P1-5：九维偏弱维度加权
1. 偏弱维度判断逻辑是否准确？（最少维度不到最多的30%）
2. 权重x2会不会导致过度补偿？
3. 只有5个维度有任务类型映射，其他4个维度怎么补？
4. 加权后九维会不会从一个极端走向另一个极端？
5. 这个机制和任务池自进化会不会冲突？

### P1-6：C级认知过滤
1. load_top_cognitions是否真的跳过了C级？
2. S/A/B级不够时用无级补充，会不会导致低质认知注入？
3. 缓存_cached_cognitions什么时候刷新？会不会用旧数据？
4. distill_cognition里的C级过滤是否和load_top_cognitions一致？
5. 历史C级认知怎么处理？（归档还是保留？）

### 综合评估
1. 六个P1修复是否都真正解决了问题？
2. 修复代码质量评分（每个0-100）
3. 有没有引入新的问题？
4. 给出具体改进建议

输出要长、要深、要具体。"""

def phase3_prompt(materials, phase1_result, phase2_result):
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」整改后的代码进行**第三阶段深度复审：P2修复验证**。

之前的评估发现了多个P2一般问题，现在已经修复了6个。你需要深度审查。

## 一、P2问题及修复方案
{json.dumps(materials['fixed_issues']['P2'], ensure_ascii=False, indent=2)}

## 二、关键函数代码

### complete_zhuan（P2-3/4/5/6都在这里）
```python
{materials['key_functions'].get('complete_zhuan', '未找到')}
```

### select_engine（P2-1修复对象）
```python
{materials['key_functions'].get('select_engine', '未找到')}
```

### memory_monitor_loop（内存监控）
```python
{materials['key_functions'].get('memory_monitor_loop', '未找到')}
```

## 三、前两阶段复审结论（供参考）
阶段一：{phase1_result[:1000]}
阶段二：{phase2_result[:1000]}

## 四、复审要求

### P2-1：select_engine重复代码重构
1. 字典+循环代替a/b/c复制粘贴，逻辑是否完全等价？
2. 重构后有没有边界情况遗漏？（比如engine_c不存在的情况）
3. 代码可读性是提升了还是下降了？
4. 重构后性能有没有影响？
5. 还有没有其他地方有类似的重复代码可以重构？

### P2-2：运行时长统计
1. 启动时间记录是否准确？
2. uptime_history保留最近50次，会不会丢失重要历史？
3. 运行时长统计有什么实际用途？（分析沙箱回收规律？）
4. 异常退出时运行时长会不会记录错误？
5. 这个统计和沙箱心跳机制有没有重叠？

### P2-3：健康度评分
1. 四个维度（额度/成功率/认知质量/九维均衡）的权重分配是否合理？
2. 额度健康度计算是否准确？（超支扣30分会不会太严厉？）
3. 认知质量用S/A级占比，数据来源是否准确？（cognition_grade_stats有没有正确维护？）
4. 九维均衡度用标准差计算，会不会因为某个维度为0导致失真？
5. 健康度评分有什么实际用途？（飞书展示？自动调参？告警？）
6. 健康度历史保留100次，够不够分析趋势？

### P2-4：飞书通知健康度图标
1. 🟢(≥70)/🟡(40-69)/🔴(<40)的阈值是否合理？
2. 飞书消息里加入健康度后，信息会不会太多？
3. 飞书通知的发送频率是每转一次，会不会太频繁？
4. 有没有必要增加异常时的即时告警（不等转完成）？
5. 飞书webhook调用失败会不会影响主流程？

### P2-5：认知去重
1. 每转完成检查最近50条，范围是否合理？
2. 用text[:50]的md5做哈希，会不会误判？（前50字相同但内容不同）
3. 标记重复但不删除，后续怎么处理这些重复认知？
4. 去重会不会影响认知密度统计？
5. 50条的范围会不会漏掉更早的重复？

### P2-6：C级认知归档
1. 只归档超过24小时的C级文件，时间窗口是否合理？
2. 整个文件所有认知都是C级才归档，会不会漏掉混合文件里的C级？
3. 移到archive_c_level目录后，还能不能检索到？
4. 每转最多归档20个，会不会积压？
5. 归档后认知总数cognition_count会不会减少？（应该不会，因为只是移动文件）
6. 归档目录有没有大小限制？会不会无限增长？

### 综合评估
1. 六个P2修复是否都真正解决了问题？
2. 修复代码质量评分（每个0-100）
3. 有没有引入新的问题？
4. 给出具体改进建议

输出要长、要深、要具体。"""

def phase4_prompt(materials, p1, p2, p3):
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」整改后的整体架构进行**第四阶段深度评估：整体架构与并发安全**。

经过P0/P1/P2共15个问题的修复，引擎代码已经有了很大变化。你需要从整体架构层面评估整改效果。

## 一、引擎基本信息
- 代码总行数：{materials['code_total_lines']}
- 当前转数：{materials['state']['zhuan_count']}
- 总完成任务：{materials['state']['total_completed']}
- 认知数：{materials['state']['cognition_count']}
- 健康度：{materials['state']['engine_health_score']}
- 坑库：{len(materials['pits'])}个

## 二、当前状态全量
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 三、关键函数代码

### 主循环相关（execute_single_api + cultivation_pipeline）
```python
{materials['key_functions'].get('execute_single_api', '未找到')}
```
```python
{materials['key_functions'].get('cultivation_pipeline', '未找到')}
```

### 状态管理（save_state + check_daily_reset）
```python
{materials['key_functions'].get('save_state', '未找到')}
```
```python
{materials['key_functions'].get('check_daily_reset', '未找到')}
```

### 空闲模式（run_idle_task）
```python
{materials['key_functions'].get('run_idle_task', '未找到')}
```

## 四、前三阶段复审结论（供参考）
P0复审：{p1[:800]}
P1复审：{p2[:800]}
P2复审：{p3[:800]}

## 五、评估要求

### 1. 整体架构评估
- 整改后的架构是否比之前更健康？
- 还有没有"大泥球"问题？（2900+行单文件）
- 模块划分是否清晰？有没有职责不清的函数？
- 代码可维护性评分（0-100）
- 给出架构改进的优先级建议

### 2. 并发安全全面审计
- 除了已修复的3个P0，还有没有其他并发安全问题？
- 逐个审查关键函数：哪些操作了state但没加锁？
- state_lock的使用是否一致？有没有遗漏的写操作？
- 内存监控线程和主循环的竞态是否完全解决？
- 空闲模式任务和主循环任务有没有冲突？
- 给出并发安全评分（0-100）和剩余风险清单

### 3. 状态管理评估
- 多JSON状态分散问题有没有改善？
- save_state的原子写是否可靠？
- 状态恢复机制是否完善？（沙箱回收后能不能正确恢复？）
- 状态字段有没有冗余或不一致？
- 给出状态管理评分（0-100）

### 4. 自进化闭环评估
- 引擎的"自进化"是否真的在转？还是只是计数器？
- 认知蒸馏→反哺调参→任务优化的闭环是否通畅？
- 九维修炼是否真的在均衡发展？
- 任务池自进化是否真的在产生高质量新任务？
- 失败认知蒸馏→坑库→任务降权的闭环是否有效？
- 给出自进化有效性评分（0-100）

### 5. 运维稳定性评估
- 引擎24小时运行的稳定性如何？
- 崩溃告警+看门狗+自动重启的链路是否完整？
- 沙箱回收后的自恢复能力如何？
- 三方备份（Gitee/飞书/Supabase）是否真的在工作？
- 给出运维稳定性评分（0-100）

### 6. 整改效果总评
- 15个问题修复后，引擎整体提升了多少？
- 哪些修复效果最明显？哪些还有改进空间？
- 整改有没有引入新的技术债？
- 给出整改效果总评分（0-100）
- 列出整改后仍然存在的Top 10问题

输出要长、要深、要具体，每个评估都要有数据支撑和具体分析。"""

def phase5_prompt(materials, p1, p2, p3, p4):
    return f"""你是一位资深AI引擎架构师，正在对「凡心九转引擎」进行**第五阶段深度评估：剩余问题与演进路线图**。

经过P0/P1/P2共15个问题的修复，以及整体架构评估，现在需要梳理剩余问题，给出未来演进路线图。

## 一、引擎当前状态
{json.dumps(materials['state'], ensure_ascii=False, indent=2)}

## 二、坑库全量（{len(materials['pits'])}个已踩过的坑）
{json.dumps(materials['pits'][:30], ensure_ascii=False, indent=2)}

## 三、前四阶段评估结论（供参考）
P0复审：{p1[:600]}
P1复审：{p2[:600]}
P2复审：{p3[:600]}
整体架构：{p4[:600]}

## 四、评估要求

### 1. 剩余问题全面梳理
从以下维度梳理整改后仍然存在的问题，按P0/P1/P2/P3分级：
- 架构层面：代码拆分、模块划分、技术债
- 并发安全：剩余的竞态、死锁风险
- 状态管理：多JSON分散、恢复机制、一致性
- 自进化：闭环有效性、认知质量、任务多样性
- 运维稳定：备份可靠性、告警完整性、自恢复能力
- 性能优化：内存占用、API调用效率、并发度
- 功能缺失：规划中但未实现的功能

每个问题要写：现象、根因、影响、严重程度、修复难度。

### 2. 短期演进路线图（1-2周）
- 优先修复哪些问题？为什么？
- 每个问题的修复方案、预估工作量、预期效果
- 短期目标是什么？（健康度达到多少？稳定性提升多少？）
- 有没有 quick win（投入小收益大的改进）？

### 3. 中期演进路线图（1-2个月）
- 架构层面的重大改进（代码拆分？模块重构？）
- 自进化能力的深度提升
- 运维体系的完善
- 中期目标是什么？
- 关键里程碑有哪些？

### 4. 长期演进路线图（3-6个月）
- 引擎的终极形态是什么？
- 从"能跑"到"跑得好"到"自我进化"的路径
- 技术选型的重大变化（SQLite？微服务？）
- 长期目标和愿景

### 5. 风险与挑战
- 演进过程中最大的风险是什么？
- 哪些问题可能越修越复杂？
- 有没有需要避免的陷阱？
- 资源约束（2核4G沙箱、API额度、人力）对演进的影响

### 6. 给凡心的建议
- 作为AI引擎架构师，你给凡心的最重要的3条建议是什么？
- 哪些事情应该立刻做？哪些可以缓一缓？
- 有没有"不做比做更好"的事情？
- 怎么平衡"快速迭代"和"技术债积累"？

输出要长、要深、要具体，路线图要有可执行性，不要画大饼。"""

def main():
    print("="*70)
    print("凡心引擎·五阶段深度复审（整改后）")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"目标: 总消耗8-10万token")
    print("="*70)
    
    print("\n[收集材料]...")
    materials = collect_materials()
    print(f"  状态: 第{materials['state']['zhuan_count']}转")
    print(f"  坑库: {len(materials['pits'])}个")
    print(f"  关键函数: {list(materials['key_functions'].keys())}")
    print(f"  代码: {materials['code_total_lines']}行")
    
    results = {}
    total_tokens = 0
    
    phases = [
        ("阶段一：P0修复验证", phase1_prompt, 16000),
        ("阶段二：P1修复验证", phase2_prompt, 15000),
        ("阶段三：P2修复验证", phase3_prompt, 15000),
        ("阶段四：整体架构评估", phase4_prompt, 20000),
        ("阶段五：剩余问题与路线图", phase5_prompt, 20000),
    ]
    
    for i, (name, prompt_func, max_tok) in enumerate(phases):
        print("\n" + "="*70)
        print(f"{name} (max_tokens={max_tok})")
        print("="*70)
        
        if i == 0:
            prompt = prompt_func(materials)
        elif i == 1:
            prompt = prompt_func(materials, results.get("phase1", ""))
        elif i == 2:
            prompt = prompt_func(materials, results.get("phase1", ""), results.get("phase2", ""))
        elif i == 3:
            prompt = prompt_func(materials, results.get("phase1", ""), results.get("phase2", ""), results.get("phase3", ""))
        else:
            prompt = prompt_func(materials, results.get("phase1", ""), results.get("phase2", ""), results.get("phase3", ""), results.get("phase4", ""))
        
        content, usage, elapsed = call_model(prompt, max_tokens=max_tok, phase=name)
        if content:
            results[f"phase{i+1}"] = content
            total_tokens += usage.get("total_tokens", 0)
    
    # 汇总输出
    print("\n" + "="*70)
    print(f"五阶段复审完成！总消耗: {total_tokens} token")
    print("="*70)
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    outfile = OUTPUT_DIR / f"五阶段深度复审报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(outfile, 'w') as f:
        f.write(f"# 凡心引擎·五阶段深度复审报告（整改后）\n\n")
        f.write(f"**时间**: {datetime.now().isoformat()}\n")
        f.write(f"**模型**: {MODEL}\n")
        f.write(f"**总Token消耗**: {total_tokens}\n\n")
        f.write("---\n\n")
        for i, (name, _, _) in enumerate(phases):
            f.write(f"## {name}\n\n")
            f.write(results.get(f"phase{i+1}", "未完成"))
            f.write("\n\n---\n\n")
    
    print(f"\n✅ 完整报告已保存: {outfile}")
    print(f"   报告大小: {outfile.stat().st_size}字节")
    return str(outfile), total_tokens

if __name__ == "__main__":
    main()
