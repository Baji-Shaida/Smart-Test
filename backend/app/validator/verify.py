"""Bug verification step: ask the LLM whether the function or the test is wrong."""
from __future__ import annotations

import json
import re

from ..generator.llm import LLMClient, LLMError
from ..generator.prompts import build_verification_prompt

VERDICTS = {"likely_bug", "test_wrong", "unclear"}


def parse_verdict(reply: str) -> dict:
    """Parse {"verdict", "reason"} defensively; anything invalid becomes unclear."""
    text = (reply or "").strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("verdict") in VERDICTS:
            reason = str(data.get("reason") or "").strip().splitlines()
            return {"verdict": data["verdict"], "reason": (reason[0] if reason else "")[:400]}
    return {"verdict": "unclear", "reason": "Verification reply was not valid JSON."}


def verify_failure(client: LLMClient, fn: dict, test_code: str, pytest_output: str) -> dict:
    try:
        reply = client.generate(build_verification_prompt(fn, test_code, pytest_output))
    except LLMError as exc:
        return {"verdict": "unclear", "reason": f"Verification failed: {exc}"}
    return parse_verdict(reply)
