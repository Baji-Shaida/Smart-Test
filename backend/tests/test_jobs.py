import io
import json
import shutil
import stat
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import jobs as jobs_mod
from app.jobs import JobError, reset_manager, safe_extract_zip
from app.main import app


@pytest.fixture()
def client(tmp_path):
    reset_manager(tmp_path / "jobs")
    with TestClient(app) as c:
        yield c


def _zip_dir(src, dest_base):
    return shutil.make_archive(str(dest_base), "zip", root_dir=src.parent, base_dir=src.name)


def _wait(client, job_id, statuses, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job_id}").json()
        if state["status"] in statuses:
            return state
        time.sleep(0.2)
    raise AssertionError(f"job did not reach {statuses}: {state}")


def _parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        rec = {}
        for line in block.splitlines():
            if line.startswith(":") or ":" not in line:
                continue
            key, _, value = line.partition(": ")
            rec[key] = value
        if "event" in rec:
            events.append({"id": int(rec["id"]), "event": rec["event"], "data": json.loads(rec["data"])})
    return events


def _make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries:
            if isinstance(data, zipfile.ZipInfo):
                zf.writestr(data, name)
            else:
                zf.writestr(name, data)
    return buf.getvalue()


def test_zip_slip_and_limits(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(_make_zip([("../evil.py", "x = 1")]))
    with pytest.raises(JobError, match="Unsafe path"):
        safe_extract_zip(bad, tmp_path / "out1", 100, 10**6)
    absolute = tmp_path / "abs.zip"
    absolute.write_bytes(_make_zip([("/etc/evil.py", "x = 1")]))
    with pytest.raises(JobError, match="Unsafe path"):
        safe_extract_zip(absolute, tmp_path / "out2", 100, 10**6)
    link = zipfile.ZipInfo("link.py")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    sym = tmp_path / "sym.zip"
    sym.write_bytes(_make_zip([("/etc/passwd", link)]))
    with pytest.raises(JobError, match="Symbolic links"):
        safe_extract_zip(sym, tmp_path / "out3", 100, 10**6)
    many = tmp_path / "many.zip"
    many.write_bytes(_make_zip([(f"m{i}.py", "x = 1") for i in range(5)]))
    with pytest.raises(JobError, match="limit is 3"):
        safe_extract_zip(many, tmp_path / "out4", 3, 10**6)
    assert not (tmp_path / "evil.py").exists()


def test_create_job_validation(client):
    r = client.post("/api/jobs", files={"file": ("p.zip", _make_zip([("README.md", "hi")]), "application/zip")})
    assert r.status_code == 400 and "Python" in r.json()["error"]
    r = client.post("/api/jobs", files={"file": ("p.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400 and "zip" in r.json()["error"]
    r = client.post("/api/jobs", files={"file": ("p.zip", _make_zip([("../x.py", "x=1")]), "application/zip")})
    assert r.status_code == 400 and "Unsafe" in r.json()["error"]
    r = client.post("/api/jobs", data={"repo_url": "file:///etc"})
    assert r.status_code == 400 and "GitHub" in r.json()["error"]
    assert client.post("/api/jobs").status_code == 400
    r = client.post("/api/jobs", data={"repo_url": "https://github.com/a/b", "settings": "{bad"})
    assert r.status_code == 400
    assert client.get("/api/jobs/doesnotexist").json() == {"error": "Job not found"}
    assert client.get("/api/jobs/abcdef123456").status_code == 404


def test_full_two_phase_run_with_replay(client, sample_repo, tmp_path):
    archive = _zip_dir(sample_repo, tmp_path / "sample_repo")
    with open(archive, "rb") as fh:
        r = client.post("/api/jobs", files={"file": ("sample_repo.zip", fh, "application/zip")},
                        data={"settings": json.dumps({"max_functions": 5, "coverage_threshold": 60})})
    assert r.status_code == 201
    job_id = r.json()["job_id"]
    state = _wait(client, job_id, {"analyzed", "failed"})
    assert state["status"] == "analyzed", state
    assert state["settings"]["max_functions"] == 5
    assert client.get(f"/api/jobs/{job_id}/tests.zip").status_code == 404

    events = _parse_sse(client.get(f"/api/jobs/{job_id}/events").text)
    assert [e["id"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1]["event"] == "analysis_complete"
    messages = [e["data"]["message"] for e in events if e["event"] == "log"]
    assert any(m.startswith("Repository loaded: ") for m in messages)
    assert any("current coverage: 46%" in m for m in messages)
    preview = events[-1]["data"]["summary_preview"]
    assert preview["coverage_before"] == pytest.approx(45.83, abs=0.5) and preview["untested_before"] == 7

    fns = client.get(f"/api/jobs/{job_id}/functions").json()
    candidates = [f for f in fns if f["candidate"]]
    assert candidates[0]["id"] == "billing.py::apply_coupon" and candidates[0]["risk_label"] == "High"
    assert "source" not in fns[0]
    assert client.post(f"/api/jobs/{job_id}/generate", json={"function_ids": ["nope::x"]}).status_code == 404
    assert client.post(f"/api/jobs/{job_id}/generate", json={}).status_code == 400

    ids = ["billing.py::apply_coupon", "billing.py::calculate_discount", "cart.py::Cart.remove_item"]
    r = client.post(f"/api/jobs/{job_id}/generate", json={"function_ids": ids})
    assert r.status_code == 202
    assert client.post(f"/api/jobs/{job_id}/generate", json={"all": True}).status_code in (409, 202)
    state = _wait(client, job_id, {"completed"})

    last = events[-1]["id"]
    replay = _parse_sse(client.get(f"/api/jobs/{job_id}/events", headers={"Last-Event-ID": str(last)}).text)
    assert replay[0]["id"] == last + 1
    assert replay[-1]["event"] == "generation_complete"
    updates = {e["data"]["function_id"]: e["data"]["status"] for e in replay if e["event"] == "function_update"}
    assert updates == {"billing.py::apply_coupon": "possible_bug", "billing.py::calculate_discount": "accepted",
                       "cart.py::Cart.remove_item": "rejected"}
    stages = [(e["data"]["stage"], e["data"]["status"]) for e in replay if e["event"] == "stage"]
    assert ("report", "done") in stages
    assert any(e["event"] == "progress" and e["data"] == {"done": 3, "total": 3} for e in replay)
    assert any(e["event"] == "log" and e["data"]["message"] == "Running test for `apply_coupon`... POSSIBLE BUG FOUND"
               for e in replay)
    q = _parse_sse(client.get(f"/api/jobs/{job_id}/events?last_event_id={len(events) + len(replay) - 2}").text)
    assert len(q) == 2

    summary = client.get(f"/api/jobs/{job_id}/summary").json()
    assert summary["generated"] and summary["coverage_after"] > summary["coverage_before"]
    assert summary["possible_bugs"] == 1 and summary["bugs"][0]["test"] == "test_apply_coupon_at_minimum_boundary"
    assert summary["functions_processed"] == 3
    assert summary["untested_after"] < summary["untested_before"]
    assert "billing.py::calculate_discount" in summary["newly_covered"]

    detail = client.get(f"/api/jobs/{job_id}/functions/billing.py::apply_coupon").json()
    assert "def apply_coupon" in detail["source"]
    bug = next(t for t in detail["tests"] if t["status"] == "possible_bug")
    assert bug["expected"] == "45.0" and bug["actual"] == "50" and bug["verdict"]["verdict"] == "likely_bug"

    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{job_id}/tests.zip").content))
    names = sorted(z.namelist())
    assert names == ["accepted_tests/test_billing__apply_coupon.py",
                     "accepted_tests/test_billing__calculate_discount.py"]
    coupon = z.read("accepted_tests/test_billing__apply_coupon.py").decode()
    assert "test_apply_coupon_at_minimum_boundary" not in coupon and "test_apply_coupon_above_minimum" in coupon
    assert not (sample_repo / "tests" / "test_billing__apply_coupon.py").exists()


def test_one_function_failure_is_not_fatal(client, sample_repo, tmp_path, monkeypatch):
    archive = _zip_dir(sample_repo, tmp_path / "sample_repo")
    real = jobs_mod.process_function

    def flaky(fn, sites, ctx):
        if fn["name"] == "apply_coupon":
            raise RuntimeError("LLM exploded")
        return real(fn, sites, ctx)

    monkeypatch.setattr(jobs_mod, "process_function", flaky)
    with open(archive, "rb") as fh:
        job_id = client.post("/api/jobs", files={"file": ("s.zip", fh, "application/zip")}).json()["job_id"]
    _wait(client, job_id, {"analyzed"})
    client.post(f"/api/jobs/{job_id}/generate",
                json={"function_ids": ["billing.py::apply_coupon", "billing.py::calculate_discount"]})
    _wait(client, job_id, {"completed"})
    a = client.get(f"/api/jobs/{job_id}/functions/billing.py::apply_coupon").json()
    assert a["status"] == "rejected" and "LLM exploded" in a["error"]
    assert client.get(f"/api/jobs/{job_id}/functions/billing.py::calculate_discount").json()["status"] == "accepted"


def test_github_clone_failure_reports_error(client, monkeypatch):
    def fake_clone(job):
        raise JobError("git clone failed: repository not found")

    monkeypatch.setattr(jobs_mod, "_clone", fake_clone)
    job_id = client.post("/api/jobs", data={"repo_url": "https://github.com/nobody/missing"}).json()["job_id"]
    state = _wait(client, job_id, {"failed"})
    assert "repository not found" in state["error"]
    events = _parse_sse(client.get(f"/api/jobs/{job_id}/events").text)
    assert events[-1]["event"] == "error" and events[-1]["data"]["recoverable"] is False


def test_project_without_tests_or_git(client, sample_repo_nogit, tmp_path):
    shutil.rmtree(sample_repo_nogit / "tests")
    archive = _zip_dir(sample_repo_nogit, tmp_path / "nogit")
    with open(archive, "rb") as fh:
        job_id = client.post("/api/jobs", files={"file": ("nogit.zip", fh, "application/zip")}).json()["job_id"]
    state = _wait(client, job_id, {"analyzed", "failed"})
    assert state["status"] == "analyzed" and state["coverage_before"] == 0
    msgs = [e["data"]["message"] for e in _parse_sse(client.get(f"/api/jobs/{job_id}/events").text)
            if e["event"] == "log"]
    assert any("no tests" in m for m in msgs) and any("No git history" in m for m in msgs)


def test_ollama_unreachable_returns_clear_error(client, sample_repo, tmp_path, monkeypatch):
    archive = _zip_dir(sample_repo, tmp_path / "sample_repo")
    with open(archive, "rb") as fh:
        job_id = client.post("/api/jobs", files={"file": ("s.zip", fh, "application/zip")}).json()["job_id"]
    _wait(client, job_id, {"analyzed"})
    monkeypatch.setattr(jobs_mod.get_settings(), "llm_provider", "ollama")
    monkeypatch.setattr(jobs_mod, "ollama_status", lambda: {"reachable": False, "models": [], "error": "refused"})
    r = client.post(f"/api/jobs/{job_id}/generate", json={"all": True})
    assert r.status_code == 503 and "ollama serve" in r.json()["error"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "analyzed"


def test_cleanup_old_workspaces(tmp_path):
    import os

    manager = reset_manager(tmp_path / "jobs")
    manager.ensure_root()
    old = manager.root / "aaaaaaaaaaaa"
    old.mkdir()
    os.utime(old, (time.time() - 48 * 3600,) * 2)
    running = manager.root / "bbbbbbbbbbbb"
    running.mkdir()
    (running / "job.json").write_text(json.dumps({"job_id": "bbbbbbbbbbbb", "status": "generating"}))
    assert manager.cleanup_old(24) == 1
    assert not old.exists()
    assert json.loads((running / "job.json").read_text())["status"] == "failed"
