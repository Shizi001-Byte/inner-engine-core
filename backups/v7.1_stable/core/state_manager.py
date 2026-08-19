"""
观尘子引擎 V7.1 - 状态管理模块
持久化引擎运行状态，支持快照、恢复、历史追踪
"""
import json
import os
import copy
import threading
from datetime import datetime
from typing import Any, Optional


class StateManager:
    """状态管理器 - 线程安全的持久化状态存储"""

    def __init__(self, config: dict, logger=None):
        self.config = config
        self.logger = logger
        self.state_file = config.get(
            "state_file",
            "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/data/engine_state.json",
        )
        self.history_file = config.get(
            "history_file",
            "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/data/state_history.json",
        )
        self.max_history = config.get("max_history_entries", 100)
        self._lock = threading.Lock()
        self._state: dict = {}
        self._load_state()

    def _log(self, level: str, msg: str):
        if self.logger:
            getattr(self.logger, level)(f"[StateManager] {msg}")

    def _load_state(self):
        """从文件加载状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            else:
                self._state = self._default_state()
                self._save_state()
        except Exception as e:
            self._log("error", f"状态加载失败: {e}")
            self._state = self._default_state()

    def _default_state(self) -> dict:
        """默认状态结构"""
        return {
            "engine": {
                "version": "7.1.0",
                "started_at": None,
                "last_heartbeat": None,
                "uptime_seconds": 0,
                "total_tasks_processed": 0,
                "total_tokens_used": 0,
            },
            "health": {
                "score": None,
                "status": "unknown",
                "last_check": None,
                "last_report": None,
            },
            "scheduler": {
                "is_running": False,
                "last_task_id": None,
                "last_task_time": None,
            },
            "sync": {
                "last_sync_time": None,
                "last_sync_result": None,
                "pending_files": 0,
            },
            "archive": {
                "last_scan_time": None,
                "total_files": 0,
                "last_integrity_check": None,
            },
            "cognition_qc": {
                "last_run": None,
                "total_checked": 0,
                "pass_rate": None,
            },
            "custom": {},
        }

    def _save_state(self):
        """保存状态到文件"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log("error", f"状态保存失败: {e}")

    def _append_history(self, section: str, old_value: Any, new_value: Any):
        """追加状态变更历史"""
        try:
            history = []
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)

            history.append({
                "timestamp": datetime.now().isoformat(),
                "section": section,
                "old_value": old_value,
                "new_value": new_value,
            })

            # 限制历史长度
            if len(history) > self.max_history:
                history = history[-self.max_history:]

            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log("warning", f"状态历史写入失败: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """获取状态值"""
        keys = key_path.split(".")
        value = self._state
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value: Any, track_history: bool = True):
        """设置状态值"""
        with self._lock:
            keys = key_path.split(".")
            target = self._state
            try:
                for key in keys[:-1]:
                    if key not in target:
                        target[key] = {}
                    target = target[key]

                old_value = target.get(keys[-1])
                target[keys[-1]] = value

                if track_history and old_value != value:
                    self._append_history(key_path, old_value, value)

                self._save_state()
            except Exception as e:
                self._log("error", f"状态设置失败: {e}")

    def update_health(self, score: int, status: str, report: dict):
        """更新健康状态"""
        self.set("health.score", score)
        self.set("health.status", status)
        self.set("health.last_check", datetime.now().isoformat())
        self.set("health.last_report", report, track_history=False)

    def update_scheduler(self, is_running: bool = None, last_task_id: str = None):
        """更新调度器状态"""
        if is_running is not None:
            self.set("scheduler.is_running", is_running)
        if last_task_id is not None:
            self.set("scheduler.last_task_id", last_task_id)
            self.set("scheduler.last_task_time", datetime.now().isoformat())

    def update_sync(self, result: dict = None, pending_files: int = None):
        """更新同步状态"""
        self.set("sync.last_sync_time", datetime.now().isoformat())
        if result is not None:
            self.set("sync.last_sync_result", result, track_history=False)
        if pending_files is not None:
            self.set("sync.pending_files", pending_files)

    def update_archive(self, total_files: int = None, integrity_result: dict = None):
        """更新档案状态"""
        self.set("archive.last_scan_time", datetime.now().isoformat())
        if total_files is not None:
            self.set("archive.total_files", total_files)
        if integrity_result is not None:
            self.set("archive.last_integrity_check", integrity_result, track_history=False)

    def update_cognition_qc(self, total_checked: int, pass_rate: float):
        """更新认知质检状态"""
        self.set("cognition_qc.last_run", datetime.now().isoformat())
        self.set("cognition_qc.total_checked", total_checked)
        self.set("cognition_qc.pass_rate", pass_rate)

    def heartbeat(self):
        """心跳更新"""
        self.set("engine.last_heartbeat", datetime.now().isoformat(), track_history=False)

    def mark_engine_start(self):
        """标记引擎启动"""
        self.set("engine.started_at", datetime.now().isoformat())
        self.set("engine.last_heartbeat", datetime.now().isoformat(), track_history=False)

    def increment_task_count(self, tokens: int = 0):
        """递增任务计数"""
        with self._lock:
            current = self._state.get("engine", {}).get("total_tasks_processed", 0)
            self._state["engine"]["total_tasks_processed"] = current + 1
            if tokens > 0:
                current_tokens = self._state.get("engine", {}).get("total_tokens_used", 0)
                self._state["engine"]["total_tokens_used"] = current_tokens + tokens
            self._save_state()

    def get_snapshot(self) -> dict:
        """获取当前状态快照（深拷贝）"""
        return copy.deepcopy(self._state)

    def get_history(self, section: str = None, limit: int = 20) -> list:
        """获取状态变更历史"""
        try:
            if not os.path.exists(self.history_file):
                return []
            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            if section:
                history = [h for h in history if h.get("section", "").startswith(section)]
            return history[-limit:]
        except Exception:
            return []

    def reset(self):
        """重置状态到默认值"""
        with self._lock:
            self._state = self._default_state()
            self._save_state()
            self._log("info", "状态已重置")
