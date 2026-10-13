# SmartTest — AI-Powered Code Coverage and Test Automation Tool

SmartTest takes a Python project (a `.zip` upload or a public GitHub URL), finds the functions with no or low
test coverage, ranks them by risk (how recently they changed in git + how often they are called), asks a
**local** LLM (Ollama) to write pytest tests for the riskiest ones, runs those tests in a sandboxed subprocess
and classifies every test as **Accepted**, **Needs Review**, **Rejected** or **Possible Bug Found**. The web UI
shows a live terminal-style feed, before/after coverage cards, a side-by-side view of each function and its
generated tests, a Bug Report, and exports a PDF report plus a zip of the accepted tests.

Everything is free and local: no paid API, no API key, no database (job state is JSON files under
`backend/data/jobs/<job_id>/`). The full specification is in
[`docs/SmartTest_Technical_Specification.pdf`](docs/SmartTest_Technical_Specification.pdf).

| Layer    | Stack |
|----------|-------|
| Backend  | Python 3.11+, FastAPI, Uvicorn, `ast`, coverage.py, GitPython, pytest, reportlab |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, react-syntax-highlighter (Prism) |
| LLM      | Ollama (`qwen2.5-coder:7b` by default) through a pluggable `LLMClient`; `MockLLMClient` for tests/demo |

## 1. Install

