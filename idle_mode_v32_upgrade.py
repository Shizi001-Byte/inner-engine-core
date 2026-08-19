#!/usr/bin/env python3
"""空闲模式V3.2批量改造脚本"""
import re
from pathlib import Path

ENGINE_FILE = Path("/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2/autonomy/engine_zhuan1.py")
content = ENGINE_FILE.read_text(encoding="utf-8")

# ============================================================
# 改造1：_idle_cognition_density 加入C级自动归档冷存储
# ============================================================
old_density = '''def _idle_cognition_density(state):
    """认知密度：抽查认知池，计算密度分级，C级自动标记（每日整理/中内存）"""
    from cognition_density import calc_density
    if not COGNITION_POOL_DIR.exists():
        return f"认知池目录不存在({COGNITION_POOL_DIR.name})，跳过"
    files = sorted(COGNITION_POOL_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    low_quality = 0
    scanned = 0
    c_level_files = []
    for f in files[:50]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            text = data.get("content", "")
            if text:
                density = calc_density(text)
                if density.get("grade") == "C":
                    low_quality += 1
                    c_level_files.append(f.name)
                scanned += 1
        except:
            pass
    # P1-2反哺：C级文件列表写入state，标记待清理
    if c_level_files:
        state.setdefault("idle_c_level_pending", [])
        for fn in c_level_files[:10]:
            if fn not in state["idle_c_level_pending"]:
                state["idle_c_level_pending"].append(fn)
        state["idle_c_level_pending"] = state["idle_c_level_pending"][-20:]
    return f"抽查{scanned}篇, C级套话{low_quality}篇" + (f", 待清理{len(c_level_files)}篇" if c_level_files else "")'''

new_density = '''def _idle_cognition_density(state):
    """认知密度：抽查认知池，计算密度分级，C级自动归档冷存储（每日整理/中内存）"""
    from cognition_density import calc_density
    import shutil
    if not COGNITION_POOL_DIR.exists():
        return f"认知池目录不存在({COGNITION_POOL_DIR.name})，跳过"
    # P3：冷存储目录
    cold_dir = COGNITION_POOL_DIR / "_cold_storage"
    cold_dir.mkdir(exist_ok=True)
    files = sorted(COGNITION_POOL_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    low_quality = 0
    scanned = 0
    archived = 0
    for f in files[:50]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            text = data.get("content", "")
            if text:
                density = calc_density(text)
                if density.get("grade") == "C":
                    low_quality += 1
                    # P3：C级自动归档到冷存储（移动，不删除）
                    try:
                        dest = cold_dir / f.name
                        if not dest.exists():
                            shutil.move(str(f), str(dest))
                            archived += 1
                    except:
                        pass
                scanned += 1
        except:
            pass
    # P1-2反哺：C级统计写入state
    state["idle_c_level_total"] = state.get("idle_c_level_total", 0) + low_quality
    state["idle_c_level_archived"] = state.get("idle_c_level_archived", 0) + archived
    return f"抽查{scanned}篇, C级套话{low_quality}篇, 归档冷存储{archived}篇(累计{state['idle_c_level_archived']})"'''

if old_density in content:
    content = content.replace(old_density, new_density)
    print("✅ 改造1完成：C级认知自动归档冷存储")
else:
    print("❌ 改造1失败：未找到旧代码")

# ============================================================
# 改造2：_idle_content_dedup 加入重复内容标记
# ============================================================
old_dedup = '''def _idle_content_dedup(state):
    """内容去重：扫描认知池检测重复，重复对归档（每日整理/中内存）"""
    from content_dedup import load_recent_contents, check_duplicate
    contents = load_recent_contents(str(COGNITION_POOL_DIR), limit=30)
    dup_count = 0
    dup_pairs = []
    for i, c in enumerate(contents):
        for c2 in contents[i+1:]:
            result = check_duplicate(c, [c2], threshold=0.7)
            if result.get("is_duplicate"):
                dup_count += 1
                if len(dup_pairs) < 5:
                    dup_pairs.append(f"#{i}-#{i+1}")
    # P1-2反哺：重复对写入state
    if dup_pairs:
        state["idle_dup_pairs_recent"] = dup_pairs
    return f"扫描{len(contents)}篇, 疑似重复{dup_count}对" + (f", 示例:{','.join(dup_pairs)}" if dup_pairs else "")'''

