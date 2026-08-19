#!/usr/bin/env python3
"""空闲模式V4.0·阴阳节律生命体升级脚本
21字真言落地：反者道之动(平滑节律) + 弱者道之用(深度休眠) + 有生于无(成长值反哺)
"""
import re
from pathlib import Path

ENGINE_FILE = Path("/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/autonomy/engine_zhuan1.py")
content = ENGINE_FILE.read_text(encoding="utf-8")

# ============================================================
# 改造1：light冷却 5分钟→30分钟（弱者道之用：无新输入时低频）
# ============================================================
old_cooldown = '''    if schedule_level == "light":
        if now - last_run < 300:  # P3优化：light级5分钟冷却，避免无新数据时空转
            remaining = int(300 - (now - last_run))
            return False, f"轻巡检冷却中(剩{remaining}秒)"
        return True, "轻巡检可执行"'''

new_cooldown = '''    if schedule_level == "light":
        if now - last_run < 1800:  # V4.0：light级30分钟冷却，无新输入时深度低频，弱者道之用
            remaining = int(1800 - (now - last_run))
            return False, f"轻巡检冷却中(剩{remaining}秒)"
        return True, "轻巡检可执行"'''

if old_cooldown in content:
    content = content.replace(old_cooldown, new_cooldown)
    print("✅ 改造1完成：light冷却5分钟→30分钟")
else:
    print("❌ 改造1失败")

# ============================================================
# 改造2：阴期次第调度——重活先干，干完休眠（反者道之动：初阴重、中阴轻、深阴眠）
# ============================================================
old_pick = '''def _pick_next_idle_task(state):
    """P2-1：分级调度 - 跳过冷却中的任务，选下一个可执行的"""
    idle_idx = state.get("idle_task_index", 0)
    total = len(IDLE_TASK_ORDER)
    for offset in range(total):
        task_name = IDLE_TASK_ORDER[(idle_idx + offset) % total]
        task_func, mem_level, sched_level, task_desc = IDLE_TASK_REGISTRY[task_name]
        # 检查调度冷却
        can_sched, sched_reason = _check_schedule_cooldown(task_name, sched_level, state)
        if not can_sched:
            continue
        # 检查内存预算
        can_mem, mem_reason = _check_memory_budget(mem_level)
        if not can_mem:
            continue
        # 找到可执行的任务
        state["idle_task_index"] = (idle_idx + offset + 1) % total
        return task_name, task_func, mem_level, sched_level, task_desc
    # 所有任务都在冷却或内存不够，返回None
    return None, None, None, None, None'''

new_pick = '''def _pick_next_idle_task(state):
    """V4.0：阴期次第调度——初阴重活先干，中阴轻活后干，深阴休眠
    反者道之动：阴期不是均匀轮询，是按精力递减次第而行"""
    # V4.0：阴期次第优先级——重活(密度/去重/蒸馏) > 轻活(盘点/备份/总结) > 巡检(预判/坑库)
    idle_phase = state.get("idle_phase", "early")  # early=初阴(重活), mid=中阴(轻活), deep=深阴(休眠)
    priority_order = {
        "early": ["cognition_density", "content_dedup", "failure_distill", "integrity_check",
                  "asset_inventory", "auto_backup", "daily_summary",
                  "prediction_audit", "pit_library_expand"],
        "mid":   ["asset_inventory", "auto_backup", "daily_summary", "failure_distill",
                  "prediction_audit", "pit_library_expand", "cognition_density", "content_dedup"],
        "deep":  ["prediction_audit", "failure_distill", "pit_library_expand"]  # 深阴只跑最轻的巡检
    }
    order = priority_order.get(idle_phase, IDLE_TASK_ORDER)
    # 过滤掉注册表中不存在的任务
    order = [t for t in order if t in IDLE_TASK_REGISTRY]
    for task_name in order:
        task_func, mem_level, sched_level, task_desc = IDLE_TASK_REGISTRY[task_name]
        can_sched, sched_reason = _check_schedule_cooldown(task_name, sched_level, state)
        if not can_sched:
            continue
        can_mem, mem_reason = _check_memory_budget(mem_level)
        if not can_mem:
            continue
        return task_name, task_func, mem_level, sched_level, task_desc
    # V4.0：所有任务都跑完了，判断是否进入深阴休眠
    daily_tasks = ["cognition_density", "content_dedup", "asset_inventory", "auto_backup", "daily_summary", "integrity_check"]
    all_daily_done = all(
        state.get("idle_task_last_run", {}).get(t, 0) > 0
        for t in daily_tasks if t in IDLE_TASK_REGISTRY
    )
    if all_daily_done:
        state["idle_phase"] = "deep"
        state["idle_deep_sleep_start"] = time.time()
    return None, None, None, None, None'''