Prerequisites: **Python 3.11+**, **Node.js 18+** (with npm), **git**, and (for real test generation)
[Ollama](https://ollama.com/download).

```bash
git clone https://github.com/Baji-Shaida/Smart-Test.git
cd Smart-Test

# backend
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip install -r requirements.txt
cp ../.env.example .env                          # optional, defaults work out of the box
cd ..

# frontend
cd frontend
npm install
cd ..
```

(`uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt` works too.)

## 2. Ollama setup

```bash
# install from https://ollama.com/download, then:
ollama serve                      # starts the local server on http://localhost:11434 (often already running as a service)
ollama pull qwen2.5-coder:7b      # ~4.7 GB, the default model
```

Any other installed model can be picked in the UI (the dropdown is filled from `GET /api/models`) or set with
`OLLAMA_MODEL`. A 7B model runs on a typical laptop (8 GB+ RAM); generation takes a few seconds to a minute per
function. If Ollama is not running, the UI shows the commands above; analysis still works, only generation is
blocked.

**No Ollama?** Start the backend with `LLM_PROVIDER=mock`. The mock client returns deterministic canned tests
for the sample repository, so the full flow (Accepted, Needs Review, Rejected and Possible Bug Found) can be
demonstrated without a model.

## 3. Run (one command each)

```bash
# terminal 1 — backend on http://127.0.0.1:8000
cd backend && .venv/bin/uvicorn app.main:app --port 8000
#   with the mock LLM:  cd backend && LLM_PROVIDER=mock .venv/bin/uvicorn app.main:app --port 8000

# terminal 2 — frontend on http://localhost:5173 (proxies /api to the backend)
cd frontend && npm run dev
```

Open <http://localhost:5173>. The header badge shows whether the backend, Ollama and the model are ready.

## 4. Demo script (sample repository)

```bash
python3 scripts/create_sample_repo.py --force --zip    # creates ./sample_repo (with dated git history) and ./sample_repo.zip
```

`sample_repo/` is a tiny shop (`billing.py`, `cart.py`, `checkout.py`, `utils.py`) built over 8+
dated commits so recency differs per function. Its baseline coverage is about 46 %. `billing.apply_coupon`
contains a planted bug (`>` instead of `>=` on the minimum amount; the docstring says "at least"), and
`utils.chunk_list` drops the last partial chunk. Both folders are generated and git-ignored.

1. Start the backend (`LLM_PROVIDER=mock` for a deterministic run, or with Ollama) and the frontend.
2. On the Home screen, drop `sample_repo.zip` (or paste a GitHub URL), optionally open *Advanced settings*
   (model, max functions, coverage threshold) and press **Analyze**.
3. Analysis Dashboard: watch the live feed and stepper (Parse → Coverage → Prioritize). The ranked table shows
   `apply_coupon` at the top with **High** risk. The top N (max functions) are preselected.
4. Press **Generate Tests** (selected) or **Generate All**. The Generation view streams every step; status chips
   change as each function finishes and the cards update live.
5. Open `apply_coupon`: the original function (left) and generated tests (right, one tab per test) are
   syntax-highlighted. The boundary test is flagged **Possible Bug Found** with expected `45.0`, actual `50`,
   the verification reason and the traceback under the panels.
6. **Bug Report** lists every possible bug with file/line, failing test, expected vs actual and reason.
7. **Summary** shows coverage 46 % → 89 % with the mock, per-function results, and the **Download PDF report**
   and **Download accepted tests (.zip)** buttons.

Expected mock results: `calculate_discount`, `checkout`, `order_reference` Accepted (the latter after a syntax
retry), `quick_quote` Needs Review, `Cart.remove_item` Rejected, `apply_coupon` and `chunk_list` Possible Bug
Found.

The same flow from the command line:

```bash
curl -F file=@sample_repo.zip localhost:8000/api/jobs                     # -> {"job_id": "..."}
curl -N localhost:8000/api/jobs/<id>/events                               # SSE live feed
curl -X POST -H 'content-type: application/json' -d '{"all":true}' localhost:8000/api/jobs/<id>/generate
curl -N -H 'Last-Event-ID: 14' localhost:8000/api/jobs/<id>/events        # replay everything after event 14
curl localhost:8000/api/jobs/<id>/summary
curl -o report.pdf localhost:8000/api/jobs/<id>/report.pdf
curl -o tests.zip  localhost:8000/api/jobs/<id>/tests.zip
```

## 5. Configuration

Set in the environment or in `backend/.env` (see [`.env.example`](.env.example)).

| Variable | Default | Meaning |
|----------|---------|---------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `mock` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | default model |
| `LLM_TIMEOUT_SEC` | `120` | per LLM call |
| `TEST_TIMEOUT_SEC` | `30` | per pytest subprocess |
| `COVERAGE_THRESHOLD` | `60` | functions below this % are candidates |
| `MAX_FUNCTIONS_DEFAULT` | `10` | functions preselected for generation |
| `MAX_UPLOAD_MB` / `MAX_ZIP_FILES` | `50` / `5000` | upload limits |
| `WORKSPACE_DIR` | `./data/jobs` | job folders (relative to `backend/`) |
| `CORS_ORIGINS` | `http://localhost:5173,...` | only needed if the UI is not served through the Vite proxy |

The frontend reads `VITE_BACKEND_URL` (default `http://127.0.0.1:8000`) for its dev proxy.

## 6. How it works

1. **Ingest** — zip is validated (zip-slip, absolute paths, symlinks, size and file-count limits) and extracted;
   GitHub URLs are cloned with full history (needed for recency).
2. **Parse** — `ast` extracts every function/method (outside test files and `venv`, `.git`, `node_modules`,
   `build`, `dist`, ...), its source, signature, docstring and line range, and counts call sites.
3. **Coverage** — the project's own tests run under `coverage run -m pytest`; covered lines are mapped onto
   function ranges. Below the threshold = candidate (`untested` at 0 %, `partial` otherwise).
4. **Prioritize** — `risk = 0.5 × recency + 0.5 × usage` (git blame of the function's lines, normalized;
   High ≥ 0.66, Medium ≥ 0.33, else Low).
5. **Generate** — one function at a time with the section 9 prompt; up to 2 retries on static-check failures
   (syntax, imports, trivial tests, etc.).
6. **Validate** — tests run with pytest in a subprocess inside the job workspace with a timeout. Collection /
   import / fixture / arity errors are regenerated; plausible assertion failures are re-run once (flakiness), then
   the LLM verification prompt decides `likely_bug` → **Possible Bug Found**, `test_wrong` → regenerate once,
   `unclear` → **Needs Review**. Malformed tests are never shown as bugs.
7. **Report** — accepted tests are collected, coverage is re-measured with the original + accepted tests, and
   the summary, PDF and zip are produced.

API: `GET /api/health`, `GET /api/models`, `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/events`
(SSE, supports `Last-Event-ID`), `GET /api/jobs/{id}/functions[/{fid}]`, `POST /api/jobs/{id}/generate`,
`GET /api/jobs/{id}/summary`, `GET /api/jobs/{id}/report.pdf`, `GET /api/jobs/{id}/tests.zip`.

## 7. Tests

```bash
cd backend && .venv/bin/python -m pytest        # unit tests for every module + tests/test_e2e.py (mock LLM)
cd frontend && npm run build && npm test && npm run lint
```

`backend/tests/test_e2e.py` runs the whole flow through the HTTP API on the generated sample repo with the mock
LLM and checks the classifications, summary, PDF sections and the accepted-tests zip.

## 8. Optional Docker setup

```bash
docker compose up --build        # backend :8000, frontend :5173; Ollama stays on the host
LLM_PROVIDER=mock docker compose up --build
```

The backend container runs as an unprivileged user, so uploaded code and generated tests cannot touch your
machine's files. Ollama is reached at `host.docker.internal:11434`.

## 9. Safety note

SmartTest **executes the uploaded project's tests and the AI-generated tests**. It is intended for local use on
code you trust. Mitigations: tests only run in subprocesses with timeouts (the whole process group is killed on
timeout), inside the job's workspace, with a minimal environment (backend secrets are not passed); zip-slip,
symlink, upload size and file-count checks; workspaces older than 24 h are deleted at startup. For stronger
isolation use the Docker setup above.

## 10. Limitations

- Tests are AI-generated and must be reviewed by a human before you rely on them.
- The LLM infers intent from code and docstrings; it cannot know what the developer meant. Poorly named or
  undocumented functions yield weaker tests.
- **Possible Bug Found** means "worth a human look", not proof of a bug.
- Static analysis and subprocess runs do not reproduce every runtime condition (network, concurrency, external
  services).
- Functions needing complex fixtures or external services may be Rejected or Needs Review.
- Only Python projects with pytest-style (or unittest-compatible) tests are supported; private GitHub repos are
  not.

## 11. Choices made where the spec left details open

- **Background work**: one daemon thread per job phase (no task queue); one phase at a time per job.
- **Event log**: every SSE event is appended to `events.jsonl` with an increasing id; reconnects pass
  `Last-Event-ID` (header) or `?last_event_id=` (EventSource cannot set headers on manual reconnects) and get
  everything after it. The stream closes when the phase ends.
- **Project dependencies**: if `requirements.txt` lists packages they are installed into a per-job virtualenv
  that can also see the backend's pytest/coverage; on failure a warning is logged and the base environment is
  used.
- **Zip layout**: a zip with a single top-level folder is unwrapped so the project root is that folder.
- **Risk labels**: High ≥ 0.66, Medium ≥ 0.33, Low otherwise; functions with no git history get recency 0.
- **Accepted test file names**: `test_<module path>__<function>.py` inside `accepted_tests/` in the zip.
- **Workspace cleanup**: runs at backend startup (`WORKSPACE_MAX_AGE_HOURS`, default 24).
- **Mock provider**: `LLM_PROVIDER=mock` returns canned responses keyed by function name for the sample repo
  and a generic simple test otherwise.

## Project structure

```
backend/   FastAPI app (app/analyzer, coverage_check, prioritizer, generator, validator, reporter, jobs.py, main.py) + tests/
frontend/  React + Vite UI (src/pages, src/components, src/hooks, src/api)
scripts/   create_sample_repo.py and sample_repo_template/
docs/      SmartTest_Technical_Specification.pdf
docker-compose.yml, .env.example
```
