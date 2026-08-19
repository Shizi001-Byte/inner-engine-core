"""
观尘子引擎 V7.1 - 任务调度器模块
兼容V7.0任务队列格式，支持优先级、重试、并发控制、任务生命周期管理
"""
import json
import os
import uuid
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(int, Enum):
    """任务优先级枚举 - 数值越小优先级越高"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM_HIGH = 3
    MEDIUM = 5
    MEDIUM_LOW = 7
    LOW = 9


@dataclass
class Task:
    """任务数据结构 - 兼容V7.0格式并扩展"""
    id: str = ""
    type: str = "custom"
    target: str = ""
    name: str = ""
    description: str = ""
    priority: int = 5
    status: str = "pending"
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    # V7.0兼容字段
    size: int = 0
    md5: str = ""
    gene_passed: bool = False
    result: Any = None
    tokens: int = 0
    # V7.1扩展字段
    retries: int = 0
    max_retries: int = 3
    timeout_seconds: int = 3600
    error_message: str = ""
    progress: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    callback: Optional[str] = None  # 回调函数标识

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """转换为字典（用于序列化）"""
        d = asdict(self)
        # 移除不可序列化的回调
        d.pop("callback", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """从字典创建任务实例"""
        # 过滤未知字段
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class TaskScheduler:
    """任务调度器 - 线程安全的任务队列管理"""

    def __init__(self, config: dict, logger=None, audit_logger=None):
        self.config = config
        self.logger = logger
        self.audit_logger = audit_logger
        self.queue_file = config.get(
            "task_queue_file",
            "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/data/task_queue.json",
        )
        self.max_concurrent = config.get("max_concurrent_tasks", 3)
        self.default_priority = config.get("default_priority", 5)
        self.max_retries = config.get("max_retries", 3)
        self.cooldown = config.get("cooldown_seconds", 10)
        self.allowed_types = set(config.get("allowed_task_types", ["custom"]))

        self._lock = threading.Lock()
        self._tasks: Dict[str, Task] = {}
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        self._load_queue()

    def _log(self, level: str, msg: str):
        if self.logger:
            getattr(self.logger, level)(f"[TaskScheduler] {msg}")

    def _audit(self, event_type: str, details: dict):
        if self.audit_logger:
            self.audit_logger.log_event(event_type, details)

    def _load_queue(self):
        """从文件加载任务队列"""
        try:
            if not os.path.exists(self.queue_file):
                self._save_queue()
                return
            with open(self.queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 兼容V7.0格式: {pending: [...], completed: [...]}
            if isinstance(data, dict) and "pending" in data:
                for t_data in data.get("pending", []):
                    task = Task.from_dict(t_data)
                    task.status = TaskStatus.PENDING.value
                    self._tasks[task.id] = task
                for t_data in data.get("completed", []):
                    task = Task.from_dict(t_data)
                    task.status = TaskStatus.COMPLETED.value
                    self._tasks[task.id] = task
            elif isinstance(data, list):
                for t_data in data:
                    task = Task.from_dict(t_data)
                    self._tasks[task.id] = task
            self._log("info", f"加载任务队列: {len(self._tasks)} 个任务")
        except Exception as e:
            self._log("error", f"任务队列加载失败: {e}")

    def _save_queue(self):
        """保存任务队列到文件"""
        try:
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            # 按V7.0兼容格式保存
            pending = [
                t.to_dict()
                for t in self._tasks.values()
                if t.status in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value, TaskStatus.RETRYING.value)
            ]
            completed = [
                t.to_dict()
                for t in self._tasks.values()
                if t.status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value)
            ]
            data = {"pending": pending, "completed": completed}
            with open(self.queue_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log("error", f"任务队列保存失败: {e}")

    def register_handler(self, task_type: str, handler: Callable):
        """注册任务类型处理器"""
        self._handlers[task_type] = handler
        self._log("info", f"注册任务处理器: {task_type}")

    def submit_task(
        self,
        task_type: str,
        name: str = "",
        target: str = "",
        priority: int = None,
        metadata: dict = None,
        description: str = "",
        tags: list = None,
    ) -> Task:
        """提交新任务"""
        if task_type not in self.allowed_types and task_type != "custom":
            self._log("warning", f"任务类型未在白名单中: {task_type}")

        task = Task(
            type=task_type,
            name=name or f"{task_type}_{datetime.now().strftime('%H%M%S')}",
            target=target,
            priority=priority if priority is not None else self.default_priority,
            description=description,
            metadata=metadata or {},
            tags=tags or [],
            max_retries=self.max_retries,
        )

        with self._lock:
            self._tasks[task.id] = task
            self._save_queue()

        self._audit("task_start", {"task_id": task.id, "type": task_type, "name": task.name})
        self._log("info", f"任务已提交: {task.id} [{task_type}] {task.name}")
        return task

    def get_next_task(self) -> Optional[Task]:
        """获取下一个待执行任务（按优先级排序）"""
        with self._lock:
            pending = [
                t for t in self._tasks.values() if t.status == TaskStatus.PENDING.value
            ]
            if not pending:
                return None
            # 按优先级排序（数值小优先），同优先级按创建时间
            pending.sort(key=lambda t: (t.priority, t.created_at))
            return pending[0]

    def execute_task(self, task: Task) -> bool:
        """执行单个任务"""
        handler = self._handlers.get(task.type)
        if handler is None:
            self._log("warning", f"无处理器的任务类型: {task.type}, 任务标记为失败")
            task.status = TaskStatus.FAILED.value
            task.error_message = f"无处理器: {task.type}"
            task.completed_at = datetime.now().isoformat()
            self._save_queue()
            return False

        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.now().isoformat()
        self._save_queue()

        try:
            self._log("info", f"开始执行任务: {task.id} [{task.type}]")
            result = handler(task)
            task.status = TaskStatus.COMPLETED.value
            task.result = result
            task.progress = 100.0
            task.completed_at = datetime.now().isoformat()
            self._audit("task_complete", {"task_id": task.id, "type": task.type})
            self._log("info", f"任务完成: {task.id}")
            self._save_queue()
            return True
        except Exception as e:
            task.retries += 1
            task.error_message = str(e)
            if task.retries < task.max_retries:
                task.status = TaskStatus.RETRYING.value
                self._log("warning", f"任务失败，将重试({task.retries}/{task.max_retries}): {task.id} - {e}")
                # 重试任务重新入队
                task.status = TaskStatus.PENDING.value
            else:
                task.status = TaskStatus.FAILED.value
                task.completed_at = datetime.now().isoformat()
                self._audit("task_failed", {"task_id": task.id, "type": task.type, "error": str(e)})
                self._log("error", f"任务最终失败: {task.id} - {e}")
            self._save_queue()
            return False

    def run_forever(self, blocking: bool = False):
        """启动调度器主循环"""
        self._running = True

        def _worker():
            self._log("info", "任务调度器已启动")
            while self._running:
                try:
                    task = self.get_next_task()
                    if task:
                        self.execute_task(task)
                    else:
                        time.sleep(self.cooldown)
                except Exception as e:
                    self._log("error", f"调度器循环异常: {e}")
                    time.sleep(self.cooldown)
            self._log("info", "任务调度器已停止")

        if blocking:
            _worker()
        else:
            self._worker_thread = threading.Thread(target=_worker, daemon=True)
            self._worker_thread.start()

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING.value:
                task.status = TaskStatus.CANCELLED.value
                task.completed_at = datetime.now().isoformat()
                self._save_queue()
                self._log("info", f"任务已取消: {task_id}")
                return True
        return False

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        return self._tasks.get(task_id)

    def get_tasks_by_status(self, status: str) -> List[Task]:
        """按状态获取任务列表"""
        return [t for t in self._tasks.values() if t.status == status]

    def get_queue_stats(self) -> dict:
        """获取队列统计信息"""
        stats = {
            "total": len(self._tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "retrying": 0,
            "by_type": {},
        }
        for task in self._tasks.values():
            status = task.status
            if status in stats:
                stats[status] += 1
            stats["by_type"][task.type] = stats["by_type"].get(task.type, 0) + 1
        return stats

    def cleanup_completed(self, older_than_hours: int = 72) -> int:
        """清理已完成的旧任务"""
        cutoff = time.time() - older_than_hours * 3600
        removed = 0
        with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
                    if task.completed_at:
                        try:
                            completed_time = datetime.fromisoformat(task.completed_at).timestamp()
                            if completed_time < cutoff:
                                to_remove.append(task_id)
                        except ValueError:
                            continue
            for task_id in to_remove:
                del self._tasks[task_id]
                removed += 1
            if removed > 0:
                self._save_queue()
        self._log("info", f"清理旧任务: {removed} 个")
        return removed
