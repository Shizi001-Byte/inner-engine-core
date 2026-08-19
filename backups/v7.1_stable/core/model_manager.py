#!/usr/bin/env python3
"""
观尘子引擎 V7.1 - 双模型管理层
管理两个AI推理模型：
  - 观尘子主模型：工程推理、代码开发、系统诊断（理性、精确）
  - 星卷创作模型：星空IP创作、史诗叙事、世界观构建（感性、创意）
提供智能路由、降级切换、Token额度管控。
"""

import json
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field


# ============================================================
# 枚举与数据类
# ============================================================

class ModelRole(Enum):
    """模型角色"""
    PRIMARY = "primary"        # 观尘子主模型 - 工程推理
    CREATION = "creation"      # 星卷创作模型 - 创意生成


class TaskType(Enum):
    """任务类型"""
    ENGINEERING = "engineering"          # 工程推理
    CODE_REVIEW = "code_review"          # 代码审查
    SYSTEM_DIAGNOSIS = "system_diagnosis"  # 系统诊断
    DATA_ANALYSIS = "data_analysis"      # 数据分析
    CREATIVE_WRITING = "creative_writing"  # 创意写作
    WORLDBUILDING = "worldbuilding"      # 世界观构建
    IP_CREATION = "ip_creation"          # IP创作
    SCRIPT = "script"                    # 剧本/脚本
    GENERAL = "general"                  # 通用


@dataclass
class ModelConfig:
    """模型配置"""
    model_id: str
    display_name: str
    role: ModelRole
    api_endpoint: str = ""
    api_key: str = ""
    model_name: str = "seed-2.1-pro"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 30
    task_types: List[TaskType] = field(default_factory=list)
    enabled: bool = True


@dataclass
class ModelStats:
    """模型运行统计"""
    model_id: str
    call_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    last_call_time: Optional[str] = None
    last_success_time: Optional[str] = None
    avg_latency_ms: float = 0.0
    _latency_sum: float = 0.0


# ============================================================
# 模型管理器
# ============================================================