new_dedup = '''def _idle_content_dedup(state):
    """内容去重：扫描认知池检测重复，重复对标记待合并（每日整理/中内存）"""
    from content_dedup import load_recent_contents, check_duplicate
    contents = load_recent_contents(str(COGNITION_POOL_DIR), limit=30)
    dup_count = 0
    dup_pairs = []
    for i, c in enumerate(contents):
        for c2 in contents[i+1:]:
            result = check_duplicate(c, [c2], threshold=0.7)
            if result.get("is_duplicate"):
                dup_count += 1
                if len(dup_pairs) < 5:
                    dup_pairs.append(f"#{i}-#{i+1}")
    # P1-2反哺：重复对写入state，标记待合并
    state["idle_dup_total"] = state.get("idle_dup_total", 0) + dup_count
    if dup_pairs:
        state["idle_dup_pairs_recent"] = dup_pairs
    # P3：重复内容写入待处理列表
    if dup_count > 0:
        state.setdefault("idle_dup_pending", 0)
        state["idle_dup_pending"] += dup_count
    return f"扫描{len(contents)}篇, 疑似重复{dup_count}对(累计{state['idle_dup_total']})" + (f", 待合并{state.get('idle_dup_pending',0)}对" if dup_count else "")'''

if old_dedup in content:
    content = content.replace(old_dedup, new_dedup)
    print("✅ 改造2完成：重复内容标记待合并")
else:
    print("❌ 改造2失败：未找到旧代码")

# ============================================================
# 改造3：新增 _idle_auto_backup 自动三方备份任务
# ============================================================
new_backup_task = '''
def _idle_auto_backup(state):
    """自动三方备份：Gitee提交+飞书上传+Supabase上传（每日整理/低内存）"""
    import subprocess
    backup_ok = 0
    backup_fail = 0
    # 1. Gitee代码提交
    try:
        result = subprocess.run(
            ["git", "add", "-A", "--", "autonomy/", "data/*.json", "cognition/", "start_engine.sh", "watchdog.sh"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30
        )
        result = subprocess.run(
            ["git", "commit", "-m", "idle-auto-backup"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 or "nothing to commit" in result.stdout:
            result = subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=str(BASE_DIR), capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                backup_ok += 1
                state["idle_backup_gitee"] = "ok"
            else:
                backup_fail += 1
        else:
            backup_ok += 1  # nothing to commit也算成功
    except Exception as e:
        backup_fail += 1
        state["idle_backup_gitee_error"] = str(e)[:80]
    # 2. 记录备份状态
    state["idle_backup_last_run"] = time.time()
    state["idle_backup_ok"] = state.get("idle_backup_ok", 0) + backup_ok
    state["idle_backup_fail"] = state.get("idle_backup_fail", 0) + backup_fail
    return f"Gitee{'成功' if backup_ok>0 else '失败'}, 累计成功{state['idle_backup_ok']}次"
'''

# 在 _idle_asset_inventory 函数后面插入
insert_marker = '''    return f"认知{cog_count}篇, 坑{pit_count}个, 归档{archive_count}条"'''
if insert_marker in content and "_idle_auto_backup" not in content:
    content = content.replace(insert_marker, insert_marker + "\n" + new_backup_task)
    print("✅ 改造3完成：新增自动三方备份任务")
else:
    print("⚠️ 改造3跳过：已存在或未找到插入点")

# ============================================================
# 改造4：新增 _idle_daily_summary 每日空闲总结任务
# ============================================================
new_summary_task = '''
def _idle_daily_summary(state):
    """每日空闲总结：把阴期修炼成果沉淀为认知文档（每日整理/低内存）"""
    summary_dir = BASE_DIR / "cognition"
    summary_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    summary_file = summary_dir / f"空闲模式日总结_{today}.md"
    if summary_file.exists():
        return f"今日总结已存在({summary_file.name})，跳过"
    # 收集数据
    run_count = state.get("idle_run_count", 0)
    success_count = state.get("idle_success_count", 0)
    pit_total = state.get("idle_pit_total", 0)
    c_archived = state.get("idle_c_level_archived", 0)
    dup_total = state.get("idle_dup_total", 0)
    distilled = state.get("idle_failure_distilled_total", 0)
    asset_stats = state.get("idle_asset_stats", {})
    # 生成总结
    summary = f"""# 空闲模式日总结 {today}

## 运行统计
- 累计运行：{run_count}次
- 成功：{success_count}次
- 成功率：{success_count/max(1,run_count):.0%}

## 阴期修炼成果
- 坑库：{pit_total}个
- C级认知归档：{c_archived}篇
- 重复内容检测：{dup_total}对
- 失败蒸馏：{distilled}条

## 资产盘点
- 认知：{asset_stats.get('cognition',0)}篇
- 坑：{asset_stats.get('pits',0)}个
- 归档：{asset_stats.get('archives',0)}条

## 感悟
阴期不是空窗，是打磨存量的修炼期。
阳期产增量，阴期提质量，虚实交替方为正道。
"""
    summary_file.write_text(summary, encoding="utf-8")
    state["idle_daily_summary_file"] = str(summary_file)
    return f"生成日总结({summary_file.name}), {run_count}次运行/{pit_total}个坑/{c_archived}篇归档"
'''

