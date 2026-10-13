"""Baseline / after coverage: run coverage.py + pytest in a subprocess and map lines to functions."""
from __future__ import annotations

import json
import site
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..analyzer.extractor import SKIP_DIRS
from ..sandbox import minimal_env, run_sandboxed

Log = Callable[[str, str], None]


def _noop(level: str, message: str) -> None:  # pragma: no cover
    pass


@dataclass
class CoverageResult:
    ok: bool
    total_pct: float
    files: dict = field(default_factory=dict)  # rel path -> {"executed": set, "missing": set}
    pytest_returncode: int | None = None
    pytest_output: str = ""
    error: str | None = None


def _real_requirements(req: Path) -> list[str]:
    if not req.is_file():
        return []
    lines = []
    for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def prepare_python(repo: Path, job_dir: Path, timeout: int, log: Log = _noop) -> str:
    """Return the python executable used to run the project's tests.

    If requirements.txt lists packages, create a per-job venv that can also see the backend's
    packages (pytest, coverage) and install the requirements into it. On any failure, warn and
    fall back to the backend interpreter.
    """
    req = Path(repo) / "requirements.txt"
    if not req.is_file():
        log("info", "No requirements.txt found; using the base environment")
        return sys.executable
    if not _real_requirements(req):
        log("info", "requirements.txt lists no packages; nothing to install")
        return sys.executable
    venv_dir = Path(job_dir) / "venv"
    try:
        log("info", "Installing project dependencies into a job virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True, timeout=60)
        py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        res = run_sandboxed([str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                            cwd=job_dir, timeout=30, env=minimal_env(home=job_dir))
        purelib = Path(res.stdout.strip())
        parent_paths = [p for p in site.getsitepackages() + [site.getusersitepackages()] if Path(p).is_dir()]
        (purelib / "_smarttest_parent.pth").write_text("\n".join(parent_paths) + "\n")
        res = run_sandboxed([str(py), "-m", "pip", "install", "-q", "-r", str(req)], cwd=repo,
                            timeout=timeout, env=minimal_env(home=job_dir))
        if res.timed_out:
            log("warn", f"Dependency install timed out after {timeout}s; continuing without it")
        elif res.returncode != 0:
            tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or ["unknown error"]
            log("warn", f"Dependency install failed ({tail[0][:200]}); continuing without it")
        else:
            log("success", "Project dependencies installed")
        return str(py)
    except Exception as exc:  # noqa: BLE001
        log("warn", f"Could not create a virtual environment ({exc}); using the base environment")
        return sys.executable


def write_coveragerc(repo: Path, path: Path) -> Path:
    """Coverage config: source = the repo, omit tests and vendored folders so unimported files show 0%."""
    omit = ["*/tests/*", "*/test/*", "*/test_*.py", "*_test.py", "*/conftest.py", "tests/*", "test/*",
            "test_*.py", "conftest.py", "setup.py"]
    omit += [f"*/{d}/*" for d in sorted(SKIP_DIRS)] + [f"{d}/*" for d in sorted(SKIP_DIRS)]
    text = "[run]\nsource = .\nrelative_files = True\nbranch = False\nomit =\n"
    text += "".join(f"    {o}\n" for o in omit)
    text += "\n[report]\nignore_errors = True\n\n[json]\nshow_contexts = False\n"
    path.write_text(text)
    return path


def run_coverage(repo: Path, job_dir: Path, python: str, label: str, timeout: int,
                 test_targets: list[str] | None = None) -> CoverageResult:
    """Run ``coverage run -m pytest`` in the repo workspace and parse ``coverage json``."""
    repo = Path(repo).resolve()
    job_dir = Path(job_dir).resolve()
    rc = write_coveragerc(repo, job_dir / ".coveragerc")
    data_file = job_dir / f".coverage_{label}"
    json_out = job_dir / f"coverage_{label}.json"
    for f in (data_file, json_out):
        f.unlink(missing_ok=True)
    env = minimal_env(repo=repo, home=job_dir)
    cmd = [python, "-m", "coverage", "run", f"--rcfile={rc}", f"--data-file={data_file}",
           "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(repo), *(test_targets or [])]
    run = run_sandboxed(cmd, cwd=repo, timeout=timeout, env=env)
    result = CoverageResult(ok=False, total_pct=0.0, pytest_returncode=run.returncode,
                            pytest_output=run.output[-4000:])
    if run.timed_out:
        result.error = f"pytest timed out after {timeout}s"
    js = run_sandboxed([python, "-m", "coverage", "json", f"--rcfile={rc}", f"--data-file={data_file}",
                        "-o", str(json_out)], cwd=repo, timeout=120, env=env)
    if js.returncode != 0 or not json_out.is_file():
        result.error = result.error or (js.output.strip().splitlines() or ["coverage json failed"])[-1]
        return result
    data = json.loads(json_out.read_text())
    result.ok = True
    result.total_pct = round(float(data.get("totals", {}).get("percent_covered", 0.0)), 2)
    for name, info in data.get("files", {}).items():
        rel = Path(name).as_posix()
        if Path(name).is_absolute():
            try:
                rel = Path(name).resolve().relative_to(repo).as_posix()
            except ValueError:
                continue
        result.files[rel] = {
            "executed": set(info.get("executed_lines", [])),
            "missing": set(info.get("missing_lines", [])),
        }
    return result


def map_function_coverage(functions: list[dict], cov: CoverageResult) -> dict[str, dict]:
    """Per-function coverage over the function body (decorators/def line/docstring excluded).

    Returns {function_id: {"pct": float, "covered": int, "statements": int}}.
    """
    out: dict[str, dict] = {}
    for fn in functions:
        info = cov.files.get(fn["file"])
        lo, hi = fn.get("body_start", fn["line_start"]), fn["line_end"]
        if not info:
            out[fn["id"]] = {"pct": 0.0, "covered": 0, "statements": 0}
            continue
        executed = {ln for ln in info["executed"] if lo <= ln <= hi}
        missing = {ln for ln in info["missing"] if lo <= ln <= hi}
        statements = len(executed) + len(missing)
        pct = round(len(executed) / statements * 100, 2) if statements else 0.0
        out[fn["id"]] = {"pct": pct, "covered": len(executed), "statements": statements}
    return out


def coverage_label(pct: float, threshold: float) -> str:
    if pct <= 0:
        return "untested"
    if pct < threshold:
        return "partial"
    return "tested"