if old_pick in content:
    content = content.replace(old_pick, new_pick)
    print("✅ 改造2完成：阴期次第调度（初阴重/中阴轻/深阴眠）")
else:
    print("❌ 改造2失败")

# ============================================================
# 改造3：深度休眠态——所有daily跑完后，30分钟心跳一次（弱者道之用）
# ============================================================
old_sleep = '''    if task_name is None:
        # P3优化：计算最近一个任务的剩余冷却时间，睡到那个时间而不是每30秒醒一次
        now = time.time()
        min_remaining = 300  # 默认5分钟
        for tname in IDLE_TASK_ORDER:
            _, _, slevel, _ = IDLE_TASK_REGISTRY[tname]
            last_run = state.get("idle_task_last_run", {}).get(tname, 0)
            cooldown = {"light": 300, "daily": 86400, "weekly": 604800}.get(slevel, 300)
            remaining = cooldown - (now - last_run)
            if remaining > 0 and remaining < min_remaining:
                min_remaining = remaining
        sleep_time = min(min_remaining, 300)  # 最多睡5分钟
        log(f"[IDLE] 所有任务冷却中，休息{int(sleep_time)}秒(最近任务剩{int(min_remaining)}秒)")
        time.sleep(sleep_time)
        return True'''

new_sleep = '''    if task_name is None:
        # V4.0：深度休眠态——所有daily跑完后，30分钟心跳一次，弱者道之用
        now = time.time()
        idle_phase = state.get("idle_phase", "early")
        if idle_phase == "deep":
            # 深阴：30分钟心跳，只检查额度是否刷新
            sleep_time = 1800
            sleep_start = state.get("idle_deep_sleep_start", now)
            sleep_cycles = int((now - sleep_start) / 1800) + 1
            log(f"[IDLE] 🌙 深阴休眠态，30分钟心跳(第{sleep_cycles}次)，最低功耗待机")
            time.sleep(sleep_time)
            return True
        # 非深阴：计算最近任务剩余冷却时间
        min_remaining = 1800
        for tname in IDLE_TASK_ORDER:
            _, _, slevel, _ = IDLE_TASK_REGISTRY[tname]
            last_run = state.get("idle_task_last_run", {}).get(tname, 0)
            cooldown = {"light": 1800, "daily": 86400, "weekly": 604800}.get(slevel, 1800)
            remaining = cooldown - (now - last_run)
            if remaining > 0 and remaining < min_remaining:
                min_remaining = remaining
        sleep_time = min(min_remaining, 1800)
        log(f"[IDLE] 所有任务冷却中，休息{int(sleep_time)}秒(最近任务剩{int(min_remaining)}秒)")
        time.sleep(sleep_time)
        return True'''

if old_sleep in content:
    content = content.replace(old_sleep, new_sleep)
    print("✅ 改造3完成：深度休眠态（30分钟心跳最低功耗）")
else:
    print("❌ 改造3失败")

# ============================================================
# 改造4：阴期开始时记录阶段，初阴优先重活
# ============================================================
old_mode_set = '''    start_time = time.time()
    with state_lock:
        state["engine_mode"] = "idle"'''

new_mode_set = '''    start_time = time.time()
    with state_lock:
        if state.get("engine_mode") != "idle":
            # V4.0：刚进入阴期，标记为初阴，优先干重活
            state["idle_phase"] = "early"
            state["idle_start_time"] = time.time()
            log("[IDLE] ☯️ 阳转阴：进入初阴期，优先打磨存量重活")
        state["engine_mode"] = "idle"'''

if old_mode_set in content:
    content = content.replace(old_mode_set, new_mode_set)
    print("✅ 改造4完成：阴期开始标记初阴阶段")
else:
    print("❌ 改造4失败")

# ============================================================
# 改造5：额度平滑转阴——85%降并发，95%停新任务（反者道之动：不到顶就转）
# ============================================================
old_quota_check = '''                else:
                    engine_key, _ = select_engine(state, "exp")
                    if not engine_key:
                        log("[IDLE] 额度耗尽，切换空闲模式跑本地零消耗任务")
                        should_continue_idle = run_idle_task(state)
                        if should_continue_idle:
                            time.sleep(30)
                        continue'''

