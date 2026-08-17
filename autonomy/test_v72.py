#!/usr/bin/env python3
"""
V7.2 模块功能测试
- 任务解析器测试
- 状态管理测试
- 回执生成测试（不实际调用API）
- 瘦身脚本dry-run
- 同步管理器测试
"""
import json, os, sys, tempfile
from pathlib import Path
from datetime import datetime

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

# 基础目录 - 使用绝对路径避免符号链接解析问题
BASE_DIR = Path("/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_2")

def test_task_parser():
    """测试任务解析器"""
    print("\n" + "="*50)
    print("测试1: 任务解析器")
    print("="*50)

    # 导入解析函数
    from engine_daemon_v72 import parse_task_file

    # 创建JSON格式测试任务
    json_task = {
        "task_id": "test_001",
        "task_type": "execution",
        "priority": "P1",
        "core_target": "分析2026年Q3基金市场趋势",
        "accept_criteria": ["包含至少3个细分赛道", "数据来源可追溯", "输出结构化报告"],
        "deadline": "2026-08-18 18:00",
        "constraints": {"max_tokens": 2000, "engine_preference": "glm"},
    }
    json_path = BASE_DIR / "dispatch" / "inbox" / "test_json_001.json"
    with open(json_path, "w") as f:
        json.dump(json_task, f, ensure_ascii=False)

    result = parse_task_file(json_path)
    assert result is not None, "JSON任务解析失败"
    assert result["task_id"] == "test_001"
    assert result["priority"] == "P1"
    assert len(result["accept_criteria"]) == 3
    assert result["_source"] == "json"
    print(f"  ✓ JSON格式解析成功: task_id={result['task_id']}, priority={result['priority']}")

    # 创建极简文本格式测试任务
    text_task = """【P0】
核心目标：紧急修复V7.1引擎熔断Bug
验收：定位根因；提供修复方案；验证不影响双引擎路由
截止：2026-08-17 20:00"""
    text_path = BASE_DIR / "dispatch" / "inbox" / "test_text_001.json"
    with open(text_path, "w") as f:
        f.write(text_task)

    result2 = parse_task_file(text_path)
    assert result2 is not None, "文本任务解析失败"
    assert result2["priority"] == "P0"
    assert "修复V7.1" in result2["core_target"]
    assert len(result2["accept_criteria"]) == 3
    assert result2["_source"] == "text"
    print(f"  ✓ 文本格式解析成功: priority={result2['priority']}, criteria={len(result2['accept_criteria'])}条")

    # 清理测试文件
    json_path.unlink()
    text_path.unlink()
    print("  ✓ 测试文件已清理")
    return True

def test_state_management():
    """测试状态管理"""
    print("\n" + "="*50)
    print("测试2: 状态管理")
    print("="*50)

    from engine_daemon_v72 import load_state, save_state, check_daily_reset, update_task_status

    state = load_state()
    assert "engine_a" in state
    assert "engine_b" in state
    print(f"  ✓ 状态加载成功: date={state['date']}")

    # 修改并保存
    original_a = state["engine_a"]["tokens_used"]
    state["engine_a"]["tokens_used"] += 100
    save_state(state)

    state2 = load_state()
    assert state2["engine_a"]["tokens_used"] == original_a + 100
    print(f"  ✓ 状态持久化成功: tokens_used={state2['engine_a']['tokens_used']}")

    # 恢复原值
    state2["engine_a"]["tokens_used"] = original_a
    save_state(state2)

    # 任务状态更新
    update_task_status("test_status_001", "running", progress="50%")
    status_file = BASE_DIR / "dispatch" / "status" / "test_status_001.json"
    assert status_file.exists()
    with open(status_file) as f:
        data = json.load(f)
    assert data["status"] == "running"
    assert data["progress"] == "50%"
    print(f"  ✓ 任务状态更新成功")

    # 清理
    status_file.unlink()
    return True

def test_receipt_generation():
    """测试回执生成（模拟结果，不调用API）"""
    print("\n" + "="*50)
    print("测试3: 回执生成")
    print("="*50)

    from engine_daemon_v72 import generate_receipt, parse_task_file, load_state

    # 创建模拟任务
    task = {
        "task_id": "test_receipt_001",
        "priority": "P2",
        "core_target": "模拟测试任务",
        "accept_criteria": ["测试标准1"],
    }
    task_file = BASE_DIR / "dispatch" / "inbox" / "test_receipt_001.json"
    with open(task_file, "w") as f:
        json.dump(task, f)

    # 模拟成功结果
    mock_result = {
        "content": "这是模拟的任务执行结果，用于测试回执生成功能是否正常工作。",
        "tokens_used": 150,
        "duration_seconds": 2.3,
        "engine_used": "engine_a",
    }

    state = load_state()
    receipt = generate_receipt(task, mock_result, state)

    assert receipt["status"] == "completed"
    assert receipt["tokens_used"] == 150
    assert len(receipt["deliverables"]) == 1
    assert "md5" in receipt["deliverables"][0]

    receipt_file = BASE_DIR / "dispatch" / "receipts" / "test_receipt_001.json"
    assert receipt_file.exists()
    print(f"  ✓ 成功回执生成: status={receipt['status']}, md5={receipt['deliverables'][0]['md5'][:8]}...")

    # 验证产出文件
    output_path = BASE_DIR / "outputs" / "test_receipt_001_output.txt"
    assert output_path.exists()
    print(f"  ✓ 产出文件已保存: {output_path.name}")

    # 验证inbox已清理
    assert not task_file.exists(), "inbox文件应在完成后移除"
    print(f"  ✓ inbox文件已自动清理")

    # 清理测试产物
    receipt_file.unlink()
    output_path.unlink()
    return True

