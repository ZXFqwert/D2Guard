"""
D²Guard 统一大模型配置管理模块
支持动态切换外部商用 API (DeepSeek-v3.2) 与算力机 GPU1 自部署服务 (Huihui-Qwen3.8-27B / vLLM)
"""

from __future__ import annotations
import os
from typing import Any, Dict, Optional, Tuple
from openai import OpenAI


def get_llm_config(provider: Optional[str] = None) -> Dict[str, str]:
    """
    获取指定或环境变量默认的模型配置
    provider: 'deepseek' | 'gpu1' | None (读取 LLM_PROVIDER 环境变量)
    """
    selected = (provider or os.getenv("LLM_PROVIDER", "deepseek")).strip().lower()

    if selected in ["gpu1", "server", "vllm", "local_gpu"]:
        base_url = os.getenv("GPU1_BASE_URL", "https://api.li33.art/gpu1/v1")
        api_key = os.getenv("GPU1_API_KEY", "15581643721")
        model = os.getenv("GPU1_MODEL", "huihui-qwen3.8-27b")
        return {
            "provider": "gpu1",
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "display_name": f"算力机 GPU1 自部署 ({model})"
        }
    else:
        base_url = os.getenv("LLM_BASE_URL", "https://api.huiyan-ai.cn/v1")
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "deepseek-v3.2")
        return {
            "provider": "deepseek",
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "display_name": f"DeepSeek API ({model})"
        }


_CLIENT_CACHE: Dict[Tuple[str, str], OpenAI] = {}


def create_llm_client(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> Tuple[Optional[OpenAI], str]:
    """
    创建并返回 (OpenAI_client, model_name)
    使用单例缓存池，消除 Windows 下每次新建 httpx 客户端长达 2.2 秒的初始化延迟
    """
    cfg = get_llm_config(provider)
    final_key = api_key or cfg["api_key"]
    final_url = base_url or cfg["base_url"]
    final_model = model or cfg["model"]

    if not final_key:
        return None, final_model

    cache_key = (final_key, final_url)
    if cache_key not in _CLIENT_CACHE:
        _CLIENT_CACHE[cache_key] = OpenAI(api_key=final_key, base_url=final_url)

    return _CLIENT_CACHE[cache_key], final_model
