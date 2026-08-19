"""
观尘子引擎 V7.1 - 插件加载模块
支持动态加载业务插件，热插拔，插件依赖管理
"""
import os
import sys
import importlib
import importlib.util
import json
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable


class PluginLoader:
    """插件加载器 - 动态加载和管理业务插件"""

    def __init__(self, config: dict, logger=None, audit_logger=None):
        self.config = config
        self.logger = logger
        self.audit_logger = audit_logger
        self.plugin_dirs = config.get(
            "plugin_dirs",
            [
                "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/modules",
                "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/plugins",
            ],
        )
        self.auto_load = config.get("auto_load", True)
        self.enabled_plugins = set(config.get("enabled_plugins", []))
        self._plugins: Dict[str, Any] = {}
        self._plugin_meta: Dict[str, dict] = {}
        self._lock = threading.Lock()

        # 确保插件目录在Python路径中
        for plugin_dir in self.plugin_dirs:
            if plugin_dir not in sys.path:
                sys.path.insert(0, os.path.dirname(plugin_dir))

    def _log(self, level: str, msg: str):
        if self.logger:
            getattr(self.logger, level)(f"[PluginLoader] {msg}")

    def _audit(self, event_type: str, details: dict):
        if self.audit_logger:
            self.audit_logger.log_event(event_type, details)

    def discover_plugins(self) -> list:
        """扫描插件目录，发现可用插件"""
        discovered = []
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                continue
            for item in os.listdir(plugin_dir):
                item_path = os.path.join(plugin_dir, item)
                # Python模块插件
                if item.endswith(".py") and not item.startswith("_"):
                    plugin_name = item[:-3]
                    discovered.append({
                        "name": plugin_name,
                        "path": item_path,
                        "type": "module",
                    })
                # 包插件（含__init__.py的目录）
                elif os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
                    plugin_name = item
                    discovered.append({
                        "name": plugin_name,
                        "path": item_path,
                        "type": "package",
                    })
        return discovered

    def load_plugin(self, plugin_name: str, plugin_path: str = None) -> bool:
        """加载单个插件"""
        with self._lock:
            if plugin_name in self._plugins:
                self._log("warning", f"插件已加载: {plugin_name}")
                return True

            # 如果指定了路径，使用动态导入
            if plugin_path:
                try:
                    if os.path.isfile(plugin_path):
                        spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                    else:
                        module = importlib.import_module(plugin_name)
                except Exception as e:
                    self._log("error", f"插件加载失败 {plugin_name}: {e}")
                    return False
            else:
                try:
                    module = importlib.import_module(f"engine_v7_1.modules.{plugin_name}")
                except ImportError:
                    try:
                        module = importlib.import_module(plugin_name)
                    except Exception as e:
                        self._log("error", f"插件导入失败 {plugin_name}: {e}")
                        return False

            # 提取插件元信息
            meta = {
                "name": plugin_name,
                "loaded_at": datetime.now().isoformat(),
                "version": getattr(module, "__version__", "unknown"),
                "description": getattr(module, "__doc__", "").strip()[:200] if module.__doc__ else "",
                "exports": [x for x in dir(module) if not x.startswith("_")],
            }

            self._plugins[plugin_name] = module
            self._plugin_meta[plugin_name] = meta
            self._audit("plugin_load", {"name": plugin_name, "version": meta["version"]})
            self._log("info", f"插件已加载: {plugin_name} v{meta['version']}")
            return True

    def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件"""
        with self._lock:
            if plugin_name not in self._plugins:
                return False
            del self._plugins[plugin_name]
            del self._plugin_meta[plugin_name]
            # 从sys.modules中移除（尝试）
            for key in list(sys.modules.keys()):
                if key == plugin_name or key.startswith(f"{plugin_name}."):
                    del sys.modules[key]
            self._log("info", f"插件已卸载: {plugin_name}")
            return True

    def reload_plugin(self, plugin_name: str) -> bool:
        """重新加载插件"""
        if plugin_name in self._plugins:
            self.unload_plugin(plugin_name)
        return self.load_plugin(plugin_name)

    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """获取已加载的插件模块"""
        return self._plugins.get(plugin_name)

    def get_plugin_class(self, plugin_name: str, class_name: str = None) -> Optional[type]:
        """获取插件中的类"""
        module = self._plugins.get(plugin_name)
        if module is None:
            return None
        if class_name is None:
            # 尝试查找默认类名（插件名首字母大写 + 常见后缀）
            candidates = [
                plugin_name,
                plugin_name.capitalize(),
                plugin_name.replace("_", " ").title().replace(" ", ""),
            ]
            for candidate in candidates:
                if hasattr(module, candidate):
                    attr = getattr(module, candidate)
                    if isinstance(attr, type):
                        return attr
            return None
        return getattr(module, class_name, None)

    def instantiate_plugin(self, plugin_name: str, class_name: str = None, **kwargs) -> Optional[Any]:
        """实例化插件类"""
        cls = self.get_plugin_class(plugin_name, class_name)
        if cls is None:
            self._log("error", f"未找到插件类: {plugin_name}.{class_name or '?'}")
            return None
        try:
            return cls(**kwargs)
        except Exception as e:
            self._log("error", f"插件实例化失败 {plugin_name}: {e}")
            return None

    def load_all(self) -> dict:
        """加载所有启用的插件"""
        results = {"loaded": [], "failed": [], "skipped": []}
        discovered = self.discover_plugins()

        for plugin_info in discovered:
            name = plugin_info["name"]
            # 检查是否启用
            if self.enabled_plugins and name not in self.enabled_plugins:
                results["skipped"].append(name)
                continue
            if self.load_plugin(name, plugin_info["path"]):
                results["loaded"].append(name)
            else:
                results["failed"].append(name)

        self._log("info", f"插件加载完成: 成功={len(results['loaded'])}, 失败={len(results['failed'])}, 跳过={len(results['skipped'])}")
        return results

    def get_loaded_plugins(self) -> list:
        """获取已加载插件列表"""
        return list(self._plugins.keys())

    def get_plugin_info(self, plugin_name: str) -> Optional[dict]:
        """获取插件元信息"""
        return self._plugin_meta.get(plugin_name)

    def get_all_info(self) -> list:
        """获取所有已加载插件的元信息"""
        return list(self._plugin_meta.values())
