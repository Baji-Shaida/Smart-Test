"""Run untrusted code (user projects, generated tests) in subprocesses with a timeout and a minimal env."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_PASSTHROUGH = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def output(self) -> str:
        return (self.stdout or "") + (("\n" + self.stderr) if self.stderr else "")


def pythonpath_for(repo: Path) -> str:
    repo = Path(repo).resolve()
    paths = [str(repo)]
    if (repo / "src").is_dir():
        paths.append(str(repo / "src"))
    return os.pathsep.join(paths)


def minimal_env(repo: Path | None = None, home: Path | None = None, extra: dict | None = None) -> dict:
    """A clean environment: no backend secrets, only what Python/pytest need."""
    env = {k: os.environ[k] for k in _PASSTHROUGH if k in os.environ}
    env.setdefault("PATH", os.defpath)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if home is not None:
        env["HOME"] = str(home)
    if repo is not None:
        env["PYTHONPATH"] = pythonpath_for(repo)
    if extra:
        env.update(extra)
    return env


def run_sandboxed(cmd: list[str], cwd: Path, timeout: float, env: dict | None = None) -> RunResult:
    """Run ``cmd`` in ``cwd``; kill the whole process group on timeout."""
    kwargs: dict = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - windows
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), env=env if env is not None else minimal_env(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
        encoding="utf-8", errors="replace", **kwargs,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return RunResult(proc.returncode, out, err, False)
    except subprocess.TimeoutExpired:
        _kill(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            out, err = "", ""
        return RunResult(-9, out or "", err or "", True)


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover
            proc.kill()
    except (ProcessLookupError, PermissionError):
        proc.kill()


def backend_python() -> str:
    return sys.executable
