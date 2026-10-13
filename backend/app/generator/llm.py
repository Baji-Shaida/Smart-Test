"""Pluggable LLM clients: OllamaClient (default) and MockLLMClient (deterministic, offline)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..config import get_settings


class LLMError(RuntimeError):
    """Raised when the LLM cannot be reached or returns an invalid response."""


class LLMClient(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return the raw completion for ``prompt``."""


class OllamaClient(LLMClient):
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        s = get_settings()
        self.base_url = (base_url or s.ollama_base_url).rstrip("/")
        self.model = model or s.ollama_model
        self.timeout = timeout or s.llm_timeout_sec

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Ollama is unreachable at {self.base_url} ({exc.__class__.__name__}). "
                "Start it with `ollama serve`."
            ) from exc
        if resp.status_code != 200:
            detail = resp.text[:300]
            raise LLMError(f"Ollama returned HTTP {resp.status_code}: {detail}")
        try:
            return resp.json().get("response", "")
        except ValueError as exc:
            raise LLMError("Ollama returned invalid JSON") from exc


def ollama_status(base_url: str | None = None, timeout: float = 3.0) -> dict:
    """Return {"reachable": bool, "models": [...], "error": str|None}."""
    url = (base_url or get_settings().ollama_base_url).rstrip("/")
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        return {"reachable": True, "models": models, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "models": [], "error": str(exc) or exc.__class__.__name__}


def get_llm_client(provider: str | None = None, model: str | None = None) -> LLMClient:
    provider = (provider or get_settings().llm_provider).lower()
    if provider == "mock":
        from .mock_llm import MockLLMClient

        return MockLLMClient()
    return OllamaClient(model=model)
