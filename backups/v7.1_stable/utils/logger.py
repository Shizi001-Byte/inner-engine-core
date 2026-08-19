"""
观尘子引擎 V7.1 - 日志与审计模块
提供统一的日志记录和审计追踪功能
"""
import logging
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


class EngineLogger:
    """统一日志管理器"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config=None):
        if self._initialized:
            return
        self._initialized = True
        self.config = config or {}
        self._setup_logger()

    def _setup_logger(self):
        """配置日志系统"""
        log_level = self.config.get("level", "INFO")
        log_file = self.config.get(
            "log_file",
            "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/logs/engine.log",
        )
        max_size = self.config.get("max_file_size_mb", 50) * 1024 * 1024
        backup_count = self.config.get("backup_count", 5)
        fmt = self.config.get(
            "format",
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        )

        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # 根日志器
        self.root_logger = logging.getLogger("guanchenzi_engine")
        self.root_logger.setLevel(getattr(logging, log_level, logging.INFO))
        self.root_logger.handlers.clear()

        # 文件处理器
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_size, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(fmt))
        self.root_logger.addHandler(file_handler)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(fmt))
        self.root_logger.addHandler(console_handler)

        self.audit_logger = AuditLogger(self.config)

    def get_logger(self, name: str) -> logging.Logger:
        """获取子模块日志器"""
        return self.root_logger.getChild(name)

    def debug(self, msg: str, **kwargs):
        self.root_logger.debug(msg, extra=kwargs)

    def info(self, msg: str, **kwargs):
        self.root_logger.info(msg, extra=kwargs)

    def warning(self, msg: str, **kwargs):
        self.root_logger.warning(msg, extra=kwargs)

    def error(self, msg: str, **kwargs):
        self.root_logger.error(msg, extra=kwargs)

    def critical(self, msg: str, **kwargs):
        self.root_logger.critical(msg, extra=kwargs)


class AuditLogger:
    """审计日志记录器 - 记录关键操作事件"""

    def __init__(self, config=None):
        self.config = config or {}
        self.audit_file = self.config.get(
            "audit_log",
            "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/logs/audit.log",
        )
        self.audit_events = set(
            self.config.get(
                "audit_events",
                [
                    "task_start",
                    "task_complete",
                    "task_failed",
                    "config_change",
                    "plugin_load",
                    "sync_event",
                    "archive_event",
                    "qc_result",
                    "health_alert",
                    "engine_start",
                    "engine_stop",
                ],
            )
        )
        os.makedirs(os.path.dirname(self.audit_file), exist_ok=True)

    def log_event(self, event_type: str, details: dict, actor: str = "engine"):
        """记录审计事件"""
        if event_type not in self.audit_events:
            return

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "actor": actor,
            "details": details,
        }

        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.getLogger("guanchenzi_engine").error(
                f"审计日志写入失败: {e}"
            )

    def get_recent_events(self, event_type: str = None, limit: int = 50) -> list:
        """获取最近的审计事件"""
        events = []
        try:
            if not os.path.exists(self.audit_file):
                return events
            with open(self.audit_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines[-limit * 2 :]):
                try:
                    entry = json.loads(line.strip())
                    if event_type is None or entry.get("event_type") == event_type:
                        events.append(entry)
                    if len(events) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logging.getLogger("guanchenzi_engine").error(
                f"审计日志读取失败: {e}"
            )
        return events
