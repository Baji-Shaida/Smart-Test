"""FastAPI application: CORS, REST endpoints, SSE event stream."""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .generator import ollama_status
from .jobs import RUNNING, JobError, get_manager

LIST_FIELDS_EXCLUDED = ("source", "imports", "class_context", "test_code", "call_sites")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        removed = get_manager().cleanup_old()
        if removed:
            print(f"SmartTest: removed {removed} job workspace(s) older than "
                  f"{get_settings().workspace_max_age_hours}h")
    except Exception as exc:  # noqa: BLE001
        print(f"SmartTest: workspace cleanup failed: {exc}")
    yield


app = FastAPI(title="SmartTest", version="1.0.0", lifespan=lifespan)
_s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_s.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(JobError)
async def job_error_handler(_: Request, exc: JobError):
    return JSONResponse({"error": exc.message}, status_code=exc.status)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse({"error": f"Invalid request: {loc} {first.get('msg', '')}".strip()}, status_code=422)


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    status = ollama_status()
    return {
        "status": "ok",
        "llm_provider": s.llm_provider,
        "ollama_reachable": status["reachable"],
        "ollama_base_url": s.ollama_base_url,
        "model": s.ollama_model,
        "model_installed": s.ollama_model in status["models"],
        "error": status["error"],
    }


@app.get("/api/models")
def models() -> dict:
    status = ollama_status()
    return {"reachable": status["reachable"], "models": status["models"], "default": get_settings().ollama_model}


def _parse_settings(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JobError("settings must be a JSON object") from exc
    if not isinstance(data, dict):
        raise JobError("settings must be a JSON object")
    return data


@app.post("/api/jobs", status_code=201)
async def create_job(file: UploadFile | None = File(None), repo_url: str | None = Form(None),
                     settings: str | None = Form(None)) -> dict:
    s = get_settings()
    opts = _parse_settings(settings)
    manager = get_manager()
    if file is not None and file.filename:
        if not file.filename.lower().endswith(".zip"):
            raise JobError("Upload a .zip file")
        limit = s.max_upload_mb * 1024 * 1024
        manager.ensure_root()
        with tempfile.NamedTemporaryFile(suffix=".zip", dir=manager.root, delete=False) as tmp:
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise JobError(f"Upload is larger than {s.max_upload_mb} MB", 413)
                tmp.write(chunk)
        try:
            job = await asyncio.to_thread(manager.create_from_zip, Path(tmp.name), file.filename, opts)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    elif repo_url and repo_url.strip():
        job = manager.create_from_url(repo_url, opts)
    else:
        raise JobError("Provide a zip file or a GitHub repository URL")
    manager.start_analysis(job)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return get_manager().get(job_id).public_state()


def _sse(rec: dict) -> str:
    return f"id: {rec['id']}\nevent: {rec['event']}\ndata: {json.dumps(rec['data'], default=str)}\n\n"


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str, request: Request, last_event_id: int | None = None):
    """SSE stream. Replays events after Last-Event-ID (header or ?last_event_id=) and then follows live.

    The stream closes once the job is idle (analysis or generation finished, or failed) and every
    event has been sent; the client reopens it with the last id when it starts the next phase.
    """
    job = get_manager().get(job_id)
    header = request.headers.get("last-event-id")
    start = last_event_id if last_event_id is not None else (int(header) if header and header.isdigit() else 0)

    async def stream():
        sent = max(0, start)
        yield "retry: 2000\n\n"
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break
            batch = job.events_after(sent)
            for rec in batch:
                yield _sse(rec)
                sent = rec["id"]
            if batch:
                idle_ticks = 0
            elif job.state.get("status") not in RUNNING:
                break
            else:
                idle_ticks += 1
                if idle_ticks % 50 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/functions")
def list_functions(job_id: str) -> list[dict]:
    job = get_manager().get(job_id)
    with job.lock:
        out = []
        for f in job.functions:
            rec = {k: v for k, v in f.items() if k not in LIST_FIELDS_EXCLUDED}
            rec["tests"] = [{"name": t["name"], "status": t["status"]} for t in f.get("tests", [])]
            out.append(rec)
        return out


@app.get("/api/jobs/{job_id}/functions/{fid:path}")
def get_function(job_id: str, fid: str) -> dict:
    job = get_manager().get(job_id)
    f = job.function(fid)
    if f is None:
        raise JobError("Function not found", 404)
    with job.lock:
        return dict(f)


class GenerateBody(BaseModel):
    function_ids: list[str] | None = None
    all: bool = False


@app.post("/api/jobs/{job_id}/generate", status_code=202)
def generate(job_id: str, body: GenerateBody) -> dict:
    job = get_manager().get(job_id)
    ids = get_manager().start_generation(job, body.function_ids, body.all)
    return {"job_id": job.id, "function_ids": ids, "status": "generating"}


@app.get("/api/jobs/{job_id}/summary")
def summary(job_id: str) -> dict:
    return get_manager().get(job_id).summary()


@app.get("/api/jobs/{job_id}/report.pdf")
def report_pdf(job_id: str):
    job = get_manager().get(job_id)
    if job.state.get("status") not in ("analyzed", "completed"):
        raise JobError("The report is available after the analysis finishes", 409)
    from .reporter.pdf import build_pdf

    with job.lock:
        data = build_pdf(job.state, job.functions, job.summary())
    name = f"smarttest-report-{job.state.get('project_name') or job.id}.pdf"
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_name(name)}"'})


@app.get("/api/jobs/{job_id}/tests.zip")
def tests_zip(job_id: str):
    job = get_manager().get(job_id)
    acc = job.dir / "accepted_tests"
    files = sorted(acc.glob("test_*.py")) if acc.is_dir() else []
    if not files:
        raise JobError("No accepted tests yet", 404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"accepted_tests/{f.name}")
    name = f"smarttest-accepted-tests-{job.state.get('project_name') or job.id}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_name(name)}"'})


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


__all__ = ["app"]
