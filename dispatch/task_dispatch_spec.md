# 任务下发标准规范 V7.2
> 本体→引擎的唯一交互格式。本体仅需按格式输出极简指令，引擎自动解析入队。

## 一、标准下发格式（JSON）

```json
{
  "task_id": "T20260817_001",
  "priority": "P0|P1|P2|P3",
  "task_type": "execution|research|creation|maintenance|backup",
  "core_target": "一句话描述核心目标",
  "accept_criteria": [
    "验收标准1",
    "验收标准2"
  ],
  "deadline": "2026-08-17 18:00:00",
  "input_refs": ["相关文件路径或URL"],
  "constraints": {
    "max_tokens": 200000,
    "timeout_minutes": 30,
    "engine_preference": "auto|engine_a|engine_b"
  }
}
```

## 二、字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| task_id | 是 | 格式：T+日期+序号，如 T20260817_001 |
| priority | 是 | P0=紧急阻断，P1=当日必达，P2=三日内，P3=低优归档 |
| task_type | 是 | execution/research/creation/maintenance/backup |
| core_target | 是 | 一句话，不超过50字，不写实现步骤 |
| accept_criteria | 是 | 可量化的验收标准列表，2-5条 |
| deadline | 否 | 截止时间，缺省=当日24:00 |
| input_refs | 否 | 输入文件路径/URL列表 |
| constraints | 否 | 资源约束，缺省由引擎自动分配 |

## 三、极简下发模式（本体常用）

本体可使用简化文本格式，引擎自动解析转换：

```
【P1】核心目标：xxx
验收：1.xxx 2.xxx
截止：今日18:00
```

## 四、三种下发通道

### 通道1：主会话直接指令（默认）
- 本体在对话中按上述格式输出
- 引擎监听主会话，自动提取任务入队
- 适用于实时交互任务

### 通道2：云电脑指定目录投递
- 本体将任务JSON写入 `dispatch/inbox/` 目录
- 文件名：`{task_id}.json`
- 引擎定时扫描目录（默认30秒），自动拾取
- 适用于批量任务、离线任务

### 通道3：Gitee仓库更新触发
- 本体推送任务文件至Gitee指定分支
- 引擎通过webhook或定时拉取检测更新
- 适用于多端协同、异地触发

## 五、任务状态流转

```
[inbox] 待拾取 → [queued] 已入队 → [running] 执行中
     ↓              ↓              ↓
  [failed]拾取失败  [cancelled]取消  [completed]完成
                                  ↓
                            [failed]执行失败 → [retrying]重试中
```

状态文件写入 `dispatch/status/{task_id}.json`，本体可按需读取。

## 六、优先级调度规则

- P0：立即抢占当前任务，最高资源分配
- P1：当日队列头部，优先执行
- P2：按FIFO顺序执行
- P3：仅在资源空闲时执行，可延后至次日

---
*版本：V7.2 | 解析器：engine_v7_2/dispatch/task_parser.py*
