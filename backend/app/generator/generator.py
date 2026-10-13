"""Test generation with the LLM, including the static-check retry loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .llm import LLMClient
from .prompts import build_generation_prompt, build_retry_prompt, extract_code

StaticCheck = Callable[[str], "str | None"]  # returns a problem description or None


@dataclass
class GenerationResult:
    code: str
    attempts: int
    prompt: str
    problem: str | None = None  # last static-check problem if still failing
    history: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.problem is None


class TestGenerator:
    __test__ = False  # not a pytest class

    def __init__(self, client: LLMClient, max_retries: int = 2):
        self.client = client
        self.max_retries = max_retries

    def ask(self, prompt: str) -> str:
        return extract_code(self.client.generate(prompt))

    def generate(self, fn: dict, call_sites: list[str], static_check: StaticCheck | None = None,
                 attempts_used: int = 0) -> GenerationResult:
        """Generate a test file; retry (up to max_retries) while ``static_check`` reports a problem."""
        prompt = build_generation_prompt(fn, call_sites)
        code = self.ask(prompt)
        result = GenerationResult(code=code, attempts=attempts_used + 1, prompt=prompt)
        return self.fix_until_valid(result, static_check)

    def fix_until_valid(self, result: GenerationResult, static_check: StaticCheck | None) -> GenerationResult:
        problem = static_check(result.code) if static_check else None
        while problem and result.attempts <= self.max_retries:
            result.history.append({"code": result.code, "problem": problem})
            result.code = self.retry(result.prompt, result.code, problem)
            result.attempts += 1
            problem = static_check(result.code) if static_check else None
        result.problem = problem
        return result

    def retry(self, generation_prompt: str, previous_code: str, problem: str) -> str:
        return self.ask(build_retry_prompt(generation_prompt, previous_code, problem))
