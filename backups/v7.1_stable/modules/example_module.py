"""
观尘子引擎 V7.1 - 示例业务模块
演示如何编写可被插件加载器自动发现和加载的业务模块

模块规范:
1. 文件名即插件名（如 example_module.py -> example_module）
2. 模块级定义 __version__ 可选
3. 主类名建议与文件名对应（驼峰命名）
4. 构造函数接受 config, logger, audit_logger, state_manager 等参数
5. 可选实现 get_task_handlers() 返回任务类型到处理函数的映射
6. 可选实现 start(), stop() 生命周期方法
"""
import time
import threading
from datetime import datetime
from typing import Dict, Callable

__version__ = "1.0.0"


class ExampleModule:
    """
    示例业务模块 - 演示引擎扩展方式

    功能:
    - 定时生成示例数据
    - 提供示例任务处理器
    - 展示状态管理集成
    """

    def __init__(self, config: dict = None, logger=None, audit_logger=None, state_manager=None):
        self.config = config or {}
        self.logger = logger
        self.audit_logger = audit_logger
        self.state_manager = state_manager
        self.status = "initialized"
        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.counter = 0

        self._log("info", "示例模块已初始化")

    def _log(self, level: str, msg: str):
        if self.logger:
            getattr(self.logger, level)(f"[ExampleModule] {msg}")

    def get_task_handlers(self) -> Dict[str, Callable]:
        """
        返回任务处理器映射
        key: 任务类型字符串
        value: 处理函数，接受Task对象，返回结果字典
        """
        return {
            "example_hello": self._handle_hello,
            "example_compute": self._handle_compute,
            "example_slow": self._handle_slow_task,
        }

    def _handle_hello(self, task):
        """示例任务：打招呼"""
        name = task.metadata.get("name", "世界") if task.metadata else "世界"
        self._log("info", f"处理 hello 任务: {name}")
        return {
            "message": f"你好，{name}！",
            "timestamp": datetime.now().isoformat(),
            "module_version": __version__,
        }

    def _handle_compute(self, task):
        """示例任务：简单计算"""
        a = task.metadata.get("a", 0) if task.metadata else 0
        b = task.metadata.get("b", 0) if task.metadata else 0
        result = a + b
        self._log("info", f"计算 {a} + {b} = {result}")
        return {"a": a, "b": b, "sum": result, "product": a * b}

    def _handle_slow_task(self, task):
        """示例任务：模拟耗时操作"""
        duration = task.metadata.get("duration", 2) if task.metadata else 2
        self._log("info", f"开始耗时任务，预计 {duration} 秒")
        time.sleep(duration)
        self.counter += 1
        return {"completed": True, "duration": duration, "total_completed": self.counter}

    def start(self):
        """启动模块后台工作线程"""
        if self._running:
            return
        self._running = True
        self.status = "running"
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="example-worker"
        )
        self._worker_thread.start()
        self._log("info", "示例模块已启动")

    def stop(self):
        """停止模块"""
        self._running = False
        self.status = "stopped"
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        self._log("info", "示例模块已停止")

    def _worker_loop(self):
        """后台工作循环 - 每10秒递增计数器"""
        interval = self.config.get("worker_interval", 10)
        while not self._stop_event.is_set():
            self.counter += 1
            if self.state_manager:
                self.state_manager.set(f"custom.example_counter", self.counter)
            self._stop_event.wait(interval)
