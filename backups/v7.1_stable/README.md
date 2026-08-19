# 观尘子引擎 V7.1
> 自动化任务执行与认知质检引擎 · 决策-执行分层治理范式

## 架构概览
```
engine_v7_1/
├── engine.py              # 引擎主类（顶层协调器）
├── cli.py                 # 命令行入口
├── config.yaml            # 配置文件
├── core/                  # 核心引擎层
│   ├── config_manager.py  # 配置管理（热重载、验证）
│   ├── task_scheduler.py  # 任务调度（队列、重试、并发）
│   ├── health_checker.py  # 健康检查（7维度评分）
│   ├── state_manager.py   # 状态管理（键值、持久化）
│   ├── plugin_loader.py   # 插件加载（自动发现、热插拔）
│   └── model_manager.py   # 模型管理（双模型路由、Token统计）
├── modules/               # 业务模块层（可扩展）
│   ├── example_module.py  # 示例模块
│   └── ai_inference_module.py  # AI推理业务模块
├── utils/                 # 工具层
│   ├── logger.py          # 日志与审计（单例、轮转）
│   └── audit_logger.py    # 审计日志（兼容层）
├── data/                  # 数据持久化
│   └── state.json
└── logs/                  # 运行日志
    ├── engine.log
    └── audit.log
```

## 核心特性

### 1. 任务调度系统
- 优先级队列（0-10，数字越大优先级越高）
- 自动重试（可配置次数与退避策略）
- 多类型任务处理器注册
- 并发执行（线程池，可配置大小）
- 任务状态追踪与历史记录

### 2. 健康检查体系（7维度）
| 维度 | 说明 | 满分 |
|------|------|------|
| disk_space | 磁盘空间检查 | 100 |
| memory_usage | 内存使用率 | 100 |
| task_queue_health | 任务队列积压 | 100 |
| sync_status | 云端同步状态 | 100 |
| archive_integrity | 档案完整性 | 100 |
| config_validity | 配置有效性 | 100 |
| log_growth | 日志增长控制 | 100 |

### 3. 插件化架构
- 自动发现 `modules/` 目录下的业务模块
- 热插拔支持（运行时加载/卸载）
- 任务处理器自动注册
- 生命周期管理（start/stop）

### 4. 审计追踪
- 关键操作事件记录（JSON Lines格式）
- 可配置审计事件类型
- 事件查询与过滤

### 5. AI 推理双模型系统（V7.1 新增）
- **双模型路由**：观尘子主模型（工程推理）+ 星卷创作模型（创意生成）
- **任务类型自动分发**：根据任务类型自动选择最优模型
- **Token 精细化管理**：每日200万Token额度监控、按模型统计、超限预警
- **降级容错**：主模型不可用时自动切换备用模型
- **零API Key安全启动**：无密钥时以模拟模式运行，不阻塞引擎启动

**模型配置**：
| 模型ID | 显示名 | 定位 | 适用任务 |
|--------|--------|------|----------|
| guanchenzi_primary | 观尘子·工程推理 | 代码开发、参数推演、系统诊断 | engineering, code_review, system_diagnosis, data_analysis |
| xingjuan_creation | 星卷·宇宙创作 | 星空IP创作、史诗叙事、世界观构建 | creative_writing, worldbuilding, ip_creation, script |

## 快速开始

### 运行自检
```bash
python3 cli.py test
```

### 交互式启动
```bash
python3 cli.py start
# 可用命令: status, health, tasks, modules, quit
```

### 健康检查
```bash
python3 cli.py health
```

### 查看状态
```bash
python3 cli.py status
```

### 查看AI模型状态
```bash
python3 cli.py models
```

### 查看Token使用统计
```bash
python3 cli.py token
```

### 与AI模型对话测试
```bash
python3 cli.py chat                          # 默认观尘子主模型
python3 cli.py chat -m xingjuan_creation     # 星卷创作模型
python3 cli.py chat -m guanchenzi_primary -t engineering  # 指定任务类型
```

## 编写业务模块

在 `modules/` 目录下创建 `.py` 文件，引擎会自动发现并加载：

```python
__version__ = "1.0.0"

class MyModule:
    def __init__(self, config=None, logger=None, audit_logger=None, state_manager=None):
        self.config = config or {}
        self.logger = logger

    def get_task_handlers(self):
        """返回任务类型 -> 处理函数映射"""
        return {
            "my_task_type": self._handle_task,
        }

    def _handle_task(self, task):
        """处理任务，返回结果字典"""
        return {"result": "success", "data": task.metadata}

    def start(self):
        """可选：启动后台线程"""
        pass

    def stop(self):
        """可选：清理资源"""
        pass
```

## 配置说明

编辑 `config.yaml` 调整引擎行为：

- `engine.max_workers`: 并发线程数（默认4）
- `engine.health_check_interval`: 健康检查间隔秒数
- `task_scheduler.max_retries`: 任务最大重试次数
- `logging.level`: 日志级别（DEBUG/INFO/WARNING/ERROR）
- `logging.max_file_size_mb`: 日志文件大小上限
- `ai_inference.enabled`: 是否启用AI推理模块（默认true）
- `ai_inference.daily_token_limit`: 每日Token上限（默认2000000）
- `ai_inference.models`: 双模型配置（API端点、密钥、路由规则）

## 版本信息

- **当前版本**: V7.1.0
- **Python要求**: 3.8+
- **依赖**: 标准库（无第三方依赖）

## 设计哲学

> 反者道之动，弱者道之用。天地万物生于有，有生于无。

- **决策层与执行层分离**: 引擎作为执行层，专注批量事务处理
- **以实养虚，虚又返实**: 真实算力驱动认知框架，框架反哺代码产出
- **阴阳自衡**: 内部矛盾升维为制度性双轨运行
- **双模型协同**: 工程理性与创意感性双轨并行，各司其职
