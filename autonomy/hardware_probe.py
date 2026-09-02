#!/usr/bin/env python3
"""
硬件探针——启动时检测沙箱真实配置，决定模型档位。
对应坑库PIT-094：云沙箱内存配额动态变化，CPU型号随机分配。
设计原则：只观测不修改，输出JSON报告，由引擎决策层读取。
"""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def probe_cpu():
    """检测CPU型号、物理核、逻辑核、缓存。"""
    cpu_info = {}
    try:
        with open("/proc/cpuinfo") as f:
            lines = f.readlines()
        model_name = ""
        cache_size = ""
        for line in lines:
            if line.startswith("model name"):
                model_name = line.split(":")[1].strip()
            elif line.startswith("cache size"):
                cache_size = line.split(":")[1].strip()
        cpu_info["model"] = model_name
        cpu_info["cache"] = cache_size
        cpu_info["logical_cores"] = os.cpu_count() or 2
        # 物理核数
        physical_ids = set()
        core_ids = set()
        for line in lines:
            if line.startswith("physical id"):
                physical_ids.add(line.split(":")[1].strip())
            elif line.startswith("core id"):
                core_ids.add(line.split(":")[1].strip())
        cpu_info["physical_cores"] = len(core_ids) if core_ids else cpu_info["logical_cores"]
        cpu_info["sockets"] = len(physical_ids) if physical_ids else 1
    except Exception as e:
        cpu_info["error"] = str(e)
    return cpu_info


def probe_memory():
    """检测内存总量、可用、Swap。"""
    mem_info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_info["total_kb"] = int(line.split()[1])
                    mem_info["total_gb"] = round(mem_info["total_kb"] / 1024 / 1024, 2)
                elif line.startswith("MemAvailable:"):
                    mem_info["available_kb"] = int(line.split()[1])
                    mem_info["available_gb"] = round(mem_info["available_kb"] / 1024 / 1024, 2)
                elif line.startswith("SwapTotal:"):
                    mem_info["swap_kb"] = int(line.split()[1])
                    mem_info["has_swap"] = mem_info["swap_kb"] > 0
    except Exception as e:
        mem_info["error"] = str(e)
    return mem_info


def probe_disk():
    """检测磁盘挂载点和可用空间。"""
    disk_info = {}
    try:
        result = subprocess.run(
            ["df", "-h"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n")[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 6:
                mount = parts[5]
                if mount in ("/", "/tmp/user", "/sandboxdata/workspace") or "kata" in mount:
                    disk_info[mount] = {
                        "total": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "use_percent": parts[4],
                    }
    except Exception as e:
        disk_info["error"] = str(e)
    return disk_info


def probe_uptime():
    """检测沙箱运行时间。"""
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return {"seconds": int(seconds), "human": f"{hours}小时{minutes}分钟"}
    except Exception as e:
        return {"error": str(e)}


def decide_model_tier(cpu_info, mem_info):
    """
    根据硬件检测结果决定模型档位。
    档位规则：
    - 7B档：Intel Xeon好档 + 可用内存>=6GB
    - 1.5B档：可用内存>=2GB（预留，当前不下载）
    - 0.5B档：默认保底，任何环境都能跑
    """
    tier = "0.5B"
    reason = "默认保底档"
    available_gb = mem_info.get("available_gb", 0)
    cpu_model = cpu_info.get("model", "")
    cache = cpu_info.get("cache", "")

    # 7B档条件：Intel好档 + 6GB以上可用内存
    if "Xeon" in cpu_model and "Platinum" in cpu_model and available_gb >= 6.0:
        tier = "7B"
        reason = f"Intel Xeon好档 + 可用内存{available_gb}GB >= 6GB"
    # 1.5B档条件：可用内存>=2GB（预留，当前未下载模型）
    elif available_gb >= 2.0:
        tier = "0.5B"  # 暂时用0.5B，1.5B未下载
        reason = f"可用内存{available_gb}GB，0.5B保底（1.5B未下载）"

    return {"tier": tier, "reason": reason}


def main():
    report = {
        "probe_time": subprocess.run(
            ["date", "-Iseconds"], capture_output=True, text=True
        ).stdout.strip(),
        "hostname": platform.node(),
        "kernel": platform.release(),
        "cpu": probe_cpu(),
        "memory": probe_memory(),
        "disk": probe_disk(),
        "uptime": probe_uptime(),
    }
    report["model_decision"] = decide_model_tier(report["cpu"], report["memory"])

    # 输出到stdout
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 同时写入报告文件
    report_dir = Path(__file__).parent.parent / "data" / "hardware_reports"
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"probe_{report['probe_time'].replace(':', '-').replace('+', '_')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


if __name__ == "__main__":
    main()
