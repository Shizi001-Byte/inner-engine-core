#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verifier-hub 桥接模块
移植自：.skills/verifier-hub（确定性产物校验CLI，58个子命令）
用途：阴期零消耗任务，对引擎产出的JSON/代码/配置文件做确定性校验
原则：子进程调用CLI，不重写校验逻辑；超时优雅降级，不阻塞阴期调度
"""
import json
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent.parent
VERIFIER_CLI = BASE_DIR.parent / ".skills" / "verifier-hub" / "bin" / "verifier"
OUTPUT_DIR = BASE_DIR / "assets" / "yin_period"

# 引擎核心产出文件清单（相对BASE_DIR）
AUDIT_TARGETS = [
    {"path": "data/engine_state.json", "type": "json", "required": True},
    {"path": "data/backup_config.json", "type": "json", "required": False},
    {"path": "autonomy/engine_zhuan1.py", "type": "py", "required": True},
    {"path": "autonomy/yin_tasks.py", "type": "py", "required": True},
    {"path": "autonomy/self_evolution.py", "type": "py", "required": False},
]


def _run_verifier(args, timeout=30):
    """调用verifier CLI，返回解析后的JSON结果"""
    if not VERIFIER_CLI.exists():
        return {"ok": False, "error": f"CLI not found: {VERIFIER_CLI}"}
    try:
        result = subprocess.run(
            [str(VERIFIER_CLI)] + args,
            capture_output=True, text=True, timeout=timeout, cwd=str(BASE_DIR)
        )
        stdout = result.stdout.strip()
        if stdout:
            return json.loads(stdout)
        return {"ok": False, "error": result.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _check_json_file(filepath):
    """校验JSON文件：格式+可解析+非空"""
    full_path = BASE_DIR / filepath
    if not full_path.exists():
        return {"file": filepath, "status": "missing", "detail": "文件不存在"}
    # 用verifier rubric check-file-format
    fmt_result = _run_verifier(["rubric", "check-file-format", str(full_path), "--expected-ext", ".json"])
    format_ok = fmt_result.get("ok", False) and fmt_result.get("result", {}).get("passed", False)
    # 尝试解析JSON
    try:
        with open(full_path, encoding="utf-8") as f:
            data = json.load(f)
        parse_ok = True
        size = full_path.stat().st_size
        keys_count = len(data) if isinstance(data, dict) else len(data) if isinstance(data, list) else 0
    except Exception as e:
        parse_ok = False
        size = full_path.stat().st_size
        keys_count = 0
    status = "ok" if (format_ok and parse_ok) else "warn" if parse_ok else "fail"
    return {
        "file": filepath, "status": status,
        "format_ok": format_ok, "parse_ok": parse_ok,
        "size_bytes": size, "top_level_keys": keys_count
    }


def _check_py_file(filepath):
    """校验Python文件：语法+非空+大小"""
    full_path = BASE_DIR / filepath
    if not full_path.exists():
        return {"file": filepath, "status": "missing", "detail": "文件不存在"}
    size = full_path.stat().st_size
    # 语法检查
    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(full_path)],
            capture_output=True, text=True, timeout=30
        )
        syntax_ok = result.returncode == 0
        syntax_err = result.stderr.strip()[:200] if not syntax_ok else ""
    except Exception as e:
        syntax_ok = False
        syntax_err = str(e)[:200]
    status = "ok" if syntax_ok and size > 100 else "warn" if syntax_ok else "fail"
    return {
        "file": filepath, "status": status,
        "syntax_ok": syntax_ok, "size_bytes": size,
        "syntax_error": syntax_err
    }


def _audit_cognition_pool():
    """抽检认知池：随机5个JSON文件校验格式"""
    cog_dir = BASE_DIR / "cognition_pool"
    if not cog_dir.exists():
        return {"status": "skipped", "reason": "cognition_pool not found"}
    files = sorted([f for f in cog_dir.glob("*.json") if f.is_file()])
    if not files:
        return {"status": "skipped", "reason": "no cognition files"}
    # 抽检最新5个+最旧5个
    sample = files[-5:] + files[:5] if len(files) >= 10 else files
    results = []
    fail_count = 0
    for f in sample:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            # 认知池标准字段：id + core_statement/key_points 至少一个
            ok = isinstance(data, dict) and "id" in data and ("core_statement" in data or "key_points" in data or "text" in data)
            if not ok:
                fail_count += 1
            results.append({"file": f.name, "ok": ok, "size": f.stat().st_size})
        except Exception as e:
            fail_count += 1
            results.append({"file": f.name, "ok": False, "error": str(e)[:100]})
    return {
        "status": "ok" if fail_count == 0 else "warn",
        "total_files": len(files), "sampled": len(sample),
        "fail_count": fail_count, "details": results
    }


def _audit_pit_library():
    """校验坑库：所有JSON文件格式+必填字段"""
    pit_dir = BASE_DIR / "data" / "pit_library"
    if not pit_dir.exists():
        return {"status": "skipped", "reason": "pit_library not found"}
    files = sorted([f for f in pit_dir.glob("*.json") if f.is_file()])
    required_fields = ["pit_id", "name", "level", "phenomenon", "root_cause"]
    results = []
    fail_count = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            missing = [field for field in required_fields if field not in data]
            ok = len(missing) == 0
            if not ok:
                fail_count += 1
            results.append({"file": f.name, "ok": ok, "missing": missing})
        except Exception as e:
            fail_count += 1
            results.append({"file": f.name, "ok": False, "error": str(e)[:100]})
    return {
        "status": "ok" if fail_count == 0 else "warn",
        "total_pits": len(files), "fail_count": fail_count,
        "failed_files": [r["file"] for r in results if not r["ok"]][:10]
    }


def run(state=None, **kwargs):
    """
    阴期任务入口：引擎产出文件确定性校验
    返回统一格式：{ok, name, result, evidence, output_path}
    """
    start = time.time()
    audit_results = {"core_files": [], "cognition_pool": {}, "pit_library": {}}

    # 1. 核心文件校验
    for target in AUDIT_TARGETS:
        if target["type"] == "json":
            audit_results["core_files"].append(_check_json_file(target["path"]))
        elif target["type"] == "py":
            audit_results["core_files"].append(_check_py_file(target["path"]))

    # 2. 认知池抽检
    audit_results["cognition_pool"] = _audit_cognition_pool()

    # 3. 坑库全量校验
    audit_results["pit_library"] = _audit_pit_library()

    # 汇总
    fail_files = [f["file"] for f in audit_results["core_files"] if f["status"] == "fail"]
    warn_files = [f["file"] for f in audit_results["core_files"] if f["status"] == "warn"]
    total_issues = len(fail_files) + len(warn_files)
    overall_status = "ok" if total_issues == 0 else "warn" if len(fail_files) == 0 else "fail"

    result = {
        "status": overall_status,
        "duration_seconds": round(time.time() - start, 2),
        "core_files_checked": len(audit_results["core_files"]),
        "fail_files": fail_files,
        "warn_files": warn_files,
        "cognition_pool": audit_results["cognition_pool"],
        "pit_library": audit_results["pit_library"],
        "audit_time": datetime.now().isoformat()
    }

    # 保存产出
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"verifier_audit_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    evidence = f"校验{len(audit_results['core_files'])}个核心文件，失败{len(fail_files)}个，警告{len(warn_files)}个；坑库{audit_results['pit_library'].get('total_pits',0)}个，失败{audit_results['pit_library'].get('fail_count',0)}个"

    return {
        "ok": overall_status != "fail",
        "name": "yin_verifier_audit",
        "result": result,
        "evidence": evidence,
        "output_path": str(output_path)
    }


if __name__ == "__main__":
    # 独立测试
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
