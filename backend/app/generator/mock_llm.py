"""Deterministic offline LLM used by automated tests and machines without a GPU."""
from __future__ import annotations

from .llm import LLMClient


class MockLLMClient(LLMClient):
    name = "mock"
    model = "mock"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return "```python\n# mock\n```"
