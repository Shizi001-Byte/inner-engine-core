#!/usr/bin/env python3
"""
观尘子引擎 V7.1 - AI 推理业务模块
封装双模型（观尘子主模型 + 星卷创作模型）的推理能力，
作为引擎标准业务模块接入调度体系。
"""

import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

from core.model_manager import (
    ModelManager, ModelConfig, ModelRole, TaskType,
)

__version__ = "1.0.0"


class AIInferenceModule:
    """AI 推理业务模块 - 双模型推理能力封装"""

    def __init__(self, config=None, logger=None, audit_logger=None, state_manager=None):
        self.config = config or {}
        self.logger = logger
        self.audit_logger = audit_logger
        self.state_manager = state_manager

        ai_config = self.config.get("ai_inference", {}) if isinstance(self.config, dict) else {}
        self.enabled = ai_config.get("enabled", True)
        self.daily_token_limit = ai_config.get("daily_token_limit", 2000000)

        self.model_manager = None
        self._lock = threading.Lock()
        self._initialized = False

    # ============================================================
    # 生命周期
    # ============================================================

    def initialize(self) -> bool:
        """初始化模型管理器"""
        if not self.enabled:
            if self.logger:
                self.logger.info("AI推理模块已禁用")
            return True

        try:
            ai_config = self.config.get("ai_inference", {}) if isinstance(self.config, dict) else {}
            models_config = ai_config.get("models", {})

            self.model_manager = ModelManager(
                daily_token_limit=self.daily_token_limit,
                state_manager=self.state_manager,
            )

            # 注册观尘子主模型
            primary_config = models_config.get("guanchenzi_primary", {})
            self.model_manager.register_model(ModelConfig(
                model_id="guanchenzi_primary",
                display_name=primary_config.get("display_name", "观尘子·工程推理"),
                role=ModelRole.PRIMARY,
                api_endpoint=primary_config.get("api_endpoint", ""),
                api_key=primary_config.get("api_key", ""),
                model_name=primary_config.get("model_name", "seed-2.1-pro"),
                temperature=primary_config.get("temperature", 0.3),
                max_tokens=primary_config.get("max_tokens", 4096),
                task_types=[
                    TaskType.ENGINEERING, TaskType.CODE_REVIEW,
                    TaskType.SYSTEM_DIAGNOSIS, TaskType.DATA_ANALYSIS,
                ],
            ))

            # 注册星卷创作模型
            creation_config = models_config.get("xingjuan_creation", {})
            self.model_manager.register_model(ModelConfig(
                model_id="xingjuan_creation",
                display_name=creation_config.get("display_name", "星卷·宇宙创作"),
                role=ModelRole.CREATION,
                api_endpoint=creation_config.get("api_endpoint", ""),
                api_key=creation_config.get("api_key", ""),
                model_name=creation_config.get("model_name", "seed-2.1-pro"),
                temperature=creation_config.get("temperature", 0.8),
                max_tokens=creation_config.get("max_tokens", 8192),
                task_types=[
                    TaskType.CREATIVE_WRITING, TaskType.WORLDBUILDING,
                    TaskType.IP_CREATION, TaskType.SCRIPT,
                ],
            ))

            self._initialized = True
            if self.logger:
                status = self.model_manager.get_status()
                self.logger.info(
                    f"AI推理模块初始化完成: {status['ready_models']}/{status['total_models']} 模型就绪"
                )
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"AI推理模块初始化失败: {e}")
            return False

    def start(self):
        """启动模块（引擎标准接口）"""
        if not self._initialized:
            self.initialize()

    def stop(self):
        """停止模块（引擎标准接口）"""
        pass

    # ============================================================
    # 引擎标准接口
    # ============================================================

    def get_task_handlers(self) -> Dict[str, Any]:
        """返回任务类型 -> 处理函数映射"""
        return {
            "ai_chat": self._handle_ai_chat,
            "ai_completion": self._handle_ai_completion,
            "ai_engineering": self._handle_engineering_task,
            "ai_creation": self._handle_creation_task,
        }

    def get_health_metrics(self) -> Dict[str, Any]:
        """返回健康检查指标"""
        if not self.model_manager:
            return {"enabled": self.enabled, "ready": False}
        status = self.model_manager.get_status()
        return {
            "enabled": self.enabled,
            "ready": status["ready_models"] > 0,
            "total_models": status["total_models"],
            "ready_models": status["ready_models"],
            "token_usage": status["token_usage"],
        }

    # ============================================================
    # 公开推理接口
    # ============================================================

    def chat(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        task_type: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        对话式推理

        Args:
            prompt: 用户提示词
            model_id: 指定模型ID，不指定则按任务类型自动选择
            task_type: 任务类型，用于自动路由
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大生成token数

        Returns:
            推理结果字典
        """
        if not self.enabled:
            return {"success": False, "error": "AI推理模块已禁用"}
        if not self.model_manager:
            return {"success": False, "error": "模型管理器未初始化"}

        # 字符串 task_type 转换为 TaskType 枚举
        task_type_enum = None
        if task_type:
            try:
                task_type_enum = TaskType(task_type)
            except ValueError:
                if self.logger:
                    self.logger.warning(f"未知任务类型 '{task_type}'，使用默认路由")

        return self.model_manager.chat(
            prompt=prompt,
            model_id=model_id,
            task_type=task_type_enum,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def completion(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        task_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """补全式推理（简化接口）"""
        return self.chat(prompt=prompt, model_id=model_id, task_type=task_type,
                         temperature=temperature, max_tokens=max_tokens)

    def get_status(self) -> Dict[str, Any]:
        """获取模块状态"""
        if not self.model_manager:
            return {"enabled": self.enabled, "initialized": False}
        return {
            "enabled": self.enabled,
            "initialized": self._initialized,
            **self.model_manager.get_status(),
        }

    def get_token_usage(self) -> Dict[str, Any]:
        """获取Token使用统计"""
        if not self.model_manager:
            return {"today_used": 0, "daily_limit": self.daily_token_limit, "remaining": self.daily_token_limit}
        return self.model_manager.get_token_usage()

    # ============================================================
    # 任务处理函数
    # ============================================================

    def _handle_ai_chat(self, task) -> Dict[str, Any]:
        """处理通用AI对话任务"""
        prompt = task.metadata.get("prompt", "")
        model_id = task.metadata.get("model_id")
        task_type = task.metadata.get("task_type")
        result = self.chat(prompt=prompt, model_id=model_id, task_type=task_type)
        return {"success": result["success"], "data": result}

    def _handle_ai_completion(self, task) -> Dict[str, Any]:
        """处理AI补全任务"""
        prompt = task.metadata.get("prompt", "")
        result = self.completion(prompt=prompt)
        return {"success": result["success"], "data": result}

    def _handle_engineering_task(self, task) -> Dict[str, Any]:
        """处理工程推理任务（自动路由到观尘子主模型）"""
        prompt = task.metadata.get("prompt", "")
        result = self.chat(prompt=prompt, task_type=TaskType.ENGINEERING)
        return {"success": result["success"], "data": result}

    def _handle_creation_task(self, task) -> Dict[str, Any]:
        """处理创作任务（自动路由到星卷创作模型）"""
        prompt = task.metadata.get("prompt", "")
        result = self.chat(prompt=prompt, task_type=TaskType.CREATIVE_WRITING)
        return {"success": result["success"], "data": result}
