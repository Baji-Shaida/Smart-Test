"""Prompt templates (spec section 9) and helpers."""
from __future__ import annotations

import re

GENERATION_TEMPLATE = """You are an expert Python test engineer. Write pytest unit tests for the function below.
FILE: {file_path}
IMPORT STATEMENT TO USE: {import_stmt}
{class_context}
FUNCTION UNDER TEST:
```python
{function_source}
```
DOCSTRING / INTENT: {docstring}
EXAMPLE CALL SITES FROM THE CODEBASE:
{call_sites}
RULES:
1. Output ONE python code block containing only the test code. No explanation.
2. Use exactly the import statement given. Do not import anything that is not installed.
3. Write 3 to 6 test functions named test_{function_name}_<scenario>.
4. Cover a normal case, at least one edge case (zero, empty, boundary), and an invalid-input
   case only if the code or docstring shows it raises an error (use pytest.raises).
5. Every test must call the function under test and assert on its real return value
   or on the raised exception.
6. Derive expected values from the docstring/intent and simple hand calculation,
   NOT by guessing what the current code returns.
7. No network, no randomness, no dependence on the current time. Use tmp_path for files.
"""

RETRY_TEMPLATE = """Your previous test code was rejected.
PROBLEM: {problem}
PREVIOUS CODE:
```python
{previous_code}
```
Fix the problem and output ONE corrected python code block. Follow all original rules.
"""

VERIFY_TEMPLATE = """A generated test failed. Decide whether the FUNCTION has a bug or the TEST is wrong.
FUNCTION:
```python
{function_source}
```
DOCSTRING / INTENT: {docstring}
FAILING TEST:
```python
{test_code}
```
PYTEST OUTPUT (trimmed):
{pytest_output}
Answer with JSON only, no other text:
{{"verdict": "likely_bug" | "test_wrong" | "unclear", "reason": "<one sentence>"}}
"""

_FENCE_RE = re.compile(r"```[ \t]*(?:python3?|py)?[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_OPEN_FENCE_RE = re.compile(r"```[ \t]*(?:python3?|py)?[ \t]*\r?\n(.*)", re.DOTALL | re.IGNORECASE)


def import_statement(fn: dict) -> str:
    """Exact import for the target: ``from <module> import <function or class>``."""
    target = fn["class_name"] if fn.get("is_method") else fn["name"]
    return f"from {fn['module']} import {target}"


def import_target(fn: dict) -> str:
    return fn["class_name"] if fn.get("is_method") else fn["name"]


def extract_code(reply: str) -> str:
    """First fenced python block; if none, the whole reply is treated as code."""
    m = _FENCE_RE.search(reply or "")
    if m:
        return m.group(1).strip() + "\n"
    m = _OPEN_FENCE_RE.search(reply or "")
    if m:
        return m.group(1).strip() + "\n"
    return (reply or "").strip() + "\n"


def _context_block(fn: dict) -> str:
    parts = []
    if fn.get("is_method") and fn.get("class_context"):
        parts.append(
            "CLASS CONTEXT (the method belongs to this class; create an instance to call it):\n"
            f"```python\n{fn['class_context']}\n```"
        )
    if fn.get("imports"):
        parts.append("MODULE IMPORTS (context only):\n" + "\n".join(fn["imports"]))
    return "\n".join(parts)


def build_generation_prompt(fn: dict, call_sites: list[str]) -> str:
    return GENERATION_TEMPLATE.format(
        file_path=fn["file"],
        import_stmt=import_statement(fn),
        class_context=_context_block(fn),
        function_source=fn["source"].rstrip(),
        docstring=fn.get("docstring") or "none provided",
        call_sites="\n".join(call_sites) if call_sites else "none found",
        function_name=fn["name"].strip("_") or fn["name"],
    )


def build_retry_prompt(generation_prompt: str, previous_code: str, problem: str) -> str:
    """Retry prompt. The original prompt is included first so a stateless LLM keeps the full context."""
    retry = RETRY_TEMPLATE.format(problem=problem, previous_code=previous_code.rstrip())
    return f"{generation_prompt}\n---\n{retry}"


def build_verification_prompt(fn: dict, test_code: str, pytest_output: str) -> str:
    return VERIFY_TEMPLATE.format(
        function_source=fn["source"].rstrip(),
        docstring=fn.get("docstring") or "none provided",
        test_code=test_code.rstrip(),
        pytest_output=pytest_output.strip() or "(no output)",
    )


def generated_test_filename(fn: dict) -> str:
    module = fn["module"].replace(".", "_") or "module"
    func = fn["qualname"].replace(".", "_")
    return f"test_{module}__{func}.py"
