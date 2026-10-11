"""Modular Local LLM Architecture and Integration Interface for DeskBot.

Provides an extensible, pluggable interface for local offline LLM runtimes
(such as Ollama or llama.cpp) without blocking Phase 1 on downloading heavy models.
"""

from __future__ import annotations

import abc
import json
import logging
import os
import platform
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LocalLLMProvider(abc.ABC):
    """Abstract interface for local offline LLM runtimes."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check whether the local runtime daemon is responsive and ready."""
        pass

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 250,
        temperature: float = 0.2,
    ) -> Optional[str]:
        """Generate response text using local inference."""
        pass

    @abc.abstractmethod
    def get_model_name(self) -> str:
        """Return the active model tag/name."""
        pass


class OllamaProvider(LocalLLMProvider):
    """Modular integration for Ollama local inference daemon (http://127.0.0.1:11434)."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 8.0,
    ):
        self.model = model or os.getenv("DESKBOT_LOCAL_LLM_MODEL", "llama3.2:3b")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._is_enabled = os.getenv("DESKBOT_ENABLE_LOCAL_LLM", "0").lower() in ("1", "true", "yes")

    def is_available(self) -> bool:
        """Probe Ollama API endpoint with a tight 0.8s timeout."""
        if not self._is_enabled:
            return False
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"User-Agent": "DeskBot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    # Check if requested model or any model is loaded
                    return bool(models)
        except Exception:
            return False
        return False

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 250,
        temperature: float = 0.2,
    ) -> Optional[str]:
        if not self.is_available():
            return None

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "DeskBot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    return res_json.get("response", "").strip()
        except Exception as err:
            logger.debug("Ollama local generation exception: %s", err)
            return None
        return None

    def get_model_name(self) -> str:
        return f"Ollama ({self.model})"


_LOCAL_LLM_INSTANCE: Optional[LocalLLMProvider] = None


def get_local_llm_provider() -> Optional[LocalLLMProvider]:
    """Retrieve active local LLM provider if enabled and responsive."""
    global _LOCAL_LLM_INSTANCE
    if _LOCAL_LLM_INSTANCE is None:
        provider = OllamaProvider()
        if provider.is_available():
            _LOCAL_LLM_INSTANCE = provider
    return _LOCAL_LLM_INSTANCE


def get_hardware_recommendations() -> Dict[str, Any]:
    """Inspect local hardware and recommend optimal local LLM configurations."""
    total_ram_gb = 8.0
    try:
        import psutil
        total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass

    sys_platform = platform.system()
    machine = platform.machine()
    is_apple_silicon = sys_platform == "Darwin" and machine in ("arm64", "aarch64")

    if total_ram_gb >= 16:
        recommended_model = "llama3.2:3b" if is_apple_silicon else "qwen2.5:3b"
        recommended_quant = "Q4_K_M (int4)"
        recommended_runtime = "Ollama with Metal acceleration" if is_apple_silicon else "Ollama (CPU/DirectML)"
    elif total_ram_gb >= 8:
        recommended_model = "llama3.2:1b"
        recommended_quant = "Q4_0"
        recommended_runtime = "Ollama"
    else:
        recommended_model = "smollm:135m"
        recommended_quant = "Q4_0"
        recommended_runtime = "llama.cpp minimalist"

    return {
        "platform": f"{sys_platform} ({machine})",
        "total_ram_gb": total_ram_gb,
        "is_apple_silicon": is_apple_silicon,
        "recommended_runtime": recommended_runtime,
        "recommended_model": recommended_model,
        "recommended_quantization": recommended_quant,
    }