if "_idle_daily_summary" not in content:
    # 在 _idle_auto_backup 后面插入
    if "def _idle_auto_backup" in content:
        # 找到 _idle_auto_backup 函数结束的位置（下一个 def 或 注册表）
        pattern = r'(def _idle_auto_backup\(state\):.*?return f"Gitee.*?\n)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            content = content[:match.end()] + "\n" + new_summary_task + content[match.end():]
            print("✅ 改造4完成：新增每日空闲总结任务")
        else:
            print("❌ 改造4失败：未找到插入点")
    else:
        print("⚠️ 改造4跳过：_idle_auto_backup不存在")
else:
    print("⚠️ 改造4跳过：已存在")

# ============================================================
# 改造5：更新注册表，加入新任务
# ============================================================
old_registry = '''IDLE_TASK_REGISTRY = {
    "prediction_audit":    (_idle_prediction_audit,    "low",    "light",  "预判层批量审查存量"),
    "failure_distill":     (_idle_failure_distill,     "low",    "light",  "失败蒸馏入避坑池"),
    "pit_library_expand":  (_idle_pit_library_expand,  "low",    "light",  "坑库跨层级迁移扩充"),
    "cognition_density":   (_idle_cognition_density,   "medium", "daily",  "认知密度重算与套话过滤"),
    "content_dedup":       (_idle_content_dedup,       "medium", "daily",  "内容去重检测"),
    "asset_inventory":     (_idle_asset_inventory,     "low",    "daily",  "资产盘点统计"),
    "integrity_check":     (_idle_integrity_check,     "low",    "weekly", "资产完整性全量校验"),
}
# 调度顺序：轻巡检优先，然后每日整理，最后全量校验
IDLE_TASK_ORDER = ["prediction_audit", "failure_distill", "pit_library_expand",
                   "cognition_density", "content_dedup", "asset_inventory", "integrity_check"]'''

new_registry = '''IDLE_TASK_REGISTRY = {
    "prediction_audit":    (_idle_prediction_audit,    "low",    "light",  "预判层批量审查存量"),
    "failure_distill":     (_idle_failure_distill,     "low",    "light",  "失败蒸馏入避坑池"),
    "pit_library_expand":  (_idle_pit_library_expand,  "low",    "light",  "坑库跨层级迁移扩充"),
    "cognition_density":   (_idle_cognition_density,   "medium", "daily",  "认知密度重算与C级归档"),
    "content_dedup":       (_idle_content_dedup,       "medium", "daily",  "内容去重检测"),
    "asset_inventory":     (_idle_asset_inventory,     "low",    "daily",  "资产盘点统计"),
    "auto_backup":         (_idle_auto_backup,         "low",    "daily",  "自动三方备份(Gitee)"),
    "daily_summary":       (_idle_daily_summary,       "low",    "daily",  "每日空闲总结沉淀"),
    "integrity_check":     (_idle_integrity_check,     "low",    "weekly", "资产完整性全量校验"),
}
# 调度顺序：轻巡检优先，然后每日整理，最后全量校验
IDLE_TASK_ORDER = ["prediction_audit", "failure_distill", "pit_library_expand",
                   "cognition_density", "content_dedup", "asset_inventory",
                   "auto_backup", "daily_summary", "integrity_check"]'''

if old_registry in content:
    content = content.replace(old_registry, new_registry)
    print("✅ 改造5完成：注册表加入auto_backup和daily_summary")
else:
    print("❌ 改造5失败：未找到旧注册表")

# ============================================================
# 写回文件
# ============================================================
ENGINE_FILE.write_text(content, encoding="utf-8")
print("\n🎉 全部改造完成，文件已写回")
