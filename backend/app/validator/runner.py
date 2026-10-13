"""Gate 2: run a generated test file with pytest in a subprocess and parse JUnit XML per test."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..sandbox import minimal_env, run_sandboxed


@dataclass
class CaseResult:
    name: str
    outcome: str  # passed | failed | error | skipped
    message: str = ""
    text: str = ""


@dataclass
class PytestRun:
    returncode: int
    timed_out: bool
    output: str
    cases: dict[str, CaseResult] = field(default_factory=dict)
    collection_error: str | None = None


def run_pytest(test_file: Path, repo: Path, job_dir: Path, python: str, timeout: float) -> PytestRun:
    test_file = Path(test_file).resolve()
    xml_path = Path(job_dir) / "junit" / (test_file.stem + ".xml")
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    xml_path.unlink(missing_ok=True)
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short", "-o", "console_output_style=classic",
           "--rootdir", str(test_file.parent), f"--junitxml={xml_path}", str(test_file)]
    res = run_sandboxed(cmd, cwd=repo, timeout=timeout, env=minimal_env(repo=repo, home=job_dir))
    run = PytestRun(returncode=res.returncode, timed_out=res.timed_out, output=res.output[-6000:])
    if res.timed_out:
        return run
    if not xml_path.is_file():
        run.collection_error = (res.output.strip() or "pytest produced no report")[-3000:]
        return run
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        run.collection_error = f"could not parse pytest report: {exc}"
        return run
    for tc in root.iter("testcase"):
        name = tc.get("name", "")
        name = re.sub(r"\[.*\]$", "", name)  # parametrized ids collapse to the function
        children = list(tc)
        fail = next((c for c in children if c.tag in ("failure", "error")), None)
        skipped = next((c for c in children if c.tag == "skipped"), None)
        if fail is not None and fail.tag == "error" and (fail.get("message") or "") == "collection failure":
            run.collection_error = (fail.text or fail.get("message") or "collection failure")[-3000:]
            continue
        if fail is not None:
            outcome = "failed" if fail.tag == "failure" else "error"
            case = CaseResult(name, outcome, fail.get("message") or "", fail.text or "")
        elif skipped is not None:
            case = CaseResult(name, "skipped", skipped.get("message") or "", skipped.text or "")
        else:
            case = CaseResult(name, "passed")
        prev = run.cases.get(name)
        if prev is None or prev.outcome == "passed":  # keep the worst outcome per function
            run.cases[name] = case
    if not run.cases and run.collection_error is None and res.returncode not in (0, 5):
        run.collection_error = (res.output.strip() or "pytest failed")[-3000:]
    return run
