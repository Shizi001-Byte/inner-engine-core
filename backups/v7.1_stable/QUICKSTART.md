# 串行双引擎 V7.1 — 快速启动指南

## 一句话说明
观尘子（工程）和星卷（创作）**串行排队跑**，观尘子跑完150万自动切星卷，**断点自动续跑**，每次激活只跑指定秒数，到点安全收尾。

## 快速开始

```bash
# 进入目录
cd engine_v7_1

# 跑9分钟（默认540秒，沙箱安全窗口）
python3 serial_dual_engine.py

# 自定义时长
python3 serial_dual_engine.py --duration 300   # 跑5分钟
python3 serial_dual_engine.py --duration 60    # 跑1分钟

# 只看当前进度（不跑任务）
python3 serial_dual_engine.py --status

# 只跑指定引擎（跳过自动切换）
python3 serial_dual_engine.py --engine guanchenzi
python3 serial_dual_engine.py --engine xingjuan
```

## 核心机制

### 1. 串行调度（非并行）
```
观尘子 1,500,000 token → 达标 → 星卷 1,500,000 token → 全部完成
```
- 观尘子：工程型任务，每个 ~3,000 token（脚本、巡检、API集成）
- 星卷：创作型任务，每个 ~8,000 token（宇宙学、角色、剧情、诗篇）

### 2. 断点续跑
- 状态文件：`data/serial_runner_state.json`
- 每个任务完成后**立即保存**，断电/中断不丢失
- 下次启动自动从上次位置继续，**不会重置**

### 3. 沙箱安全窗口
- `--duration N` 控制本次运行秒数
- 最后 **10秒** 只做收尾，不接新任务
- 到点自动保存断点并退出，不会被强制中断

### 4. 每日目标
- 观尘子：1,500,000 token/天
- 星卷：1,500,000 token/天
- 合计：3,000,000 token/天
- 全部达标后自动停止

## 典型使用场景

### 场景1：每天分多次跑
```bash
# 早上跑9分钟
python3 serial_dual_engine.py --duration 540

# 中午再跑9分钟（自动续跑，不会重复）
python3 serial_dual_engine.py --duration 540

# 晚上再跑9分钟
python3 serial_dual_engine.py --duration 540
```
三次共跑27分钟，累计约135万token，断点自动衔接。

### 场景2：查看进度
```bash
python3 serial_dual_engine.py --status
```
输出：
```
  观尘子  |█████░░░░░░░░░░░░░░░░░░░░░░░░░|  16.8%
           252,000 /  1,500,000 tokens  (84个任务)
  星卷   |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|   0.0%
                 0 /  1,500,000 tokens  (0个任务)
```

### 场景3：重置进度（跨天或重新开始）
```bash
rm data/serial_runner_state.json
```

## 文件结构
```
engine_v7_1/
├── serial_dual_engine.py    # 主程序（零依赖，纯Python）
├── data/
│   └── serial_runner_state.json  # 断点状态（自动生成）
├── output/                   # 任务输出（自动生成）
├── README.md                 # 详细说明
├── QUICKSTART.md             # 本文件
└── CHANGELOG.md              # 版本记录
```

## 与V7.0的区别

| 特性 | V7.0 并行 | V7.1 串行 |
|------|----------|----------|
| 调度方式 | 双引擎同时跑 | 观尘子→星卷排队 |
| Token竞争 | 两个引擎抢额度 | 顺序消耗，无竞争 |
| 断点续跑 | 各自独立 | 统一状态文件 |
| 适用场景 | 紧急赶进度 | 稳定日常消耗 |
| 复杂度 | 高（需协调） | 低（简单可靠） |

## 故障排查

**Q: 启动后显示"剩余时间不足"直接退出？**
A: `--duration` 必须大于10秒（安全收尾阈值）。用 `--duration 30` 以上。

**Q: 观尘子跑完了但星卷没启动？**
A: 检查是否用了 `--engine guanchenzi` 强制单引擎模式。去掉该参数即可自动切换。

**Q: 想从0开始重新计数？**
A: 删除 `data/serial_runner_state.json`，下次启动自动初始化。

**Q: 可以后台运行吗？**
A: 可以：`nohup python3 serial_dual_engine.py --duration 540 &`