new_quota_check = '''                else:
                    engine_key, _ = select_engine(state, "exp")
                    # V4.0：额度平滑转阴——85%降并发，95%停新任务，反者道之动不到顶就转
                    a_used = state.get("engine_a", {}).get("tokens_used", 0)
                    c_used = state.get("engine_c", {}).get("tokens_used", 0)
                    a_thresh = state.get("engine_a", {}).get("daily_threshold", 1600000)
                    c_thresh = state.get("engine_c", {}).get("daily_threshold", 1600000)
                    max_ratio = max(a_used/max(1,a_thresh), c_used/max(1,c_thresh))
                    if max_ratio >= 0.95 and not state.get("idle_phase"):
                        # 95%：停止接新任务，排空在途后转阴
                        log(f"[IDLE] 额度95%({max_ratio:.0%})，停止接新任务，排空在途后转阴")
                        state["idle_phase"] = "winding_down"
                    elif max_ratio >= 0.85 and state.get("concurrency_override", 5) > 2:
                        # 85%：并发降到2路，平滑收功
                        state["concurrency_override"] = 2
                        log(f"[EVOLVE] 额度85%({max_ratio:.0%})，并发降为2路，平滑收功")
                    if not engine_key:
                        log("[IDLE] 额度耗尽，切换空闲模式跑本地零消耗任务")
                        should_continue_idle = run_idle_task(state)
                        if should_continue_idle:
                            time.sleep(30)
                        continue'''

if old_quota_check in content:
    content = content.replace(old_quota_check, new_quota_check)
    print("✅ 改造5完成：额度平滑转阴（85%降并发/95%停新任务）")
else:
    print("❌ 改造5失败")

# ============================================================
# 改造6：阴期结束切回阳期时，计算成长值（有生于无：阴期沉淀转化为阳期能力）
# ============================================================
old_mode_back = '''    if a_used < a_threshold or c_used < c_threshold:
        log(f"[IDLE] 额度已刷新(A:{a_used}/{a_threshold}, C:{c_used}/{c_threshold})，切回正常模式")
        with state_lock:
            state["engine_mode"] = "normal"
        save_state(state)
        return False'''

new_mode_back = '''    if a_used < a_threshold or c_used < c_threshold:
        # V4.0：阴转阳，计算本轮阴期成长值（有生于无：沉淀转化为能力）
        idle_start = state.get("idle_start_time", time.time())
        idle_duration = int((time.time() - idle_start) / 60)
        pit_gain = state.get("idle_pit_total", 0) - state.get("idle_pit_before", 0)
        c_archived = state.get("idle_c_level_archived", 0)
        distilled = state.get("idle_failure_distilled_total", 0)
        backup_ok = state.get("idle_backup_ok", 0)
        growth_score = pit_gain * 10 + c_archived * 2 + distilled * 5 + backup_ok * 15
        state.setdefault("idle_cycles", 0)
        state["idle_cycles"] += 1
        state.setdefault("total_growth_score", 0)
        state["total_growth_score"] += growth_score
        log(f"[IDLE] 🌅 阴转阳：本轮阴期{idle_duration}分钟，成长值+{growth_score}(坑+{pit_gain}/归档{c_archived}/蒸馏{distilled}/备份{backup_ok})，累计成长{state['total_growth_score']}")
        # 重置阴期状态
        state["idle_phase"] = None
        state["idle_pit_before"] = state.get("idle_pit_total", 0)
        with state_lock:
            state["engine_mode"] = "normal"
        save_state(state)
        return False'''

if old_mode_back in content:
    content = content.replace(old_mode_back, new_mode_back)
    print("✅ 改造6完成：阴转阳成长值计算（有生于无）")
else:
    print("❌ 改造6失败")

# ============================================================
# 改造7：run_idle_task文档串更新为V4.0
# ============================================================
old_doc = '''    """
    空闲模式V3.0：额度耗尽时跑本地零消耗任务
    P0: 统一异常隔离 + 内存预算 + 模式切换检查
    P1: 任务进度持久化 + 产出反哺 + 调度冷却
    P2: 分级调度 + 资源统计
    返回：True=继续空闲模式, False=额度已刷新应切回正常模式
    """'''

new_doc = '''    """
    空闲模式V4.0·阴阳节律生命体：额度耗尽时跑本地零消耗任务
    21字真言落地：
      反者道之动：85%降并发/95%停新任务，平滑转阴，不到顶就转
      弱者道之用：初阴重活→中阴轻活→深阴休眠(30分钟心跳)，越低耗越长久
      有生于无：阴期沉淀(坑/归档/蒸馏/备份)转化为成长值，反哺阳期能力
    返回：True=继续空闲模式, False=额度已刷新应切回正常模式
    """'''

if old_doc in content:
    content = content.replace(old_doc, new_doc)
    print("✅ 改造7完成：文档串更新为V4.0阴阳节律")
else:
    print("❌ 改造7失败")

# ============================================================
# 写回文件
# ============================================================
ENGINE_FILE.write_text(content, encoding="utf-8")
print("\n🎉 空闲模式V4.0·阴阳节律生命体 全部改造完成")