class ModelManager:
    """双模型管理器
    管理观尘子主模型 + 星卷创作模型，提供智能路由、降级切换、额度管控
    """

    # 任务类型 -> 首选模型角色 的路由表
    ROUTING_TABLE: Dict[TaskType, ModelRole] = {
        TaskType.ENGINEERING: ModelRole.PRIMARY,
        TaskType.CODE_REVIEW: ModelRole.PRIMARY,
        TaskType.SYSTEM_DIAGNOSIS: ModelRole.PRIMARY,
        TaskType.DATA_ANALYSIS: ModelRole.PRIMARY,
        TaskType.CREATIVE_WRITING: ModelRole.CREATION,
        TaskType.WORLDBUILDING: ModelRole.CREATION,
        TaskType.IP_CREATION: ModelRole.CREATION,
        TaskType.SCRIPT: ModelRole.CREATION,
        TaskType.GENERAL: ModelRole.PRIMARY,
    }

    def __init__(
        self,
        daily_token_limit: int = 2000000,
        state_manager=None,
        logger=None,
    ):
        self.daily_token_limit = daily_token_limit
        self.state_manager = state_manager
        self.logger = logger

        self._models: Dict[str, ModelConfig] = {}
        self._stats: Dict[str, ModelStats] = {}
        self._lock = threading.Lock()

        # Token 用量追踪
        self._used_tokens_today: int = 0
        self._token_date: str = date.today().isoformat()
        self._load_token_state()

    # ============================================================
    # 模型注册与管理
    # ============================================================

    def register_model(self, config: ModelConfig) -> None:
        """注册模型"""
        with self._lock:
            self._models[config.model_id] = config
            if config.model_id not in self._stats:
                self._stats[config.model_id] = ModelStats(model_id=config.model_id)
            if self.logger:
                self.logger.info(f"注册模型: {config.display_name} ({config.model_id})")

    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self._models.get(model_id)

    def get_models_by_role(self, role: ModelRole) -> List[ModelConfig]:
        """按角色获取模型列表"""
        return [m for m in self._models.values() if m.role == role and m.enabled]

    def get_primary_model(self) -> Optional[ModelConfig]:
        """获取主模型（观尘子）"""
        models = self.get_models_by_role(ModelRole.PRIMARY)
        return models[0] if models else None

    def get_creation_model(self) -> Optional[ModelConfig]:
        """获取创作模型（星卷）"""
        models = self.get_models_by_role(ModelRole.CREATION)
        return models[0] if models else None

    # ============================================================
    # 智能路由
    # ============================================================

    def route_model(
        self,
        task_type: Optional[TaskType] = None,
        preferred_model_id: Optional[str] = None,
    ) -> Optional[ModelConfig]:
        """
        智能路由：根据任务类型选择最优模型
        优先级：指定模型 > 任务类型路由 > 主模型
        """
        # 1. 指定模型优先
        if preferred_model_id:
            model = self.get_model(preferred_model_id)
            if model and model.enabled:
                return model

        # 2. 按任务类型路由
        if task_type:
            role = self.ROUTING_TABLE.get(task_type, ModelRole.PRIMARY)
            models = self.get_models_by_role(role)
            if models:
                return models[0]

        # 3. 默认主模型
        return self.get_primary_model()

    # ============================================================
    # Token 额度管理
    # ============================================================

    def _load_token_state(self) -> None:
        """从 state_manager 加载今日Token用量"""
        if not self.state_manager:
            return
        try:
            state = self.state_manager.get("model_token_usage", {})
            saved_date = state.get("date", "")
            today = date.today().isoformat()
            if saved_date == today:
                self._used_tokens_today = state.get("used", 0)
                if self.logger:
                    self.logger.info(f"加载今日Token用量: {self._used_tokens_today}/{self.daily_token_limit}")
            else:
                self._used_tokens_today = 0
                self._token_date = today
        except Exception as e:
            if self.logger:
                self.logger.warning(f"加载Token状态失败: {e}")

    def _save_token_state(self) -> None:
        """保存Token用量到 state_manager"""
        if not self.state_manager:
            return
        try:
            self.state_manager.set("model_token_usage", {
                "date": self._token_date,
                "used": self._used_tokens_today,
                "limit": self.daily_token_limit,
            })
        except Exception as e:
            if self.logger:
                self.logger.warning(f"保存Token状态失败: {e}")

    def _check_daily_reset(self) -> None:
        """检查是否需要重置每日Token计数"""
        today = date.today().isoformat()
        if self._token_date != today:
            if self.logger:
                self.logger.info("新的一天，Token额度已重置")
            self._used_tokens_today = 0
            self._token_date = today
            self._save_token_state()

    def check_token_available(self, estimated_tokens: int = 1000) -> bool:
        """检查Token额度是否充足"""
        self._check_daily_reset()
        return (self._used_tokens_today + estimated_tokens) <= self.daily_token_limit

    def consume_tokens(self, prompt_tokens: int, completion_tokens: int, model_id: str) -> None:
        """消耗Token并更新统计"""
        total = prompt_tokens + completion_tokens
        with self._lock:
            self._used_tokens_today += total
            if model_id in self._stats:
                stats = self._stats[model_id]
                stats.total_prompt_tokens += prompt_tokens
                stats.total_completion_tokens += completion_tokens
                stats.total_tokens += total
        self._save_token_state()

    def get_token_usage(self) -> Dict[str, Any]:
        """获取Token使用统计"""
        self._check_daily_reset()
        used = self._used_tokens_today
        remaining = max(0, self.daily_token_limit - used)
        usage_pct = (used / self.daily_token_limit * 100) if self.daily_token_limit > 0 else 0

        per_model = {}
        for mid, stats in self._stats.items():
            per_model[mid] = {
                "total_tokens": stats.total_tokens,
                "prompt_tokens": stats.total_prompt_tokens,
                "completion_tokens": stats.total_completion_tokens,
                "calls": stats.call_count,
            }

        return {
            "date": self._token_date,
            "daily_limit": self.daily_token_limit,
            "today_used": used,
            "remaining": remaining,
            "usage_percent": round(usage_pct, 2),
            "per_model": per_model,
            "near_limit": usage_pct >= 90,
            "exceeded": used >= self.daily_token_limit,
        }

    # ============================================================
    # 推理调用
    # ============================================================

    def chat(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        对话式推理（支持自动路由与降级）
        """
        # 路由选择模型
        model = self.route_model(task_type=task_type, preferred_model_id=model_id)
        if not model:
            return {"success": False, "error": "没有可用的模型"}

        # Token 额度检查
        if not self.check_token_available():
            return {
                "success": False,
                "error": "今日Token额度已用尽",
                "token_usage": self.get_token_usage(),
            }

        # 执行推理（带降级重试）
        result = self._call_chat_api(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 主模型失败时尝试降级到另一个模型
        if not result["success"]:
            fallback = self._get_fallback_model(model)
            if fallback:
                if self.logger:
                    self.logger.warning(f"模型 [{model.display_name}] 失败，降级到 [{fallback.display_name}]")
                result = self._call_chat_api(
                    model=fallback,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                result["degraded_from"] = model.model_id
                result["used_model"] = fallback.model_id

        return result

    def _get_fallback_model(self, failed_model: ModelConfig) -> Optional[ModelConfig]:
        """获取降级备用模型"""
        for m in self._models.values():
            if m.enabled and m.model_id != failed_model.model_id:
                return m
        return None

    def _call_chat_api(
        self,
        model: ModelConfig,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """调用模型 Chat API（OpenAI 兼容格式）"""
        start_time = time.time()
        stats = self._stats.get(model.model_id)

        if stats:
            stats.call_count += 1
            stats.last_call_time = datetime.now().isoformat()

        # 无 API 端点时返回模拟响应（安全降级）
        if not model.api_endpoint or not model.api_key:
            if self.logger:
                self.logger.warning(f"模型 [{model.display_name}] 未配置API，返回模拟响应")
            mock_content = self._generate_mock_response(model, prompt)
            if stats:
                stats.success_count += 1
                stats.last_success_time = datetime.now().isoformat()
            # 模拟Token消耗
            prompt_tokens = len(prompt) // 2
            completion_tokens = len(mock_content) // 2
            self.consume_tokens(prompt_tokens, completion_tokens, model.model_id)
            return {
                "success": True,
                "model_id": model.model_id,
                "model_name": model.display_name,
                "content": mock_content,
                "mode": "mock",
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model.model_name,
                "messages": messages,
                "temperature": temperature if temperature is not None else model.temperature,
                "max_tokens": max_tokens if max_tokens is not None else model.max_tokens,
            }

            req = urllib.request.Request(
                url=model.api_endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {model.api_key}",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=model.timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            # 更新统计
            latency_ms = int((time.time() - start_time) * 1000)
            if stats:
                stats.success_count += 1
                stats.last_success_time = datetime.now().isoformat()
                stats._latency_sum += latency_ms
                stats.avg_latency_ms = stats._latency_sum / stats.success_count

            self.consume_tokens(prompt_tokens, completion_tokens, model.model_id)

            return {
                "success": True,
                "model_id": model.model_id,
                "model_name": model.display_name,
                "content": content,
                "mode": "api",
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "latency_ms": latency_ms,
            }

        except urllib.error.URLError as e:
            if stats:
                stats.fail_count += 1
            if self.logger:
                self.logger.error(f"模型 [{model.display_name}] API调用失败: {e}")
            return {
                "success": False,
                "model_id": model.model_id,
                "error": f"API调用失败: {e}",
                "latency_ms": int((time.time() - start_time) * 1000),
            }
        except Exception as e:
            if stats:
                stats.fail_count += 1
            if self.logger:
                self.logger.error(f"模型 [{model.display_name}] 调用异常: {e}")
            return {
                "success": False,
                "model_id": model.model_id,
                "error": f"调用异常: {e}",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

    def _generate_mock_response(self, model: ModelConfig, prompt: str) -> str:
        """生成模拟响应（无API时使用）"""
        if model.role == ModelRole.PRIMARY:
            return f"[观尘子·工程推理-模拟响应]\n收到任务: {prompt[:50]}...\n\n当前为模拟模式，配置API端点后可获得真实推理结果。"
        else:
            return f"[星卷·宇宙创作-模拟响应]\n以星海为墨，以时空为笔，关于「{prompt[:30]}」的史诗正在酝酿...\n\n当前为模拟模式，配置API端点后可获得真实创作结果。"

    # ============================================================
    # 状态与统计
    # ============================================================

    def get_status(self) -> Dict[str, Any]:
        """获取模型管理器整体状态"""
        ready_count = sum(1 for m in self._models.values() if m.enabled)
        models_info = {}
        for mid, config in self._models.items():
            stats = self._stats.get(mid, ModelStats(model_id=mid))
            models_info[mid] = {
                "display_name": config.display_name,
                "role": config.role.value,
                "enabled": config.enabled,
                "api_configured": bool(config.api_endpoint and config.api_key),
                "call_count": stats.call_count,
                "success_count": stats.success_count,
                "fail_count": stats.fail_count,
                "total_tokens": stats.total_tokens,
                "avg_latency_ms": round(stats.avg_latency_ms, 1),
            }

        return {
            "total_models": len(self._models),
            "ready_models": ready_count,
            "models": models_info,
            "token_usage": self.get_token_usage(),
        }

    def get_model_stats(self, model_id: str) -> Optional[ModelStats]:
        """获取指定模型统计"""
        return self._stats.get(model_id)
