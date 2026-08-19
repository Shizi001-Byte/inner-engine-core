"""
观尘子引擎 V7.1 - 主引擎类
统一入口，整合所有核心模块与业务插件，提供完整的引擎生命周期管理
"""
import os
import sys
import json
import signal
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

# 确保项目根目录在路径中
_ENGINE_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from core.config_manager import ConfigManager
from core.task_scheduler import TaskScheduler, Task, TaskStatus
from core.health_checker import HealthChecker
from core.state_manager import StateManager
from core.plugin_loader import PluginLoader
from modules.ai_inference_module import AIInferenceModule
from utils.logger import EngineLogger, AuditLogger


class EngineV71:
    """
    观尘子引擎 V7.1 主类

    架构:
    - 决策层: 本类，负责整体调度与生命周期管理
    - 执行层: TaskScheduler + 各业务插件
    - 基础设施层: ConfigManager, StateManager, Logger, AuditLogger
    - 监控层: HealthChecker

    使用方式:
        engine = EngineV71()
        engine.initialize()
        engine.start()
        # 提交任务
        engine.submit_task("custom", name="测试任务")
        # 获取状态
        status = engine.get_status()
        engine.stop()
    """

    VERSION = "7.1.0"
    ENGINE_NAME = "观尘子引擎"

    def __init__(self, config_path: str = None, config: dict = None):
        """
        初始化引擎

        Args:
            config_path: 配置文件路径
            config: 直接传入配置字典（优先级高于config_path）
        """
        self._initialized = False
        self._running = False
        self._lock = threading.Lock()

        # 加载配置
        if config:
            self.config_manager = ConfigManager(config_dict=config)
        else:
            self.config_manager = ConfigManager(config_path=config_path)
        self.config = self.config_manager.get_all()

        # 初始化基础设施
        self._init_infrastructure()

        # 核心模块（延迟初始化）
        self.state_manager: Optional[StateManager] = None
        self.task_scheduler: Optional[TaskScheduler] = None
        self.health_checker: Optional[HealthChecker] = None
        self.plugin_loader: Optional[PluginLoader] = None

        # 业务插件实例
        self.modules: Dict[str, Any] = {}
        # AI 推理模块（内置核心模块）
        self.ai_inference: Optional[AIInferenceModule] = None

        # 后台线程
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.logger.info(f"{self.ENGINE_NAME} V{self.VERSION} 实例已创建")

    def _init_infrastructure(self):
        """初始化基础设施（日志、审计）"""
        log_config = self.config.get("logging", {})
        self.engine_logger = EngineLogger(config=log_config)
        self.logger = self.engine_logger.get_logger("engine")
        self.audit_logger = self.engine_logger.audit_logger

    def initialize(self) -> bool:
        """
        初始化引擎所有模块

        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            self.logger.warning("引擎已初始化，跳过重复初始化")
            return True

        self.logger.info("=" * 60)
        self.logger.info(f"{self.ENGINE_NAME} V{self.VERSION} 开始初始化")
        self.logger.info("=" * 60)

        try:
            # 1. 状态管理器
            self.state_manager = StateManager(
                self.config.get("state", {}), logger=self.logger
            )
            self.logger.info("状态管理器初始化完成")

            # 2. 任务调度器
            self.task_scheduler = TaskScheduler(
                self.config.get("scheduler", {}),
                logger=self.logger,
                audit_logger=self.audit_logger,
            )
            self.logger.info("任务调度器初始化完成")

            # 3. 健康检查器
            self.health_checker = HealthChecker(
                self.config.get("health_check", {}),
                logger=self.logger,
                audit_logger=self.audit_logger,
                state_manager=self.state_manager,
            )
            self.logger.info("健康检查器初始化完成")

            # 4. 插件加载器
            self.plugin_loader = PluginLoader(
                self.config.get("plugins", {}),
                logger=self.logger,
                audit_logger=self.audit_logger,
            )
            self.logger.info("插件加载器初始化完成")

            # 5. 加载业务插件
            self._load_business_modules()

            # 6. 注册默认任务处理器
            self._register_default_handlers()

            self._initialized = True
            self.state_manager.mark_engine_start()
            self.audit_logger.log_event("engine_init", {"version": self.VERSION})
            self.logger.info(f"{self.ENGINE_NAME} 初始化完成")
            return True

        except Exception as e:
            self.logger.error(f"引擎初始化失败: {e}", exc_info=True)
            self.audit_logger.log_event("engine_init_failed", {"error": str(e)})
            return False

    def _load_business_modules(self):
        """加载业务模块插件"""
        # 0. 先加载内置 AI 推理模块（双模型）
        ai_cfg = self.config.get("ai_inference", {})
        if ai_cfg.get("enabled", True):
            self.ai_inference = AIInferenceModule(config=ai_cfg)
            if self.ai_inference.initialize():
                self.modules["ai_inference"] = self.ai_inference
                self.logger.info("内置AI推理模块（双模型）加载完成")
            else:
                self.logger.warning("AI推理模块初始化失败，将以降级模式运行")
        else:
            self.logger.info("AI推理模块已在配置中禁用")

        # 1. 插件加载器扫描外部模块
        module_configs = self.config.get("modules", {})
        loaded = self.plugin_loader.load_all()

        for plugin_name in loaded.get("loaded", []):
            module_config = module_configs.get(plugin_name, {})
            if not module_config.get("enabled", True):
                continue

            # 尝试实例化模块主类
            instance = self.plugin_loader.instantiate_plugin(
                plugin_name,
                config=module_config,
                logger=self.logger,
                audit_logger=self.audit_logger,
                state_manager=self.state_manager,
            )
            if instance is not None:
                self.modules[plugin_name] = instance
                self.logger.info(f"业务模块已实例化: {plugin_name}")

                # 注册模块的任务处理器
                if hasattr(instance, "get_task_handlers"):
                    handlers = instance.get_task_handlers()
                    for task_type, handler in handlers.items():
                        self.task_scheduler.register_handler(task_type, handler)
                        self.logger.info(f"  注册任务处理器: {task_type}")

    def _register_default_handlers(self):
        """注册默认任务处理器"""
        # 自定义任务处理器（直接执行metadata中的callable或记录）
        def custom_handler(task: Task):
            self.logger.info(f"执行自定义任务: {task.name}")
            return {"status": "completed", "task_id": task.id}

        self.task_scheduler.register_handler("custom", custom_handler)

        # 健康检查任务
        def health_check_handler(task: Task):
            context = {
                "scheduler": self.task_scheduler,
                "config_manager": self.config_manager,
            }
            return self.health_checker.run_full_check(context)

        self.task_scheduler.register_handler("health_check", health_check_handler)

        # 状态报告任务
        def status_report_handler(task: Task):
            return self.get_status()

        self.task_scheduler.register_handler("status_report", status_report_handler)

    def start(self) -> bool:
        """
        启动引擎

        Returns:
            bool: 启动是否成功
        """
        if not self._initialized:
            self.logger.error("引擎未初始化，无法启动")
            return False

        if self._running:
            self.logger.warning("引擎已在运行中")
            return True

        self.logger.info("=" * 60)
        self.logger.info(f"{self.ENGINE_NAME} V{self.VERSION} 启动")
        self.logger.info("=" * 60)

        try:
            self._running = True
            self._stop_event.clear()

            # 启动任务调度器
            self.task_scheduler.run_forever(blocking=False)
            self.state_manager.update_scheduler(is_running=True)

            # 启动心跳线程
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True, name="engine-heartbeat"
            )
            self._heartbeat_thread.start()

            # 启动健康检查线程
            health_interval = self.config.get("health_check", {}).get("check_interval_seconds", 300)
            self._health_thread = threading.Thread(
                target=self._health_check_loop,
                args=(health_interval,),
                daemon=True,
                name="engine-health",
            )
            self._health_thread.start()

            self.audit_logger.log_event("engine_start", {"version": self.VERSION})
            self.logger.info(f"{self.ENGINE_NAME} 已启动，心跳间隔=30s, 健康检查间隔={health_interval}s")
            return True

        except Exception as e:
            self.logger.error(f"引擎启动失败: {e}", exc_info=True)
            self._running = False
            return False

    def stop(self, graceful: bool = True):
        """
        停止引擎

        Args:
            graceful: 是否优雅停止（等待当前任务完成）
        """
        if not self._running:
            return

        self.logger.info(f"{self.ENGINE_NAME} 正在停止...")
        self._stop_event.set()
        self._running = False

        # 停止调度器
        if self.task_scheduler:
            self.task_scheduler.stop()
            self.state_manager.update_scheduler(is_running=False)

        # 等待后台线程
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=10)

        # 停止业务模块
        for name, module in self.modules.items():
            if hasattr(module, "stop"):
                try:
                    module.stop()
                except Exception as e:
                    self.logger.warning(f"模块停止异常 {name}: {e}")

        self.audit_logger.log_event("engine_stop", {"graceful": graceful})
        self.logger.info(f"{self.ENGINE_NAME} 已停止")

    def _heartbeat_loop(self):
        """心跳循环"""
        interval = self.config.get("heartbeat_interval_seconds", 30)
        while not self._stop_event.is_set():
            try:
                self.state_manager.heartbeat()
            except Exception as e:
                self.logger.warning(f"心跳更新失败: {e}")
            self._stop_event.wait(interval)

    def _health_check_loop(self, interval: int):
        """健康检查循环"""
        # 启动时先做一次检查
        time.sleep(5)
        while not self._stop_event.is_set():
            try:
                context = {
                    "scheduler": self.task_scheduler,
                    "config_manager": self.config_manager,
                }
                self.health_checker.run_full_check(context)
            except Exception as e:
                self.logger.warning(f"健康检查异常: {e}")
            self._stop_event.wait(interval)

    def submit_task(
        self,
        task_type: str,
        name: str = "",
        target: str = "",
        priority: int = None,
        metadata: dict = None,
        description: str = "",
        tags: list = None,
    ) -> Optional[Task]:
        """
        提交任务到调度器

        Args:
            task_type: 任务类型
            name: 任务名称
            target: 任务目标
            priority: 优先级（1-9，越小越高）
            metadata: 元数据
            description: 描述
            tags: 标签

        Returns:
            Task: 任务对象，失败返回None
        """
        if not self._initialized:
            self.logger.error("引擎未初始化")
            return None

        return self.task_scheduler.submit_task(
            task_type=task_type,
            name=name,
            target=target,
            priority=priority,
            metadata=metadata,
            description=description,
            tags=tags,
        )

    def get_status(self) -> dict:
        """获取引擎完整状态"""
        if not self._initialized:
            return {"status": "not_initialized", "version": self.VERSION}

        state = self.state_manager.get_snapshot()
        queue_stats = self.task_scheduler.get_queue_stats() if self.task_scheduler else {}
        health = self.health_checker.get_health_summary() if self.health_checker else {}
        modules_info = {}
        for name, module in self.modules.items():
            modules_info[name] = {
                "version": getattr(module, "__version__", "unknown"),
                "status": getattr(module, "status", "unknown"),
            }

        return {
            "engine": {
                "name": self.ENGINE_NAME,
                "version": self.VERSION,
                "running": self._running,
                "initialized": self._initialized,
            },
            "state": state,
            "task_queue": queue_stats,
            "health": health,
            "modules": modules_info,
            "loaded_plugins": self.plugin_loader.get_loaded_plugins() if self.plugin_loader else [],
        }

    def run_health_check(self) -> dict:
        """手动触发健康检查"""
        if not self.health_checker:
            return {"error": "健康检查器未初始化"}
        context = {
            "scheduler": self.task_scheduler,
            "config_manager": self.config_manager,
        }
        return self.health_checker.run_full_check(context)

    def get_module(self, module_name: str) -> Optional[Any]:
        """获取业务模块实例"""
        return self.modules.get(module_name)

    def reload_config(self) -> bool:
        """热重载配置"""
        try:
            self.config_manager.reload_if_changed()
            self.config = self.config_manager.get_all()
            self.audit_logger.log_event("config_reload", {})
            self.logger.info("配置已热重载")
            return True
        except Exception as e:
            self.logger.error(f"配置重载失败: {e}")
            return False

    def cleanup(self, older_than_hours: int = 72) -> dict:
        """清理引擎数据"""
        results = {}
        if self.task_scheduler:
            results["tasks_cleaned"] = self.task_scheduler.cleanup_completed(older_than_hours)
        # 日志轮转
        self.logger.info(f"引擎清理完成: {results}")
        return results


# ============== 便捷函数 ==============

def create_engine(config_path: str = None) -> EngineV71:
    """创建并初始化引擎实例"""
    engine = EngineV71(config_path=config_path)
    engine.initialize()
    return engine


def run_engine_forever(config_path: str = None):
    """以守护模式运行引擎"""
    engine = create_engine(config_path)
    engine.start()

    # 注册信号处理
    def signal_handler(signum, frame):
        print(f"\n收到信号 {signum}，正在停止引擎...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"{EngineV71.ENGINE_NAME} V{EngineV71.VERSION} 已启动，按 Ctrl+C 停止")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop()


if __name__ == "__main__":
    run_engine_forever()
