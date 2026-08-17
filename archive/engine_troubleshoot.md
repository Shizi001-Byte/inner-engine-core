# 九转引擎故障速查表
> 对标星卷失败修复速查表，常见问题10秒定位
> 最后更新：2026-08-18

## 一级速查（高频问题）

| 现象 | 一级排查 | 二级排查点 | 修复方法 |
|------|---------|-----------|---------|
| 引擎启动后无Worker输出 | 模型调用卡住 | 1. API格式是否chat/completions<br>2. timeout是否≥300秒<br>3. 废稿检测是否无限重试 | 单测API调用，关闭B模型废稿检测 |
| 九维计数对不上 | 计数逻辑 | 1. count是否=task+bonus<br>2. 是否漏加bonus分支<br>3. 是否重复计数 | 对照标准规则逐函数检查 |
| 调参不生效 | 热加载断点 | 1. state字段是否正确写入<br>2. 执行逻辑是否读取state<br>3. 是否有全局常量覆盖 | 先查state值，再查读取点 |
| tokens不涨 | 路由调度 | 1. force_model是否正确<br>2. select_engine返回值<br>3. 是否熔断了 | 打印路由日志确认实际模型 |
| 任务重复率高 | 任务池/权重 | 1. 任务池是否<30个<br>2. 权重是否倾斜<br>3. 去重是否生效 | 扩充任务池，调整权重 |
| 认知池只进不出 | 反哺闭环 | 1. execute_feedback是否被调用<br>2. task_weights是否被读取<br>3. concurrency_override是否生效 | 检查evolution_log是否有记录 |
| 进程自动退出 | 异常未捕获 | 1. 主循环是否有try-except<br>2. 单任务异常是否崩溃全局<br>3. 内存是否溢出 | 加全局异常保护，检查日志 |

## 模型相关

| 现象 | 原因 | 修复 |
|------|------|------|
| B模型content为空 | 用了Responses API格式 | 改用chat/completions |
| B模型推理慢 | turbo正常，pro版本才慢 | 确认型号是doubao-seed-2-1-turbo |
| B模型被判定废稿 | reasoning占比高被误杀 | B模型跳过check_waste |
| A模型满了不切B | SWITCH_THRESHOLD未触发 | 检查阈值1,600,000是否正确 |

## 计数相关标准规则

| 维度 | task_count触发 | bonus_count触发 |
|------|---------------|----------------|
| 筑基 | deep类任务 | 无 |
| 炼精 | eng类任务 | 无 |
| 养气 | exp类任务 | self_audit自审计 |
| 结丹 | cog类任务 | 无 |
| 育神 | 无 | generate_narrative每日日志 |
| 通神 | 无 | 新增认知条数 |
| 阳神 | 无 | adjust_task_weights调权 |
| 还虚 | L4成品任务 | generate_evolution_report报告 |
| 合道 | 0 | 0 |

铁则：count = task_count + bonus_count，任何加操作必须同时维护三者关系。
