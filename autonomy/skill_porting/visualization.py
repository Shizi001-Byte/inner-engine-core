#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引擎运行状态可视化模块
移植自：.skills/doubao-visualization（结构化关系图形化表达）
用途：阴期零消耗任务，把引擎运行数据生成HTML可视化报告
原则：纯本地生成HTML+CSS+JS，零API调用；所有数据来自状态文件/认知池/坑库/日志
"""
import json
import glob
import os
import re
from datetime import datetime

def get_base_dir():
    """获取引擎根目录"""
    # __file__ = autonomy/skill_porting/visualization.py
    # dirname x3 = engine_v7_2/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_state():
    """加载引擎状态"""
    state_file = os.path.join(get_base_dir(), "data", "engine_state.json")
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_cognition_stats():
    """统计认知池分级分布，适配两种格式：直接认知条目和任务快照"""
    cog_dir = os.path.join(get_base_dir(), "cognition_pool")
    stats = {"S": 0, "A": 0, "B": 0, "C": 0, "unknown": 0}
    if not os.path.exists(cog_dir):
        return stats
    def count_grade(c):
        density_obj = c.get("density", {})
        grade = density_obj.get("grade", c.get("grade", c.get("density_grade", "unknown")))
        if grade in stats:
            stats[grade] += 1
        else:
            stats["unknown"] += 1
    for f in glob.glob(os.path.join(cog_dir, "*.json")):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            # 格式1：任务快照，cognitions是数组
            if isinstance(data.get("cognitions"), list):
                for c in data["cognitions"]:
                    if isinstance(c, dict):
                        count_grade(c)
            # 格式2：直接认知条目
            elif "core_statement" in data or "text" in data or "content" in data or "density" in data:
                count_grade(data)
            else:
                stats["unknown"] += 1
        except Exception:
            stats["unknown"] += 1
    return stats

def load_pit_stats():
    """统计坑库分级分布"""
    pit_dir = os.path.join(get_base_dir(), "data", "pit_library")
    stats = {"L1": 0, "L2": 0, "L3": 0, "active": 0, "fixed": 0, "unknown": 0}
    if not os.path.exists(pit_dir):
        return stats
    for f in glob.glob(os.path.join(pit_dir, "*.json")):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                p = json.load(fh)
            level = p.get("level", "unknown")
            status = p.get("status", "unknown")
            if level in stats:
                stats[level] += 1
            else:
                stats["unknown"] += 1
            if status == "active" or status == "open":
                stats["active"] += 1
            elif status == "fixed" or "fixed" in str(status):
                stats["fixed"] += 1
        except Exception:
            stats["unknown"] += 1
    return stats

def load_nine_dim_progress(state):
    """获取九维进度"""
    dims = state.get("nine_dim_progress", {})
    result = {}
    for dim, data in dims.items():
        result[dim] = data.get("count", data.get("task_count", 0))
    return result

def load_model_usage(state):
    """获取三模型使用情况"""
    models = {}
    for key, label in [("engine_a", "A主"), ("engine_b", "B轻"), ("engine_c", "C中")]:
        e = state.get(key, {})
        used = e.get("tokens_used", 0)
        threshold = e.get("daily_threshold", 800000)
        models[label] = {
            "used": used,
            "threshold": threshold,
            "percent": round(used / max(1, threshold) * 100, 1),
            "requests": e.get("requests", 0)
        }
    return models

def generate_html(state, cog_stats, pit_stats, nine_dim, models):
    """生成HTML可视化报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_cogs = sum(cog_stats.values())
    total_pits = pit_stats.get("L1",0) + pit_stats.get("L2",0) + pit_stats.get("L3",0) + pit_stats.get("unknown",0)
    total_completed = state.get("total_completed", state.get("tasks_completed", 0))
    sixiang = state.get("sixiang_state", "unknown")
    concurrency = state.get("concurrency_override", 5)

    # 九维数据
    dim_labels = list(nine_dim.keys())
    dim_values = list(nine_dim.values())
    max_dim = max(dim_values) if dim_values else 1

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>引擎运行状态可视化报告 - {now}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0e1a; color: #e0e6f0; padding: 20px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
.header {{ text-align: center; margin-bottom: 30px; padding: 20px; background: linear-gradient(135deg, #1a1f3a, #0d1225); border-radius: 12px; border: 1px solid #2a3050; }}
.header h1 {{ font-size: 24px; color: #7eb8ff; margin-bottom: 8px; }}
.header .meta {{ font-size: 13px; color: #8892b0; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
.stat-card {{ background: linear-gradient(135deg, #1a1f3a, #0d1225); border-radius: 10px; padding: 20px; border: 1px solid #2a3050; text-align: center; }}
.stat-card .value {{ font-size: 32px; font-weight: bold; color: #7eb8ff; margin-bottom: 5px; }}
.stat-card .label {{ font-size: 13px; color: #8892b0; }}
.charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin-bottom: 30px; }}
.chart-card {{ background: linear-gradient(135deg, #1a1f3a, #0d1225); border-radius: 10px; padding: 20px; border: 1px solid #2a3050; }}
.chart-card h3 {{ font-size: 16px; color: #7eb8ff; margin-bottom: 15px; text-align: center; }}
.chart-container {{ position: relative; height: 300px; }}
.model-bars {{ margin-top: 20px; }}
.model-bar {{ margin-bottom: 15px; }}
.model-bar .label {{ display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 5px; }}
.model-bar .bar-bg {{ height: 20px; background: #1a1f3a; border-radius: 10px; overflow: hidden; }}
.model-bar .bar-fill {{ height: 100%; border-radius: 10px; transition: width 0.5s; }}
.footer {{ text-align: center; padding: 20px; color: #5a6380; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>九转玄功引擎 · 运行状态可视化报告</h1>
<div class="meta">生成时间：{now} | 四象状态：{sixiang} | 并发数：{concurrency}路</div>
</div>

<div class="stats-grid">
<div class="stat-card"><div class="value">{total_completed}</div><div class="label">累计完成任务</div></div>
<div class="stat-card"><div class="value">{total_cogs}</div><div class="label">认知池条目</div></div>
<div class="stat-card"><div class="value">{total_pits}</div><div class="label">坑库条目</div></div>
<div class="stat-card"><div class="value">{state.get('zhuan_count', 0)}</div><div class="label">当前转数</div></div>
</div>

<div class="charts-grid">
<div class="chart-card">
<h3>九维进度</h3>
<div class="chart-container"><canvas id="nineDimChart"></canvas></div>
</div>
<div class="chart-card">
<h3>认知分级分布</h3>
<div class="chart-container"><canvas id="cognitionChart"></canvas></div>
</div>
<div class="chart-card">
<h3>坑库分级分布</h3>
<div class="chart-container"><canvas id="pitChart"></canvas></div>
</div>
<div class="chart-card">
<h3>三模型额度使用</h3>
<div class="model-bars">
"""

    # 模型进度条
    colors = {"A主": "#ff6b6b", "B轻": "#4ecdc4", "C中": "#ffe66d"}
    for label, data in models.items():
        color = colors.get(label, "#7eb8ff")
        html += f"""<div class="model-bar">
<div class="label"><span>{label} ({data['requests']}次请求)</span><span>{data['used']:,} / {data['threshold']:,} ({data['percent']}%)</span></div>
<div class="bar-bg"><div class="bar-fill" style="width:{data['percent']}%;background:{color};"></div></div>
</div>"""

    html += """
</div>
</div>
</div>

<div class="footer">
<p>九转玄功引擎 V7.2 · 阴期可视化任务自动生成 · 数据来源：engine_state.json / cognition_pool / pit_library</p>
</div>
</div>

<script>
// 九维进度雷达图
const nineDimCtx = document.getElementById('nineDimChart').getContext('2d');
new Chart(nineDimCtx, {
    type: 'radar',
    data: {
        labels: """ + json.dumps(dim_labels, ensure_ascii=False) + """,
        datasets: [{
            label: '九维进度',
            data: """ + json.dumps(dim_values) + """,
            backgroundColor: 'rgba(126, 184, 255, 0.2)',
            borderColor: '#7eb8ff',
            borderWidth: 2,
            pointBackgroundColor: '#7eb8ff'
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            r: { beginAtZero: true, max: """ + str(max_dim) + """, ticks: { color: '#8892b0', backdropColor: 'transparent' }, grid: { color: '#2a3050' }, angleLines: { color: '#2a3050' }, pointLabels: { color: '#e0e6f0', font: { size: 11 } } }
        },
        plugins: { legend: { display: false } }
    }
});

// 认知分级饼图
const cogCtx = document.getElementById('cognitionChart').getContext('2d');
new Chart(cogCtx, {
    type: 'doughnut',
    data: {
        labels: ['S级', 'A级', 'B级', 'C级', '未知'],
        datasets: [{
            data: [""" + str(cog_stats.get('S',0)) + """, """ + str(cog_stats.get('A',0)) + """, """ + str(cog_stats.get('B',0)) + """, """ + str(cog_stats.get('C',0)) + """, """ + str(cog_stats.get('unknown',0)) + """],
            backgroundColor: ['#ff6b6b', '#ffe66d', '#4ecdc4', '#7eb8ff', '#5a6380'],
            borderWidth: 0
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { color: '#e0e6f0', font: { size: 12 } } } }
    }
});

// 坑库分级柱状图
const pitCtx = document.getElementById('pitChart').getContext('2d');
new Chart(pitCtx, {
    type: 'bar',
    data: {
        labels: ['L1工程级', 'L2流程级', 'L3认知级', '活跃中', '已修复'],
        datasets: [{
            label: '坑库数量',
            data: [""" + str(pit_stats.get('L1',0)) + """, """ + str(pit_stats.get('L2',0)) + """, """ + str(pit_stats.get('L3',0)) + """, """ + str(pit_stats.get('active',0)) + """, """ + str(pit_stats.get('fixed',0)) + """],
            backgroundColor: ['#ff6b6b', '#ffe66d', '#4ecdc4', '#ff9f43', '#26de81'],
            borderRadius: 6
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            y: { beginAtZero: true, ticks: { color: '#8892b0' }, grid: { color: '#2a3050' } },
            x: { ticks: { color: '#8892b0', font: { size: 11 } }, grid: { display: false } }
        },
        plugins: { legend: { display: false } }
    }
});
</script>
</body>
</html>"""
    return html

def run(state=None, **kwargs):
    """主入口：生成可视化报告"""
    state = state or load_state()
    cog_stats = load_cognition_stats()
    pit_stats = load_pit_stats()
    nine_dim = load_nine_dim_progress(state)
    models = load_model_usage(state)
    html = generate_html(state, cog_stats, pit_stats, nine_dim, models)
    output_dir = os.path.join(get_base_dir(), "data", "visualizations")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"engine_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    output_path = os.path.join(output_dir, filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return {
        "ok": True,
        "name": "yin_visualization",
        "result": {
            "cognition_stats": cog_stats,
            "pit_stats": pit_stats,
            "nine_dim_count": len(nine_dim),
            "models": models,
            "output_file": filename
        },
        "evidence": f"生成可视化报告，认知{sum(cog_stats.values())}条/坑库{pit_stats.get('L1',0)+pit_stats.get('L2',0)+pit_stats.get('L3',0)}个/九维{len(nine_dim)}维",
        "output_path": output_path
    }

if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
