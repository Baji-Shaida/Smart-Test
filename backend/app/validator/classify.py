"""Classification rules for a single test result (spec section 4, Step 5)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath

from .runner import CaseResult

_FRAME_RE = re.compile(r"^(\S[^\n]*?):(\d+): in (\S+)\s*$", re.MULTILINE)
_EXC_RE = re.compile(
    r"^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Failed)|Failed)\b:?\s?(.*)", re.DOTALL
)
INVALID_EXC = {"ImportError", "ModuleNotFoundError", "NameError", "SyntaxError", "IndentationError"}

ACCEPTED = "accepted"
NEEDS_REVIEW = "needs_review"
REJECTED = "rejected"
POSSIBLE_BUG = "possible_bug"


@dataclass
class Observation:
    kind: str  # passed | invalid | failure | skipped
    exc_type: str = ""
    reason: str = ""
    expected: str | None = None
    actual: str | None = None
    traceback: str = ""


def trim(text: str, lines: int = 15) -> str:
    return "\n".join((text or "").rstrip().splitlines()[-lines:])


def exception_type(message: str) -> str:
    msg = (message or "").strip()
    if msg.startswith("assert ") or msg.startswith("AssertionError"):
        return "AssertionError"
    m = _EXC_RE.match(msg)
    if m:
        return m.group(1).split(".")[-1]
    return "AssertionError" if "assert" in msg.split("\n", 1)[0] else (msg.split(":", 1)[0] or "Error")


def last_frame_file(text: str) -> str | None:
    frames = _FRAME_RE.findall(text or "")
    return frames[-1][0] if frames else None


def _in_test_file(frame_file: str | None, test_file_name: str) -> bool:
    return frame_file is None or PurePath(frame_file).name == test_file_name


def parse_expected_actual(message: str, text: str, func_name: str) -> tuple[str | None, str | None]:
    """Best-effort expected/actual from a pytest assertion message."""
    blob = (message or "") + "\n" + (text or "")
    m = re.search(r"assert (.+?) == (.+?)\s*$", blob.split("\n +")[0].splitlines()[0] if message else "", re.M)
    if not m:
        m = re.search(r"^E?\s*assert (.+?) == (.+?)\s*$", blob, re.M)
    if not m:
        return None, None
    left, right = m.group(1).strip(), m.group(2).strip()
    wheres = re.findall(r"where (.+?) = (.+)", blob)
    for value, expr in wheres:
        if func_name and func_name in expr:
            if value.strip() == right:
                return left, right
            break
    return right, left


def observe(case: CaseResult, test_file_name: str, func_name: str) -> Observation:
    """Turn a raw pytest case into an Observation, before verification."""
    if case.outcome == "passed":
        return Observation("passed")
    if case.outcome == "skipped":
        return Observation("skipped", reason=f"Test was skipped: {case.message[:200]}")
    tb = trim(case.text or case.message)
    if case.outcome == "error":  # setup/teardown error, e.g. missing fixture
        first = (case.message or "").splitlines()[0][:200] if case.message else "setup error"
        fixture = re.search(r"fixture '([^']+)' not found", case.text or case.message or "")
        reason = f"fixture error: fixture '{fixture.group(1)}' not found" if fixture else f"setup error: {first}"
        return Observation("invalid", "FixtureError", reason, traceback=tb)
    exc = exception_type(case.message)
    origin = last_frame_file(case.text)
    in_test = _in_test_file(origin, test_file_name)
    first_line = (case.message or "").strip().splitlines()[0][:300] if case.message else exc
    if exc in INVALID_EXC:
        return Observation("invalid", exc, f"invalid test: {first_line}", traceback=tb)
    if exc == "TypeError" and in_test:
        return Observation("invalid", exc, f"wrong arguments at the test's call site: {first_line}", traceback=tb)
    if exc == "AssertionError":
        expected, actual = parse_expected_actual(case.message, case.text, func_name)
        reason = f"Expected {expected}, function returned {actual}" if expected is not None else first_line
        return Observation("failure", exc, reason, expected, actual, tb)
    if exc == "Failed" and "DID NOT RAISE" in (case.message or ""):
        m = re.search(r"DID NOT RAISE <class '([^']+)'>", case.message)
        exp = f"raises {m.group(1) if m else 'an exception'}"
        return Observation("failure", exc, f"Expected the call to {exp}, but it returned normally", exp,
                           "returned normally", tb)
    if not in_test:
        return Observation("failure", exc, f"{first_line} (raised inside the code under test)", "no exception",
                           first_line, tb)
    return Observation("invalid", exc, f"error in test code: {first_line}", traceback=tb)


def function_status(test_statuses: list[str]) -> str:
    """Precedence: POSSIBLE BUG FOUND, NEEDS REVIEW, ACCEPTED, REJECTED."""
    for status in (POSSIBLE_BUG, NEEDS_REVIEW, ACCEPTED):
        if status in test_statuses:
            return status
    return REJECTED
