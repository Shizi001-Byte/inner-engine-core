"""
观尘子引擎 V7.1 - 配置管理模块
统一管理引擎配置，支持热加载、校验、版本追踪
"""
import os
import yaml
import copy
import threading
from datetime import datetime
from typing import Any, Optional


class ConfigManager:
    """统一配置管理器 - 线程安全的单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: str = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self.config_path = config_path or (
            "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/config.yaml"
        )
        self._config = {}
        self._config_mtime = 0
        self._change_history = []
        self.load()

    def load(self) -> bool:
        """加载配置文件"""
        try:
            if not os.path.exists(self.config_path):
                return False
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            self._config_mtime = os.path.getmtime(self.config_path)
            return True
        except Exception as e:
            print(f"配置加载失败: {e}")
            return False

    def reload_if_changed(self) -> bool:
        """检测配置文件变更并热加载"""
        try:
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self._config_mtime:
                old_config = copy.deepcopy(self._config)
                if self.load():
                    self._change_history.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "action": "hot_reload",
                            "old_version": old_config.get("engine", {}).get("version"),
                            "new_version": self._config.get("engine", {}).get("version"),
                        }
                    )
                    return True
        except Exception:
            pass
        return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """按点分路径获取配置值，如 'scheduler.max_concurrent_tasks'"""
        keys = key_path.split(".")
        value = self._config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value: Any, persist: bool = False) -> bool:
        """设置配置值，可选持久化到文件"""
        keys = key_path.split(".")
        target = self._config
        try:
            for key in keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]
            old_value = target.get(keys[-1])
            target[keys[-1]] = value

            self._change_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "action": "set",
                    "key": key_path,
                    "old_value": old_value,
                    "new_value": value,
                }
            )

            if persist:
                return self.save()
            return True
        except Exception as e:
            print(f"配置设置失败: {e}")
            return False

    def save(self) -> bool:
        """保存当前配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._config,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            self._config_mtime = os.path.getmtime(self.config_path)
            return True
        except Exception as e:
            print(f"配置保存失败: {e}")
            return False

    def validate(self) -> dict:
        """校验配置完整性，返回校验报告"""
        report = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "checked_at": datetime.now().isoformat(),
        }

        required_sections = ["engine", "paths", "scheduler", "logging"]
        for section in required_sections:
            if section not in self._config:
                report["errors"].append(f"缺少必要配置段: {section}")
                report["valid"] = False

        # 校验路径存在性
        paths = self._config.get("paths", {})
        for name, path in paths.items():
            if name.endswith("_root") and not os.path.exists(path):
                report["warnings"].append(f"路径不存在: {name}={path}")

        # 校验调度器配置
        scheduler = self._config.get("scheduler", {})
        if scheduler.get("max_concurrent_tasks", 0) < 1:
            report["errors"].append("max_concurrent_tasks 必须 >= 1")
            report["valid"] = False

        return report

    def get_section(self, section: str) -> dict:
        """获取完整配置段"""
        return self._config.get(section, {})

    def get_all(self) -> dict:
        """获取完整配置（深拷贝）"""
        return copy.deepcopy(self._config)

    def get_change_history(self, limit: int = 20) -> list:
        """获取配置变更历史"""
        return self._change_history[-limit:]

    def get_version(self) -> str:
        """获取引擎版本"""
        return self._config.get("engine", {}).get("version", "unknown")
