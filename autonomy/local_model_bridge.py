#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地模型桥接层 (Local Model Bridge)
====================================
第一阶段：旁路桥接层，零侵入引擎核心，独立可删。

定位：阴期轻量语义任务的兜底层，完全不依赖云端API。
原则：可降级、不依赖、失败安全——任何异常返回None，调用方自动回退规则逻辑。

使用方式：
    from local_model_bridge import LocalModelBridge
    bridge = LocalModelBridge()
    result = bridge.chat("请把这句话分类", max_tokens=50)
    if result is None:
        # 回退规则逻辑
        pass

注意：本模块默认关闭，需手动设置 enabled=True 才会真正调用模型。
"""

import json
import os
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


class LocalModelBridge:
    """本地模型桥接层——封装llama-server的OpenAI兼容API调用。

    设计原则：
    1. 完全独立，不导入任何引擎核心模块
    2. 零侵入，引擎不需要知道本模块存在
    3. 失败安全，所有异常捕获后返回None，不抛出
    4. 内存保护，调用前检查可用内存，不足则跳过
    5. 默认关闭，需显式启用
    """

    # ========== 配置（可被构造参数覆盖） ==========
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8081  # 避开8080端口的tinyproxy代理
    DEFAULT_TIMEOUT = 30  # 秒
    DEFAULT_MAX_TOKENS = 100
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_CONTEXT_SIZE = 2048  # 限制上下文，节省内存（全32K需384MB KV缓存）
    MIN_FREE_MEMORY_MB = 1024  # 调用前最低可用内存，低于此值自动跳过

    def __init__(self, host=None, port=None, timeout=None, enabled=False):
        """初始化桥接层。

        Args:
            host: llama-server地址，默认127.0.0.1
            port: llama-server端口，默认8081
            timeout: 请求超时秒数，默认30
            enabled: 是否启用，默认False（安全默认值）
        """
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.enabled = enabled  # 全局总开关，默认关闭

        # 统计
        self.call_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.last_error = None

        self._base_url = f"http://{self.host}:{self.port}"

    # ========== 核心接口 ==========

    def chat(self, prompt, system_prompt=None, max_tokens=None, temperature=None):
        """调用本地模型进行对话生成。

        Args:
            prompt: 用户输入文本
            system_prompt: 系统提示词（可选）
            max_tokens: 最大生成token数，默认100
            temperature: 采样温度，默认0.7

        Returns:
            str: 模型生成的文本，失败返回None
        """
        # 总开关检查
        if not self.enabled:
            return None

        # 内存保护检查
        if not self._check_memory():
            logger.debug("[LocalBridge] 内存不足，跳过本地模型调用")
            return None

        # 服务可用性检查（轻量，不阻塞）
        if not self._check_service():
            return None

        # 构造消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 构造请求体
        payload = {
            "model": "qwen2-0.5b-local",
            "messages": messages,
            "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
            "temperature": temperature if temperature is not None else self.DEFAULT_TEMPERATURE,
            "stream": False,
        }

        # 发送请求
        try:
            self.call_count += 1
            result = self._http_post(
                f"{self._base_url}/v1/chat/completions",
                payload,
                timeout=self.timeout
            )

            if result is None:
                self.fail_count += 1
                return None

            # 解析响应
            content = self._parse_chat_response(result)
            if content is not None:
                self.success_count += 1
                return content.strip()
            else:
                self.fail_count += 1
                self.last_error = "响应解析失败"
                return None

        except Exception as e:
            self.fail_count += 1
            self.last_error = str(e)
            logger.debug(f"[LocalBridge] 调用异常: {e}")
            return None

    def classify(self, text, categories, max_tokens=30):
        """文本分类快捷接口。

        Args:
            text: 待分类文本
            categories: 类别列表，如["科技", "财经", "体育"]
            max_tokens: 最大生成token数

        Returns:
            str: 分类结果，失败返回None
        """
        cat_str = "、".join(categories)
        prompt = f"请将以下文本分类为以下类别之一：{cat_str}\n只输出类别名称，不要解释。\n\n文本：{text}"
        return self.chat(prompt, max_tokens=max_tokens, temperature=0.1)

    def summarize(self, text, max_tokens=80):
        """文本摘要快捷接口。

        Args:
            text: 待摘要文本
            max_tokens: 最大生成token数

        Returns:
            str: 摘要文本，失败返回None
        """
        prompt = f"请用一句话总结以下文本的核心内容：\n\n{text}"
        return self.chat(prompt, max_tokens=max_tokens, temperature=0.3)

    # ========== 内部方法 ==========

    def _http_post(self, url, payload, timeout=30):
        """发送HTTP POST请求（用urllib，避免requests代理兼容性问题）。

        Args:
            url: 请求URL
            payload: 请求体字典
            timeout: 超时秒数

        Returns:
            dict: 响应JSON，失败返回None
        """
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            # 关键：设置空代理，避免沙箱代理干扰本地请求
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)

            with opener.open(req, timeout=timeout) as resp:
                if resp.status != 200:
                    self.last_error = f"HTTP {resp.status}"
                    return None
                body = resp.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.URLError as e:
            self.last_error = f"URLError: {e}"
            return None
        except json.JSONDecodeError as e:
            self.last_error = f"JSONDecodeError: {e}"
            return None
        except Exception as e:
            self.last_error = f"Exception: {e}"
            return None

    def _parse_chat_response(self, response):
        """解析OpenAI兼容的chat completions响应。

        Args:
            response: 响应字典

        Returns:
            str: 生成的文本内容，失败返回None
        """
        try:
            choices = response.get("choices", [])
            if not choices:
                return None
            message = choices[0].get("message", {})
            content = message.get("content", "")
            return content if content else None
        except Exception as e:
            self.last_error = f"解析异常: {e}"
            return None

    def _check_memory(self):
        """检查可用内存是否充足。

        Returns:
            bool: 内存充足返回True，不足返回False
        """
        try:
            # 读取/proc/meminfo（Linux沙箱）
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        # 格式: "MemAvailable:    3456789 kB"
                        kb = int(line.split()[1])
                        mb = kb // 1024
                        return mb >= self.MIN_FREE_MEMORY_MB
            return True  # 读不到就放行，不阻塞
        except Exception:
            return True  # 检查失败不阻塞调用

    def _check_service(self):
        """轻量检查llama-server是否可用（不阻塞主流程，超时2秒）。

        Returns:
            bool: 服务可用返回True，不可用返回False
        """
        try:
            url = f"{self._base_url}/health"
            req = urllib.request.Request(url, method="GET")
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            with opener.open(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            # /health端点可能不存在，尝试根路径
            try:
                url = f"{self._base_url}/"
                req = urllib.request.Request(url, method="GET")
                proxy_handler = urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(proxy_handler)
                with opener.open(req, timeout=2) as resp:
                    return resp.status == 200
            except Exception:
                self.last_error = "服务不可达"
                return False

    # ========== 工具方法 ==========

    def get_stats(self):
        """获取调用统计。

        Returns:
            dict: 统计信息
        """
        return {
            "enabled": self.enabled,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "success_rate": (self.success_count / self.call_count * 100) if self.call_count > 0 else 0,
            "last_error": self.last_error,
            "base_url": self._base_url,
        }

    def enable(self):
        """启用本地模型桥接。"""
        self.enabled = True
        logger.info("[LocalBridge] 本地模型桥接已启用")

    def disable(self):
        """禁用本地模型桥接。"""
        self.enabled = False
        logger.info("[LocalBridge] 本地模型桥接已禁用")

    def __repr__(self):
        stats = self.get_stats()
        return (f"<LocalModelBridge enabled={stats['enabled']} "
                f"calls={stats['call_count']} ok={stats['success_count']} "
                f"fail={stats['fail_count']} url={stats['base_url']}>")


# ========== 单例（可选） ==========
_default_bridge = None

def get_bridge():
    """获取默认桥接层单例。

    Returns:
        LocalModelBridge: 默认桥接层实例
    """
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = LocalModelBridge()
    return _default_bridge


# ========== 自测入口 ==========
if __name__ == "__main__":
    """独立自测：不依赖引擎，直接测试桥接层。

    用法：
        python3 local_model_bridge.py  # 测试（默认不启用，只测连通性）
        ENABLE_LOCAL=1 python3 local_model_bridge.py  # 启用并测试实际调用
    """
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    bridge = LocalModelBridge()
    print("=== 本地模型桥接层自测 ===")
    print(f"桥接层状态: {bridge}")
    print(f"内存检查: {bridge._check_memory()}")
    print(f"服务检查: {bridge._check_service()}")

    if os.environ.get("ENABLE_LOCAL") == "1":
        print("\n=== 启用并测试实际调用 ===")
        bridge.enable()
        result = bridge.chat("你好，请用一句话介绍你自己", max_tokens=50)
        print(f"调用结果: {result}")
        print(f"统计: {bridge.get_stats()}")
    else:
        print("\n提示：设置 ENABLE_LOCAL=1 环境变量可测试实际调用")
        print("当前仅测试连通性，不发送实际请求（默认关闭安全策略）")