def test_body_slim_dryrun():
    """测试瘦身脚本（dry-run逻辑验证）"""
    print("\n" + "="*50)
    print("测试4: 本体瘦身脚本（逻辑验证）")
    print("="*50)

    from body_slim_daily import should_archive, CORE_ANCHORS
    from pathlib import Path as PathLib

    # 测试核心锚点保护 - 使用WORKSPACE下的路径
    import body_slim_daily as slim_mod
    anchor_path = slim_mod.WORKSPACE / "engine_v7_2" / "body" / "core_anchor.md"
    assert slim_mod.is_core_anchor(anchor_path), "core_anchor.md应被识别为核心锚点"
    print(f"  ✓ 核心锚点保护: core_anchor.md 永不归档")

    # 测试归档判断逻辑 - 使用WORKSPACE内的路径
    import body_slim_daily as slim_mod
    import time as time_mod

    class MockStat:
        def __init__(self, size, mtime_offset_days=0):
            self.st_size = size
            self.st_mtime = time_mod.time() - mtime_offset_days * 86400

    # 大文件应归档（使用.log扩展名确保在可归档列表中，且路径在workspace内）
    big_path = slim_mod.WORKSPACE / "test_big.log"
    archive, reason = slim_mod.should_archive(big_path, MockStat(10*1024*1024))
    assert archive, f"大文件应归档，但返回: {reason}"
    print(f"  ✓ 大文件归档判断: 10MB → {reason}")

    # 旧文件应归档
    old_path = slim_mod.WORKSPACE / "test_old.log"
    archive, reason = slim_mod.should_archive(old_path, MockStat(1024, 30))
    assert archive, f"旧文件应归档，但返回: {reason}"
    print(f"  ✓ 旧文件归档判断: 30天 → {reason}")

    # 新小文件不应归档（使用.txt扩展名，不在可归档扩展名中）
    new_path = slim_mod.WORKSPACE / "test_new.txt"
    archive, reason = slim_mod.should_archive(new_path, MockStat(1024, 1))
    assert not archive, f"新小文件不应归档，但返回: {reason}"
    print(f"  ✓ 新文件保留判断: 1天 → {reason}")

    return True

def test_sync_manager():
    """测试同步管理器"""
    print("\n" + "="*50)
    print("测试5: 双向同步管理器")
    print("="*50)

    from sync_manager import calculate_md5, load_sync_state, save_sync_state, SYNC_STATE_FILE

    # 测试MD5计算
    test_file = BASE_DIR / "body" / "core_anchor.md"
    md5 = calculate_md5(test_file)
    assert md5 is not None and len(md5) == 32
    print(f"  ✓ MD5计算: {md5[:8]}...")

    # 测试同步状态
    state = load_sync_state()
    assert "file_hashes" in state
    assert "conflicts" in state
    original_count = state.get("sync_count", 0)
    state["sync_count"] = original_count + 1
    save_sync_state(state)

    state2 = load_sync_state()
    assert state2["sync_count"] == original_count + 1
    print(f"  ✓ 同步状态持久化: sync_count={state2['sync_count']}")

    # 恢复
    state2["sync_count"] = original_count
    save_sync_state(state2)

    return True

def test_directory_structure():
    """测试目录结构完整性"""
    print("\n" + "="*50)
    print("测试6: 目录结构完整性")
    print("="*50)

    required_dirs = [
        "body",
        "dispatch/inbox",
        "dispatch/status",
        "dispatch/receipts",
        "dispatch/failed_tasks",
        "autonomy",
        "archive",
        "reports",
        "logs",
        "data",
        "outputs",
        "backups",
    ]

    all_ok = True
    for d in required_dirs:
        path = BASE_DIR / d
        if path.exists():
            print(f"  ✓ {d}/")
        else:
            print(f"  ✗ {d}/ 缺失")
            all_ok = False

    required_files = [
        "body/core_anchor.md",
        "body/body_call_rules.md",
        "dispatch/task_dispatch_spec.md",
        "dispatch/result_receipt_spec.md",
        "autonomy/engine_daemon_v72.py",
        "autonomy/body_slim_daily.py",
        "autonomy/sync_manager.py",
    ]

    for f in required_files:
        path = BASE_DIR / f
        if path.exists():
            print(f"  ✓ {f}")
        else:
            print(f"  ✗ {f} 缺失")
            all_ok = False

    return all_ok

def main():
    print("V7.2 脑体分离引擎 - 模块功能测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"基础目录: {BASE_DIR}")

    tests = [
        ("目录结构", test_directory_structure),
        ("任务解析器", test_task_parser),
        ("状态管理", test_state_management),
        ("回执生成", test_receipt_generation),
        ("瘦身脚本", test_body_slim_dryrun),
        ("同步管理器", test_sync_manager),
    ]

    results = {}
    for name, test_func in tests:
        try:
            ok = test_func()
            results[name] = "PASS" if ok else "FAIL"
        except Exception as e:
            results[name] = f"ERROR: {e}"
            import traceback
            traceback.print_exc()

    print("\n" + "="*50)
    print("测试结果汇总")
    print("="*50)
    for name, result in results.items():
        status = "✓" if result == "PASS" else "✗"
        print(f"  {status} {name}: {result}")

    all_pass = all(r == "PASS" for r in results.values())
    print(f"\n总体: {'全部通过 ✓' if all_pass else '存在失败 ✗'}")
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
