"""
观尘子引擎 V7.1 - 健康检查模块
多维度健康评估，评分体系，告警机制
"""
import os
import shutil
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable


class HealthChecker:
    """健康检查器 - 多维度系统健康评估"""

    def __init__(self, config: dict, logger=None, audit_logger=None, state_manager=None):
        self.config = config
        self.logger = logger
        self.audit_logger = audit_logger
        self.state_manager = state_manager
        self.check_items = config.get("check_items", [
            "disk_space", "memory_usage", "task_queue_health",
            "sync_status", "archive_integrity", "config_validity", "log_growth",
        ])
        self.weights = config.get("weights", {
            "disk_space": 15, "memory_usage": 10, "task_queue_health": 25,
            "sync_status": 15, "archive_integrity": 20, "config_validity": 10, "log_growth": 5,
        })
        self.alert_thresholds = config.get("alert_thresholds", {
            "critical": 40, "warning": 70, "healthy": 85,
        })
        self._last_report: Optional[dict] = None
        self._custom_checks: Dict[str, Callable] = {}

    def _log(self, level: str, msg: str):
        if self.logger:
            getattr(self.logger, level)(f"[HealthChecker] {msg}")

    def register_custom_check(self, name: str, check_func: Callable, weight: int = 10):
        """注册自定义健康检查项"""
        self._custom_checks[name] = check_func
        self.weights[name] = weight
        if name not in self.check_items:
            self.check_items.append(name)
        self._log("info", f"注册自定义健康检查: {name} (权重={weight})")

    def check_disk_space(self) -> dict:
        """检查磁盘空间"""
        try:
            # 检查工作目录所在磁盘
            workspace = "/home/user/.super_doubao/super-doubao-runtime/workspace"
            usage = shutil.disk_usage(workspace)
            total_gb = usage.total / (1024 ** 3)
            used_gb = usage.used / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            usage_percent = (usage.used / usage.total) * 100

            # 评分: 使用率越低分越高
            if usage_percent < 50:
                score = 100
            elif usage_percent < 70:
                score = 80
            elif usage_percent < 85:
                score = 60
            elif usage_percent < 95:
                score = 30
            else:
                score = 10

            return {
                "name": "disk_space",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": {
                    "total_gb": round(total_gb, 2),
                    "used_gb": round(used_gb, 2),
                    "free_gb": round(free_gb, 2),
                    "usage_percent": round(usage_percent, 1),
                },
            }
        except Exception as e:
            return {"name": "disk_space", "score": 0, "status": "critical", "error": str(e)}

    def check_memory_usage(self) -> dict:
        """检查内存使用情况"""
        try:
            # 读取/proc/meminfo
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = int(parts[1].strip().split()[0])
                        meminfo[key] = value

            total = meminfo.get("MemTotal", 1)
            available = meminfo.get("MemAvailable", 0)
            used_percent = ((total - available) / total) * 100

            if used_percent < 50:
                score = 100
            elif used_percent < 70:
                score = 80
            elif used_percent < 85:
                score = 60
            elif used_percent < 95:
                score = 30
            else:
                score = 10

            return {
                "name": "memory_usage",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": {
                    "total_mb": round(total / 1024, 1),
                    "available_mb": round(available / 1024, 1),
                    "used_percent": round(used_percent, 1),
                },
            }
        except Exception as e:
            return {"name": "memory_usage", "score": 50, "status": "warning", "error": str(e)}

    def check_task_queue_health(self, scheduler=None) -> dict:
        """检查任务队列健康状态"""
        try:
            if scheduler is None:
                return {"name": "task_queue_health", "score": 70, "status": "healthy", "details": {"note": "无调度器引用"}}

            stats = scheduler.get_queue_stats()
            pending = stats.get("pending", 0)
            failed = stats.get("failed", 0)
            total = stats.get("total", 1)

            # 评分逻辑: 失败率高扣分，积压过多扣分
            failure_rate = (failed / total) * 100 if total > 0 else 0
            score = 100
            if failure_rate > 20:
                score -= 40
            elif failure_rate > 10:
                score -= 20
            if pending > 20:
                score -= 20
            elif pending > 10:
                score -= 10
            score = max(0, score)

            return {
                "name": "task_queue_health",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": stats,
            }
        except Exception as e:
            return {"name": "task_queue_health", "score": 50, "status": "warning", "error": str(e)}

    def check_sync_status(self, sync_manager=None) -> dict:
        """检查同步状态"""
        try:
            if sync_manager is None:
                return {"name": "sync_status", "score": 70, "status": "healthy", "details": {"note": "无同步管理器引用"}}
            status = sync_manager.get_status()
            last_sync = status.get("last_sync_time", "")
            pending_files = status.get("pending_files", 0)
            errors = status.get("error_count", 0)

            score = 100
            if errors > 0:
                score -= 30
            if pending_files > 10:
                score -= 20
            score = max(0, score)

            return {
                "name": "sync_status",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": status,
            }
        except Exception as e:
            return {"name": "sync_status", "score": 50, "status": "warning", "error": str(e)}

    def check_archive_integrity(self, archive_manager=None) -> dict:
        """检查档案完整性"""
        try:
            if archive_manager is None:
                return {"name": "archive_integrity", "score": 70, "status": "healthy", "details": {"note": "无档案管理器引用"}}
            integrity = archive_manager.check_integrity()
            corrupted = integrity.get("corrupted_count", 0)
            missing = integrity.get("missing_count", 0)
            total = integrity.get("total_files", 1)

            error_rate = ((corrupted + missing) / total) * 100 if total > 0 else 0
            score = max(0, 100 - int(error_rate * 2))

            return {
                "name": "archive_integrity",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": integrity,
            }
        except Exception as e:
            return {"name": "archive_integrity", "score": 50, "status": "warning", "error": str(e)}

    def check_config_validity(self, config_manager=None) -> dict:
        """检查配置有效性"""
        try:
            if config_manager is None:
                return {"name": "config_validity", "score": 80, "status": "healthy", "details": {"note": "无配置管理器引用"}}
            report = config_manager.validate()
            errors = len(report.get("errors", []))
            warnings = len(report.get("warnings", []))

            score = 100 - errors * 20 - warnings * 5
            score = max(0, score)

            return {
                "name": "config_validity",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": report,
            }
        except Exception as e:
            return {"name": "config_validity", "score": 50, "status": "warning", "error": str(e)}

    def check_log_growth(self) -> dict:
        """检查日志增长情况"""
        try:
            logs_dir = "/home/user/.super_doubao/super-doubao-runtime/workspace/engine_v7_1/logs"
            if not os.path.exists(logs_dir):
                return {"name": "log_growth", "score": 100, "status": "healthy", "details": {"note": "日志目录不存在"}}

            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(logs_dir):
                for f in files:
                    filepath = os.path.join(root, f)
                    total_size += os.path.getsize(filepath)
                    file_count += 1

            total_mb = total_size / (1024 * 1024)
            if total_mb < 50:
                score = 100
            elif total_mb < 200:
                score = 80
            elif total_mb < 500:
                score = 60
            else:
                score = 30

            return {
                "name": "log_growth",
                "score": score,
                "status": "healthy" if score >= 70 else "warning" if score >= 40 else "critical",
                "details": {"total_mb": round(total_mb, 2), "file_count": file_count},
            }
        except Exception as e:
            return {"name": "log_growth", "score": 80, "status": "healthy", "error": str(e)}

    def run_full_check(self, context: dict = None) -> dict:
        """运行完整健康检查"""
        context = context or {}
        results = []
        total_weight = 0
        weighted_score = 0

        check_map = {
            "disk_space": lambda: self.check_disk_space(),
            "memory_usage": lambda: self.check_memory_usage(),
            "task_queue_health": lambda: self.check_task_queue_health(context.get("scheduler")),
            "sync_status": lambda: self.check_sync_status(context.get("sync_manager")),
            "archive_integrity": lambda: self.check_archive_integrity(context.get("archive_manager")),
            "config_validity": lambda: self.check_config_validity(context.get("config_manager")),
            "log_growth": lambda: self.check_log_growth(),
        }

        for item in self.check_items:
            if item in check_map:
                result = check_map[item]()
            elif item in self._custom_checks:
                try:
                    result = self._custom_checks[item]()
                    result.setdefault("name", item)
                except Exception as e:
                    result = {"name": item, "score": 0, "status": "critical", "error": str(e)}
            else:
                continue

            weight = self.weights.get(item, 10)
            result["weight"] = weight
            results.append(result)
            total_weight += weight
            weighted_score += result["score"] * weight

        overall_score = int(weighted_score / total_weight) if total_weight > 0 else 0
        if overall_score >= self.alert_thresholds.get("healthy", 85):
            overall_status = "healthy"
        elif overall_score >= self.alert_thresholds.get("warning", 70):
            overall_status = "warning"
        else:
            overall_status = "critical"

        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": overall_score,
            "overall_status": overall_status,
            "total_weight": total_weight,
            "checks": results,
            "alerts": [r for r in results if r["status"] != "healthy"],
        }

        self._last_report = report

        # 更新状态管理器
        if self.state_manager:
            self.state_manager.update_health(overall_score, overall_status, report)

        # 告警审计
        if overall_status != "healthy":
            if self.audit_logger:
                self.audit_logger.log_event(
                    "health_alert",
                    {"score": overall_score, "status": overall_status, "alerts": report["alerts"]},
                )
            self._log("warning", f"健康检查告警: 评分={overall_score}, 状态={overall_status}")
        else:
            self._log("info", f"健康检查通过: 评分={overall_score}")

        return report

    def get_last_report(self) -> Optional[dict]:
        """获取最近一次健康检查报告"""
        return self._last_report

    def get_health_summary(self) -> dict:
        """获取健康状态摘要"""
        if self._last_report:
            return {
                "score": self._last_report["overall_score"],
                "status": self._last_report["overall_status"],
                "checked_at": self._last_report["timestamp"],
                "alert_count": len(self._last_report["alerts"]),
            }
        return {"score": None, "status": "unknown", "checked_at": None, "alert_count": 0}
