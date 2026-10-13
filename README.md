# SmartTest — AI-Powered Code Coverage and Test Automation Tool

Work in progress (built phase by phase following `docs/SmartTest_Technical_Specification.pdf`).

## Status

- Phases 0-6 done: analyzer, coverage, prioritizer, generator, validator, job orchestration with
  JSON storage under `data/jobs/<id>/`, SSE event stream with `Last-Event-ID` replay and all REST endpoints.
- Frontend, PDF report and the full README follow in the next phases.

## Quick backend check (mock LLM, no Ollama needed)

```bash
cd backend
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
LLM_PROVIDER=mock .venv/bin/uvicorn app.main:app --port 8000
# in another shell, from the repo root
python3 scripts/create_sample_repo.py --force --zip
curl -F file=@sample_repo.zip localhost:8000/api/jobs            # -> {"job_id": "..."}
curl -N localhost:8000/api/jobs/<id>/events                      # live feed (closes when the phase ends)
curl -X POST -H 'content-type: application/json' -d '{"all":true}' localhost:8000/api/jobs/<id>/generate
curl -N -H 'Last-Event-ID: 14' localhost:8000/api/jobs/<id>/events   # replay from event 15
curl localhost:8000/api/jobs/<id>/summary
```
