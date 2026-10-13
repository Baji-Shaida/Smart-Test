"""Job state, JSON storage, event log (events.jsonl) and the two background phases."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import threading
import time
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .analyzer import count_calls, example_call_sites, extract_functions, find_call_sites, iter_python_files
from .config import get_settings
from .coverage_check import map_function_coverage, prepare_python, run_coverage
from .coverage_check.runner import coverage_label
from .generator import get_llm_client, ollama_status
from .prioritizer import prioritize
from .reporter import build_summary
from .sandbox import minimal_env, run_sandboxed
from .validator import FunctionContext, keep_only_tests, process_function

GITHUB_URL_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?/?$")
STATUS_TEXT = {
    "accepted": "ACCEPTED",
    "needs_review": "NEEDS REVIEW",
    "rejected": "REJECTED",
    "possible_bug": "POSSIBLE BUG FOUND",
}
STATUS_LEVEL = {"accepted": "success", "needs_review": "warn", "rejected": "error", "possible_bug": "warn"}
RUNNING = ("queued", "analyzing", "generating")
TERMINAL_EVENTS = ("analysis_complete", "generation_complete")


class JobError(Exception):
    """A user-facing error with an HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    os.replace(tmp, path)


# --------------------------------------------------------------------------- zip handling

def safe_extract_zip(zip_path: Path, dest: Path, max_files: int, max_bytes: int) -> None:
    """Extract a zip, rejecting zip-slip paths, symlinks, too many files and zip bombs."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise JobError("The uploaded file is not a valid zip archive") from exc
    with zf:
        infos = zf.infolist()
        files = [i for i in infos if not i.is_dir()]
        if len(files) > max_files:
            raise JobError(f"Zip contains {len(files)} files; the limit is {max_files}", 413)
        if sum(i.file_size for i in files) > max_bytes:
            raise JobError("Zip expands to more than the allowed size", 413)
        dest = dest.resolve()
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts:
                raise JobError(f"Unsafe path in zip: {info.filename}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise JobError(f"Symbolic links are not allowed in the zip: {info.filename}")
            target = (dest / "/".join(parts)).resolve()
            if target != dest and dest not in target.parents:
                raise JobError(f"Unsafe path in zip: {info.filename}")
        for info in infos:
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p not in ("", ".")]
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _promote_single_root(extract_dir: Path, repo_dir: Path) -> None:
    """If the archive has one top-level folder (e.g. project/...), use that folder as the repo root."""
    entries = [p for p in extract_dir.iterdir() if p.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        entries[0].rename(repo_dir)
        shutil.rmtree(extract_dir, ignore_errors=True)
    else:
        extract_dir.rename(repo_dir)


def project_name_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


# --------------------------------------------------------------------------- job object

class Job:
    def __init__(self, job_dir: Path, state: dict):
        self.dir = job_dir
        self.state = state
        self.lock = threading.RLock()
        self.events: list[dict] = []
        self.functions: list[dict] = []
        events_file = job_dir / "events.jsonl"
        if events_file.is_file():
            for line in events_file.read_text().splitlines():
                if line.strip():
                    try:
                        self.events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        fn_file = job_dir / "functions.json"
        if fn_file.is_file():
            self.functions = json.loads(fn_file.read_text())

    @property
    def id(self) -> str:
        return self.state["job_id"]

    @property
    def repo(self) -> Path:
        return self.dir / "repo"

    # ----- persistence
    def save(self) -> None:
        with self.lock:
            self.state["updated_at"] = _now_iso()
            _write_json(self.dir / "job.json", self.state)

    def save_functions(self) -> None:
        with self.lock:
            _write_json(self.dir / "functions.json", self.functions)

    def update(self, **kw) -> None:
        with self.lock:
            self.state.update(kw)
            self.save()

    # ----- events
    def emit(self, event: str, data: dict) -> dict:
        with self.lock:
            rec = {"id": len(self.events) + 1, "event": event, "data": data}
            self.events.append(rec)
            with open(self.dir / "events.jsonl", "a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
            return rec

    def log(self, level: str, message: str) -> None:
        self.emit("log", {"ts": _now_iso(), "level": level, "message": message})

    def stage(self, stage: str, status: str) -> None:
        with self.lock:
            if status == "start":
                self.state["stage"] = stage
            self.state.setdefault("stages", {})[stage] = status
            self.save()
        self.emit("stage", {"stage": stage, "status": status})

    def events_after(self, last_id: int) -> list[dict]:
        with self.lock:
            return self.events[last_id:] if last_id >= 0 else list(self.events)

    # ----- views
    def function(self, fid: str) -> dict | None:
        return next((f for f in self.functions if f["id"] == fid), None)

    def summary(self) -> dict:
        with self.lock:
            return build_summary(self.state, self.functions)

    def public_state(self) -> dict:
        with self.lock:
            s = dict(self.state)
            s["counts"] = {
                "files": s.get("files_count", 0),
                "functions": len(self.functions),
                "candidates": sum(1 for f in self.functions if f.get("candidate")),
                "processed": sum(1 for f in self.functions if f.get("processed")),
            }
            s["last_event_id"] = len(self.events)
            return s


# --------------------------------------------------------------------------- manager

class JobManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or get_settings().workspace_dir)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def cleanup_old(self, max_age_hours: float | None = None) -> int:
        """Delete job folders older than max_age_hours; mark interrupted jobs as failed."""
        self.ensure_root()
        max_age = (max_age_hours if max_age_hours is not None else get_settings().workspace_max_age_hours) * 3600
        removed = 0
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            if time.time() - d.stat().st_mtime > max_age:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
                continue
            jf = d / "job.json"
            if jf.is_file() and d.name not in self.jobs:
                try:
                    state = json.loads(jf.read_text())
                except json.JSONDecodeError:
                    continue
                if state.get("status") in RUNNING:
                    job = Job(d, state)
                    job.emit("error", {"message": "The server restarted while this job was running",
                                       "recoverable": False})
                    job.update(status="failed", error="The server restarted while this job was running")
        return removed

    def get(self, job_id: str) -> Job:
        if not re.fullmatch(r"[a-f0-9]{8,32}", job_id or ""):
            raise JobError("Job not found", 404)
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                d = self.root / job_id
                jf = d / "job.json"
                if not jf.is_file():
                    raise JobError("Job not found", 404)
                job = Job(d, json.loads(jf.read_text()))
                self.jobs[job_id] = job
            return job

    def create(self, settings_in: dict, source: dict) -> Job:
        s = get_settings()
        self.ensure_root()
        job_id = uuid.uuid4().hex[:12]
        d = self.root / job_id
        d.mkdir(parents=True)
        settings = {
            "model": str(settings_in.get("model") or s.ollama_model),
            "max_functions": int(settings_in.get("max_functions") or s.max_functions_default),
            "coverage_threshold": float(
                settings_in["coverage_threshold"] if settings_in.get("coverage_threshold") is not None
                else s.coverage_threshold
            ),
        }
        if not 1 <= settings["max_functions"] <= 500:
            raise JobError("max_functions must be between 1 and 500")
        if not 0 < settings["coverage_threshold"] <= 100:
            raise JobError("coverage_threshold must be between 0 and 100")
        state = {
            "job_id": job_id,
            "status": "queued",
            "stage": None,
            "stages": {},
            "source": source,
            "project_name": source.get("name"),
            "settings": settings,
            "llm_provider": s.llm_provider,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "files_count": 0,
            "coverage_before": None,
            "coverage_after": None,
            "newly_covered": [],
            "progress": {"done": 0, "total": 0},
            "error": None,
        }
        job = Job(d, state)
        job.save()
        with self.lock:
            self.jobs[job_id] = job
        return job

    def create_from_zip(self, upload_path: Path, filename: str, settings_in: dict) -> Job:
        s = get_settings()
        name = Path(filename or "project.zip").stem or "project"
        job = self.create(settings_in, {"type": "zip", "name": name, "filename": filename})
        extract = job.dir / "extract"
        extract.mkdir()
        try:
            safe_extract_zip(upload_path, extract, s.max_zip_files, s.max_upload_mb * 1024 * 1024 * 10)
            _promote_single_root(extract, job.repo)
            if not iter_python_files(job.repo, include_tests=True):
                raise JobError("The zip does not contain any Python (.py) files")
        except JobError:
            shutil.rmtree(job.dir, ignore_errors=True)
            with self.lock:
                self.jobs.pop(job.id, None)
            raise
        return job

    def create_from_url(self, url: str, settings_in: dict) -> Job:
        url = (url or "").strip()
        if not GITHUB_URL_RE.match(url):
            raise JobError("Enter a public GitHub URL like https://github.com/owner/repo")
        return self.create(settings_in, {"type": "github", "name": project_name_from_url(url), "url": url})

    # ----- background phases
    def start_analysis(self, job: Job) -> None:
        threading.Thread(target=run_analysis, args=(job,), daemon=True, name=f"analyze-{job.id}").start()

    def start_generation(self, job: Job, function_ids: list[str] | None, all_: bool) -> list[str]:
        with job.lock:
            if job.state["status"] in RUNNING:
                raise JobError("A phase is already running for this job", 409)
            if job.state["status"] not in ("analyzed", "completed"):
                raise JobError("The analysis has not finished for this job", 409)
            if all_:
                ids = [f["id"] for f in job.functions if f.get("candidate")]
            else:
                known = {f["id"] for f in job.functions}
                ids = [fid for fid in dict.fromkeys(function_ids or []) if fid in known]
                unknown = [fid for fid in (function_ids or []) if fid not in known]
                if unknown:
                    raise JobError(f"Unknown function id: {unknown[0]}", 404)
            if not ids:
                raise JobError("No functions selected")
            check_llm_ready(job.state["settings"]["model"])
            job.state["status"] = "generating"
            job.state["error"] = None
            job.save()
        threading.Thread(target=run_generation, args=(job, ids), daemon=True, name=f"generate-{job.id}").start()
        return ids


def check_llm_ready(model: str) -> None:
    s = get_settings()
    if s.llm_provider == "mock":
        return
    status = ollama_status()
    if not status["reachable"]:
        raise JobError(f"Ollama is not reachable at {s.ollama_base_url}. Start it with `ollama serve`, then pull "
                       f"the model with `ollama pull {model}`.", 503)
    names = set(status["models"])
    if model not in names and f"{model}:latest" not in names:
        raise JobError(f"Model `{model}` is not installed in Ollama. Run `ollama pull {model}`.", 503)


# --------------------------------------------------------------------------- Phase A

def _clone(job: Job) -> None:
    s = get_settings()
    url = job.state["source"]["url"]
    job.log("info", f"Cloning {url} (full history)...")
    env = minimal_env(home=job.dir, extra={"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"})
    res = run_sandboxed(["git", "clone", "--no-recurse-submodules", "--", url, str(job.repo)], cwd=job.dir,
                        timeout=s.clone_timeout_sec, env=env)
    if res.timed_out:
        raise JobError(f"git clone timed out after {s.clone_timeout_sec}s")
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or ["unknown error"]
        raise JobError(f"git clone failed: {tail[0][:300]}")


def _fail(job: Job, message: str) -> None:
    job.log("error", message)
    job.emit("error", {"message": message, "recoverable": False})
    job.update(status="failed", error=message)


def run_analysis(job: Job) -> None:
    s = get_settings()
    try:
        job.update(status="analyzing")
        job.stage("parse", "start")
        if job.state["source"]["type"] == "github":
            _clone(job)
        all_py = iter_python_files(job.repo, include_tests=True)
        if not all_py:
            raise JobError("The project does not contain any Python (.py) files")
        job.update(files_count=len(all_py))
        job.log("info", f"Repository loaded: {len(all_py)} Python files found")
        extraction = extract_functions(job.repo)
        for w in extraction.warnings:
            job.log("warn", w)
        functions = extraction.functions
        job.log("info", f"Parsing code... {len(functions)} functions extracted")
        if not functions:
            job.log("warn", "No testable functions were found in the non-test source files")
        job.stage("parse", "done")

        job.stage("coverage", "start")
        python = prepare_python(job.repo, job.dir, s.deps_install_timeout_sec, job.log)
        job.update(python=python)
        has_tests = any(p for p in all_py if p not in extraction.files)
        if not has_tests:
            job.log("warn", "The project has no tests; every function starts at 0% coverage")
        cov = run_coverage(job.repo, job.dir, python, "before", timeout=max(s.test_timeout_sec * 10, 120))
        if not cov.ok:
            job.log("warn", f"Coverage run failed ({cov.error}); treating all functions as untested")
        elif cov.error:
            job.log("warn", cov.error)
        per_fn = map_function_coverage(functions, cov)
        threshold = job.state["settings"]["coverage_threshold"]
        for f in functions:
            pct = per_fn[f["id"]]["pct"]
            f.update(coverage_pct=pct, coverage_label=coverage_label(pct, threshold),
                     candidate=pct < threshold, status="pending", tests=[], processed=False,
                     last_modified_days=None, usage_count=None, risk_score=None, risk_label=None)
        job.update(coverage_before=cov.total_pct if cov.ok else 0.0)
        job.log("info", f"Running coverage analysis... current coverage: {round(job.state['coverage_before'])}%")
        job.stage("coverage", "done")

        job.stage("prioritize", "start")
        candidates = [f for f in functions if f["candidate"]]
        sites = find_call_sites(job.repo, extraction.trees)
        usage = {f["id"]: count_calls(f, sites) for f in functions}
        for f in functions:
            f["usage_count"] = usage[f["id"]]
            f["call_sites"] = example_call_sites(f, job.repo, sites)
        job.log("info", f"Ranking {len(candidates)} untested functions by risk")
        ranked, used_git = prioritize(job.repo, candidates, usage, s.risk_weight_recency, s.risk_weight_usage)
        if not used_git:
            job.log("warn", "No git history found; using file modification times for recency")
        others = sorted((f for f in functions if not f["candidate"]), key=lambda f: f["id"])
        for i, f in enumerate(ranked, 1):
            f["rank"] = i
        with job.lock:
            job.functions = ranked + others
            job.save_functions()
        top = ", ".join(f"`{f['qualname']}` ({f['risk_label']})" for f in ranked[:3])
        if top:
            job.log("info", f"Highest risk: {top}")
        job.stage("prioritize", "done")
        job.update(status="analyzed")
        job.log("success", "Analysis complete. Select functions and press Generate Tests.")
        job.emit("analysis_complete", {"summary_preview": job.summary()})
    except JobError as exc:
        _fail(job, exc.message)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        _fail(job, f"Analysis failed: {exc}")


# --------------------------------------------------------------------------- Phase B

def _collect_accepted(job: Job) -> list[str]:
    acc_dir = job.dir / "accepted_tests"
    shutil.rmtree(acc_dir, ignore_errors=True)
    acc_dir.mkdir()
    written = []
    for f in job.functions:
        keep = {t["name"] for t in f.get("tests", []) if t["status"] == "accepted"}
        if not keep or not f.get("test_code"):
            continue
        name = Path(f["test_file"]).name
        (acc_dir / name).write_text(keep_only_tests(f["test_code"], keep))
        written.append(name)
    return written


def _after_coverage(job: Job) -> None:
    s = get_settings()
    accepted = _collect_accepted(job)
    job.log("info", f"Collected {len(accepted)} accepted test file(s) into accepted_tests/")
    python = job.state.get("python") or prepare_python(job.repo, job.dir, s.deps_install_timeout_sec, job.log)
    targets = [str(job.repo)] + ([str(job.dir / "accepted_tests")] if accepted else [])
    job.log("info", "Re-running coverage with the original tests plus accepted tests...")
    cov = run_coverage(job.repo, job.dir, python, "after", timeout=max(s.test_timeout_sec * 10, 120),
                       test_targets=targets)
    if not cov.ok:
        job.log("warn", f"After-coverage run failed ({cov.error}); reusing the baseline numbers")
    per_fn = map_function_coverage(job.functions, cov) if cov.ok else {}
    threshold = job.state["settings"]["coverage_threshold"]
    newly = []
    with job.lock:
        for f in job.functions:
            after = per_fn.get(f["id"], {}).get("pct", f["coverage_pct"])
            f["coverage_after_pct"] = after
            f["coverage_after_label"] = coverage_label(after, threshold)
            if f["coverage_label"] != "tested" and f["coverage_after_label"] == "tested":
                newly.append(f["id"])
        job.save_functions()
    before = job.state["coverage_before"] or 0.0
    after_total = cov.total_pct if cov.ok else before
    job.update(coverage_after=after_total, newly_covered=newly)
    job.log("success", f"Coverage: {round(before)}% -> {round(after_total)}% ({after_total - before:+.0f}%)")


def run_generation(job: Job, ids: list[str]) -> None:
    s = get_settings()
    settings = job.state["settings"]
    try:
        client = get_llm_client(model=settings["model"])
        job.update(model_used="mock" if s.llm_provider == "mock" else settings["model"],
                   progress={"done": 0, "total": len(ids)})
        python = job.state.get("python") or prepare_python(job.repo, job.dir, s.deps_install_timeout_sec, job.log)
        ctx = FunctionContext(job.repo, job.dir, job.dir / "generated_tests", python, s.test_timeout_sec, client,
                              log=job.log)
        with job.lock:
            for fid in ids:
                f = job.function(fid)
                f.update(status="pending", tests=[], error=None)
            job.save_functions()
        for fid in ids:
            job.emit("function_update", {"function_id": fid, "status": "pending"})
        job.stage("generate", "start")
        job.stage("validate", "start")
        job.emit("progress", {"done": 0, "total": len(ids)})
        for i, fid in enumerate(ids, 1):
            f = job.function(fid)
            label = f["qualname"]
            with job.lock:
                f["status"] = "generating"
                job.save_functions()
            job.emit("function_update", {"function_id": fid, "status": "generating"})
            job.log("info", f"Generating test for `{label}`...")
            try:
                out = process_function(f, f.get("call_sites", []), ctx)
                with job.lock:
                    f.update(status=out.status, tests=out.tests, test_code=out.code, test_file=out.test_file,
                             attempts=out.attempts, processed=True, error=out.error)
                job.log(STATUS_LEVEL[out.status], f"Running test for `{label}`... {STATUS_TEXT[out.status]}")
            except Exception as exc:  # noqa: BLE001 - one function must never stop the run
                msg = f"{type(exc).__name__}: {exc}"
                with job.lock:
                    f.update(status="rejected", processed=True, error=msg,
                             tests=[{"name": "(generation failed)", "status": "rejected", "code": "", "attempts": 0,
                                     "reason": msg, "expected": None, "actual": None, "traceback": "",
                                     "verdict": None}])
                job.log("error", f"Error while processing `{label}`: {msg}; continuing")
            with job.lock:
                job.save_functions()
                job.state["progress"] = {"done": i, "total": len(ids)}
                job.save()
            job.emit("function_update", {"function_id": fid, "status": f["status"]})
            job.emit("progress", {"done": i, "total": len(ids)})
        job.stage("generate", "done")
        job.stage("validate", "done")

        job.stage("report", "start")
        _after_coverage(job)
        summary = job.summary()
        _write_json(job.dir / "summary.json", summary)
        job.stage("report", "done")
        job.update(status="completed")
        job.log("success", f"Done: {summary['accepted']} accepted, {summary['needs_review']} need review, "
                           f"{summary['rejected']} rejected, {summary['possible_bugs']} possible bug(s) found")
        job.emit("generation_complete", {"summary": summary})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        message = f"Generation failed: {exc}"
        job.log("error", message)
        job.emit("error", {"message": message, "recoverable": True})
        job.update(status="analyzed" if job.state.get("coverage_after") is None else "completed", error=message)


_manager: JobManager | None = None


def get_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_manager(root: Path | None = None) -> JobManager:
    global _manager
    _manager = JobManager(root)
    return _manager
